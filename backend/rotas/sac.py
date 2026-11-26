"""Pedidos SAC — caixa de entrada das vendas do SAC Varejo (Softline).

Fluxo:
- Cada venda com situação A chega aqui (pelo robô de sincronização ou enviando o PDF à mão)
  e fica AGUARDANDO a decisão do gestor: enviar para a fábrica, terceirizado ou ignorar.
- Orçamentos (L) e vendas canceladas (C) nunca entram. Se um L virar A, entra na leitura seguinte.
- De-para: produto como aparece no PDF do SAC -> produto do estoque PRATIC (ou "não é da fábrica").
  A chave é o NOME do produto (até antes dos detalhes de arte/impressão), porque o código do SAC
  é de família: o código 4 serve para Altacopos 330, 440 e 550; o 102 para tampas de duas marcas.
  Feito uma vez por produto; depois a venda já vem com os itens vinculados.
- Venda que já entrou e virou C no SAC fica marcada "cancelada no SAC" para o gestor decidir
  (nada é excluído sozinho: se já houve produção, mexeria no estoque sem ninguém ver).
"""
import os
import re
import json
import shutil
import tempfile
import datetime
from typing import Optional, List, Dict

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import get_conn
import database as _database
from auth_utils import get_current_user

router = APIRouter()

DESTINOS = ("aguardando", "fabrica", "terceirizado", "ignorado", "cancelado")


def _so_gestor(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Pedidos SAC: só o Gestor.")
    return current_user


def _agora() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pasta_pdfs() -> str:
    p = os.path.join(os.path.dirname(os.path.abspath(_database.DB_PATH)), "sac_pdfs")
    os.makedirs(p, exist_ok=True)
    return p


def tabelas(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS sac_vendas (
        venda TEXT PRIMARY KEY,              -- nº da venda no SAC (= nº do pedido no PRATIC)
        cliente TEXT, vendedor TEXT, total REAL, lancamento TEXT,
        situacao TEXT,                       -- última situação lida no SAC: A / L / C
        destino TEXT DEFAULT 'aguardando',   -- aguardando | fabrica | terceirizado | ignorado | cancelado
        pedido_id INTEGER,
        arquivo TEXT,                        -- PDF guardado em banco/sac_pdfs
        dados_json TEXT,                     -- o que foi lido do PDF (cliente, itens com código)
        origem TEXT,                         -- robo | manual
        cancelado_em TEXT,                   -- quando o SAC passou de A para C
        cancel_resolvido INTEGER DEFAULT 0,
        decidido_por TEXT, decidido_em TEXT,
        criado_em TEXT, atualizado_em TEXT)""")
    cols = [c[1] for c in conn.execute("PRAGMA table_info(sac_depara)").fetchall()]
    if cols and "chave" not in cols:   # versão de teste antiga (chave por código) — refaz
        conn.execute("DROP TABLE sac_depara")
    conn.execute("""CREATE TABLE IF NOT EXISTS sac_depara (
        chave TEXT PRIMARY KEY,              -- nome do produto no SAC, normalizado (ver chave_produto)
        codigo TEXT,                         -- código (família) no SAC, só para referência
        descricao TEXT,
        produto_id INTEGER,                  -- produto do estoque PRATIC
        terceirizado INTEGER DEFAULT 0,      -- 1 = item que não é da fábrica (não entra no pedido)
        atualizado_por TEXT, atualizado_em TEXT)""")


def chave_produto(descricao: str) -> str:
    """'COPO PP - ALTACOPOS - 550 MLS - ARTE X, IMPRESSÃO PRETO' -> 'COPO PP ALTACOPOS 550 ML'."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(descricao or "").upper())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    # padrão do SAC: "TIPO - MARCA - TAMANHO - detalhes": guarda até o trecho do tamanho
    partes = re.split(r"\s+[-–]\s+", s)
    for i, pt in enumerate(partes):
        if i and re.match(r"^\d+(?:[.,]\d+)?(?:/\d+)*\s*(?:MLS?|M|L|LITROS?|LTS?|G|KG)?\b", pt.strip()):
            s = " - ".join(partes[:i + 1])
            break
    s = re.split(r"\s*[-–]?\s*\bARTES?\b|,|\s+IMPRESS|\s+-\s+PRODUZIR|\s*\(|\s+-\s+FRENTE|\s+LOGO\b", s)[0]
    s = re.sub(r"[^A-Z0-9/]+", " ", s)
    s = re.sub(r"\b(\d+(?:/\d+)*)\s*(MLS|ML|M)\b", r"\1 ML", s)
    return re.sub(r"\s+", " ", s).strip()[:120]


# ─── leitura do PDF ──────────────────────────────────────────────────────────
def _ler_pdf(caminho: str, nome: str) -> dict:
    from rotas.pedidos import _extract_text_from_file, _is_pedido_sac, _parse_pedido_sac, _parse_pedido_text
    texto = _extract_text_from_file(caminho, nome)
    return _parse_pedido_sac(texto) if _is_pedido_sac(texto) else _parse_pedido_text(texto)


def _total_itens(itens) -> float:
    t = 0.0
    for it in itens or []:
        try:
            t += float(it.get("valor_total") or (float(it.get("quantidade") or 0) * float(it.get("valor_unitario") or 0)) or 0)
        except (TypeError, ValueError):
            pass
    return round(t, 2)


def registrar_pdf(conn, caminho: str, nome: str, origem: str = "manual", situacao: str = "A",
                  meta: Optional[dict] = None) -> dict:
    """Coloca uma venda na caixa de entrada a partir do PDF do pedido. Não duplica:
    venda já conhecida só atualiza a situação. Faz commit."""
    tabelas(conn)
    parsed = _ler_pdf(caminho, nome)
    venda = str(parsed.get("numero_pedido") or (meta or {}).get("venda") or "").strip()
    if not venda:
        return {"status": "erro", "arquivo": nome, "motivo": "Não achei o nº da venda no PDF (é um pedido do SAC?)"}
    meta = meta or {}
    ja = conn.execute("SELECT venda, destino FROM sac_vendas WHERE venda = ?", (venda,)).fetchone()
    if ja:
        atualizar_situacao(conn, venda, situacao, meta)
        return {"status": "ja_existe", "venda": venda, "destino": ja["destino"]}

    final = os.path.join(_pasta_pdfs(), f"venda_{re.sub(r'[^0-9A-Za-z_-]', '', venda)}.pdf")
    shutil.copyfile(caminho, final)
    cli = (parsed.get("cliente") or {}).get("razao_social")
    # Já existe no PRATIC (importado antes pela importação normal)? Entra já como "fábrica".
    ped = conn.execute("SELECT id FROM pedidos WHERE numero_pedido = ?", (venda,)).fetchone()
    destino = "fabrica" if ped else "aguardando"
    conn.execute("""INSERT INTO sac_vendas (venda, cliente, vendedor, total, lancamento, situacao, destino, pedido_id,
                        arquivo, dados_json, origem, criado_em, atualizado_em, decidido_por, decidido_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (venda, meta.get("cliente") or cli, parsed.get("vendedor"),
                  meta.get("total") if meta.get("total") is not None else _total_itens(parsed.get("itens")),
                  meta.get("lancamento"), situacao, destino, ped["id"] if ped else None,
                  os.path.basename(final), json.dumps(parsed, ensure_ascii=False, default=str), origem,
                  _agora(), _agora(), "já importado" if ped else None, _agora() if ped else None))
    conn.commit()
    return {"status": "registrada", "venda": venda, "destino": destino, "cliente": cli}


def atualizar_situacao(conn, venda: str, situacao: str, meta: Optional[dict] = None) -> Optional[str]:
    """Situação lida no SAC para uma venda que já está aqui. Devolve o que mudou ou None. Faz commit."""
    tabelas(conn)
    r = conn.execute("SELECT * FROM sac_vendas WHERE venda = ?", (str(venda),)).fetchone()
    if not r:
        return None
    situacao = (situacao or "").strip().upper()[:1]
    mudou = None
    if situacao and situacao != (r["situacao"] or ""):
        if situacao == "C" and r["destino"] not in ("cancelado",):
            if r["destino"] in ("aguardando", "ignorado", "terceirizado") or not r["pedido_id"]:
                # cancelada antes de virar pedido na fábrica: sai da caixa sozinha
                conn.execute("""UPDATE sac_vendas SET situacao='C', destino='cancelado', cancelado_em=?,
                                cancel_resolvido=1, decidido_por='SAC (cancelada)', decidido_em=?, atualizado_em=?
                                WHERE venda=?""", (_agora(), _agora(), _agora(), venda))
                mudou = "cancelada_antes"
            else:
                conn.execute("""UPDATE sac_vendas SET situacao='C', cancelado_em=?, cancel_resolvido=0, atualizado_em=?
                                WHERE venda=?""", (_agora(), _agora(), venda))
                mudou = "cancelada_com_pedido"
        else:
            conn.execute("UPDATE sac_vendas SET situacao=?, atualizado_em=? WHERE venda=?", (situacao, _agora(), venda))
            mudou = "situacao"
    if meta and meta.get("total") is not None:
        conn.execute("UPDATE sac_vendas SET total=? WHERE venda=?", (meta["total"], venda))
    conn.commit()
    return mudou


# ─── sugestão de produto (mesma ideia da vinculação automática por nome) ───────
def _palavras(s):
    return re.sub(r"[^A-Z0-9]", " ", (s or "").upper()).split()


def _parecida(a, b):
    """Mesma palavra com pequena diferença de grafia: ALTACOPOS ~ ALTACOPO, MLS ~ ML."""
    if a == b:
        return True
    if a.isdigit() or b.isdigit():
        return False
    curta, longa = sorted((a, b), key=len)
    return len(curta) >= 2 and longa.startswith(curta) and len(longa) - len(curta) <= 2


def _sugerir(produtos, descricao):
    dp = set(w for w in _palavras(descricao) if not w.isdigit())
    dn = set(re.findall(r"\d+", descricao or ""))
    melhor, nota = None, 0.0
    for p in produtos:
        txt = (p["nome"] or "") + " " + (p["marca"] or "")
        pp, pn = set(w for w in _palavras(txt) if not w.isdigit()), set(re.findall(r"\d+", txt))
        iguais = sum(1 for w in dp if any(_parecida(w, x) for x in pp))
        sc = iguais / max(len(dp), 1)
        if dn and pn and dn != pn and dn <= pn:
            sc -= 0.05          # tamanho extra no cadastro (ex.: 440 x 440/550): um pouco menos provável
        if dn and pn:
            sc += 0.4 if dn & pn else -0.3
        if sc > nota and sc >= 0.6:
            melhor, nota = p["id"], sc
    return melhor


def _montar(conn, r, depara, produtos, nomes_prod):
    try:
        dados = json.loads(r["dados_json"] or "{}")
    except ValueError:
        dados = {}
    itens = []
    pend = 0
    for it in dados.get("itens") or []:
        cod = str(it.get("codigo") or "")
        ch = chave_produto(it.get("descricao"))
        dp = depara.get(ch) if ch else None
        item = {"codigo": cod, "chave": ch, "descricao": it.get("descricao"), "quantidade": it.get("quantidade"),
                "unidade": it.get("unidade"), "valor_total": it.get("valor_total")}
        if dp and dp["terceirizado"]:
            item["vinculo"] = "terceirizado"
        elif dp and dp["produto_id"]:
            item["vinculo"] = "produto"
            item["produto_id"] = dp["produto_id"]
            item["produto_nome"] = nomes_prod.get(dp["produto_id"], f"Produto #{dp['produto_id']}")
        else:
            item["vinculo"] = None
            item["sugestao_id"] = _sugerir(produtos, ch or it.get("descricao"))
            if item["sugestao_id"]:
                item["sugestao_nome"] = nomes_prod.get(item["sugestao_id"])
            if ch:
                pend += 1
        itens.append(item)
    out = {k: r[k] for k in r.keys() if k not in ("dados_json",)}
    out["itens"] = itens
    out["itens_sem_vinculo"] = pend
    out["observacoes"] = dados.get("observacoes")
    out["documento"] = (dados.get("cliente") or {}).get("cnpj")
    if r["pedido_id"]:
        p = conn.execute("""SELECT p.id, p.status,
                                   (SELECT COUNT(*) FROM producao_diaria pd WHERE pd.pedido_numero = p.numero_pedido) AS lanc
                            FROM pedidos p WHERE p.id = ?""", (r["pedido_id"],)).fetchone()
        out["pedido"] = {"id": p["id"], "status": p["status"], "tem_producao": (p["lanc"] or 0) > 0} if p else None
    return out


def _sincronizar_com_pedidos(conn):
    """Venda aguardando cujo pedido já foi criado pela importação normal: passa para 'fábrica'."""
    conn.execute("""UPDATE sac_vendas SET destino='fabrica', decidido_por='já importado', decidido_em=?,
                        pedido_id=(SELECT id FROM pedidos WHERE numero_pedido = sac_vendas.venda)
                    WHERE destino='aguardando' AND EXISTS (SELECT 1 FROM pedidos WHERE numero_pedido = sac_vendas.venda)""",
                 (_agora(),))
    # pedido excluído no PRATIC: tira o vínculo
    conn.execute("""UPDATE sac_vendas SET pedido_id=NULL
                    WHERE pedido_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pedidos WHERE id = sac_vendas.pedido_id)""")
    conn.commit()


# ─── rotas ───────────────────────────────────────────────────────────────────
@router.get("/caixa")
def caixa(aba: str = "aguardando", current_user: dict = Depends(_so_gestor)):
    conn = get_conn()
    try:
        tabelas(conn)
        _sincronizar_com_pedidos(conn)
        cont = {d: 0 for d in DESTINOS}
        for x in conn.execute("SELECT destino, COUNT(*) n FROM sac_vendas GROUP BY destino"):
            cont[x["destino"]] = x["n"]
        cont["cancelados_pendentes"] = conn.execute(
            "SELECT COUNT(*) FROM sac_vendas WHERE situacao='C' AND cancel_resolvido=0 AND cancelado_em IS NOT NULL").fetchone()[0]
        if aba == "cancelados":
            rows = conn.execute("""SELECT * FROM sac_vendas WHERE cancelado_em IS NOT NULL
                                   ORDER BY cancel_resolvido, cancelado_em DESC LIMIT 200""").fetchall()
        else:
            if aba not in DESTINOS:
                aba = "aguardando"
            rows = conn.execute("""SELECT * FROM sac_vendas WHERE destino = ?
                                   ORDER BY CAST(venda AS INTEGER) DESC LIMIT 300""", (aba,)).fetchall()
        depara = {d["chave"]: d for d in conn.execute("SELECT * FROM sac_depara")}
        produtos = conn.execute("SELECT id, nome, marca FROM estoque_produtos WHERE ativo = 1").fetchall()
        nomes = {p["id"]: p["nome"] for p in produtos}
        vendas = [_montar(conn, r, depara, produtos, nomes) for r in rows]
        alertas = [_montar(conn, r, depara, produtos, nomes) for r in conn.execute(
            """SELECT * FROM sac_vendas WHERE situacao='C' AND cancel_resolvido=0 AND cancelado_em IS NOT NULL
               ORDER BY cancelado_em DESC""")]
    finally:
        conn.close()
    return {"aba": aba, "contagem": cont, "vendas": vendas, "cancelamentos": alertas, "robo": status_robo()}


@router.get("/resumo")
def resumo(current_user: dict = Depends(get_current_user)):
    """Contador do menu (só o gestor vê a página)."""
    if current_user.get("role") != "gestor":
        return {"aguardando": 0, "cancelados": 0}
    conn = get_conn()
    try:
        tabelas(conn)
        ag = conn.execute("SELECT COUNT(*) FROM sac_vendas WHERE destino='aguardando'").fetchone()[0]
        ca = conn.execute("SELECT COUNT(*) FROM sac_vendas WHERE situacao='C' AND cancel_resolvido=0 AND cancelado_em IS NOT NULL").fetchone()[0]
    finally:
        conn.close()
    return {"aguardando": ag, "cancelados": ca}


@router.post("/upload")
async def upload(files: List[UploadFile] = File(...), current_user: dict = Depends(_so_gestor)):
    """Envia PDFs de pedido do SAC para a caixa de entrada (enquanto o robô não lê sozinho)."""
    res = []
    conn = get_conn()
    try:
        for f in files:
            nome = f.filename or "pedido.pdf"
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(nome)[1].lower() or ".pdf") as t:
                    t.write(await f.read())
                    tmp = t.name
                res.append(registrar_pdf(conn, tmp, nome, origem="manual"))
            except Exception as e:
                conn.rollback()
                res.append({"status": "erro", "arquivo": nome, "motivo": str(e)})
            finally:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
    finally:
        conn.close()
    return {"resultados": res}


@router.get("/vendas/{venda}/pdf")
def pdf_venda(venda: str, current_user: dict = Depends(_so_gestor)):
    conn = get_conn()
    try:
        tabelas(conn)
        r = conn.execute("SELECT arquivo FROM sac_vendas WHERE venda=?", (venda,)).fetchone()
    finally:
        conn.close()
    if not r or not r["arquivo"]:
        raise HTTPException(404, "PDF não encontrado")
    caminho = os.path.join(_pasta_pdfs(), os.path.basename(r["arquivo"]))
    if not os.path.exists(caminho):
        raise HTTPException(404, "PDF não encontrado")
    return FileResponse(caminho, media_type="application/pdf", filename=f"venda_{venda}.pdf",
                        headers={"Content-Disposition": f'inline; filename="venda_{venda}.pdf"'})


class VinculoIn(BaseModel):
    chave: str
    codigo: Optional[str] = None
    produto_id: Optional[int] = None
    terceirizado: bool = False
    descricao: Optional[str] = None


def _gravar_vinculo(conn, v: VinculoIn, quem: str):
    ch = chave_produto(v.chave)
    if not ch:
        return
    if not v.terceirizado and not v.produto_id:
        conn.execute("DELETE FROM sac_depara WHERE chave=?", (ch,))
        return
    conn.execute("""INSERT INTO sac_depara (chave, codigo, descricao, produto_id, terceirizado, atualizado_por, atualizado_em)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(chave) DO UPDATE SET codigo=COALESCE(excluded.codigo, codigo),
                        descricao=COALESCE(excluded.descricao, descricao),
                        produto_id=excluded.produto_id, terceirizado=excluded.terceirizado,
                        atualizado_por=excluded.atualizado_por, atualizado_em=excluded.atualizado_em""",
                 (ch, v.codigo, v.descricao, None if v.terceirizado else v.produto_id, 1 if v.terceirizado else 0, quem, _agora()))


@router.get("/depara")
def listar_depara(current_user: dict = Depends(_so_gestor)):
    conn = get_conn()
    try:
        tabelas(conn)
        rows = conn.execute("""SELECT d.*, p.nome AS produto_nome FROM sac_depara d
                               LEFT JOIN estoque_produtos p ON p.id = d.produto_id ORDER BY d.chave""").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("/depara")
def salvar_depara(v: VinculoIn, current_user: dict = Depends(_so_gestor)):
    conn = get_conn()
    try:
        tabelas(conn)
        _gravar_vinculo(conn, v, current_user.get("nome"))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


class FabricaIn(BaseModel):
    vinculos: List[VinculoIn] = []


@router.post("/vendas/{venda}/fabrica")
async def enviar_fabrica(venda: str, body: FabricaIn, current_user: dict = Depends(_so_gestor)):
    """Cria o pedido no PRATIC (mesma importação de sempre) com os itens já ligados ao estoque
    pelo de-para. Itens marcados 'não é da fábrica' ficam de fora do pedido."""
    from rotas.pedidos import criar_pedido_de_arquivo, _auto_vincular_itens
    conn = get_conn()
    try:
        tabelas(conn)
        r = conn.execute("SELECT * FROM sac_vendas WHERE venda=?", (venda,)).fetchone()
        if not r:
            raise HTTPException(404, "Venda não encontrada")
        if r["destino"] == "fabrica" and r["pedido_id"]:
            return {"status": "ja_enviada", "pedido_id": r["pedido_id"]}
        if r["situacao"] == "C":
            raise HTTPException(400, "Esta venda está cancelada no SAC.")
        for v in body.vinculos:
            _gravar_vinculo(conn, v, current_user.get("nome"))
        dados = json.loads(r["dados_json"] or "{}")
        depara = {d["chave"]: d for d in conn.execute("SELECT * FROM sac_depara")}
        faltam = [it.get("descricao") for it in dados.get("itens") or []
                  if chave_produto(it.get("descricao")) and chave_produto(it.get("descricao")) not in depara]
        if faltam:
            conn.rollback()
            raise HTTPException(400, "Escolha o produto do estoque para: " + "; ".join(faltam[:5]))

        def resolver(it):
            d = depara.get(chave_produto(it.get("descricao")))
            if not d:
                return None
            return "pular" if d["terceirizado"] else d["produto_id"]
        caminho = os.path.join(_pasta_pdfs(), os.path.basename(r["arquivo"] or ""))
        res = await criar_pedido_de_arquivo(conn, caminho, f"venda_{venda}.pdf", current_user,
                                            resolver_item=resolver, parsed=dados)
        if res["status"] == "erro":
            conn.rollback()
            raise HTTPException(400, res.get("motivo") or "Não foi possível criar o pedido")
        pid = res.get("pedido_id")
        conn.execute("""UPDATE sac_vendas SET destino='fabrica', pedido_id=?, decidido_por=?, decidido_em=?, atualizado_em=?
                        WHERE venda=?""", (pid, current_user.get("nome"), _agora(), _agora(), venda))
        conn.commit()
        try:
            _auto_vincular_itens(conn)   # itens sem código (raro) ainda tentam pelo nome
            conn.commit()
        except Exception:
            conn.rollback()
    finally:
        conn.close()
    return {"status": res["status"], "pedido_id": pid, "qtd_itens": res.get("qtd_itens")}


class DestinoIn(BaseModel):
    destino: str


@router.post("/vendas/{venda}/destino")
def definir_destino(venda: str, body: DestinoIn, current_user: dict = Depends(_so_gestor)):
    """terceirizado | ignorado | aguardando (voltar para a caixa)."""
    if body.destino not in ("terceirizado", "ignorado", "aguardando"):
        raise HTTPException(400, "Destino inválido")
    conn = get_conn()
    try:
        tabelas(conn)
        r = conn.execute("SELECT destino, pedido_id FROM sac_vendas WHERE venda=?", (venda,)).fetchone()
        if not r:
            raise HTTPException(404, "Venda não encontrada")
        if r["destino"] == "fabrica" and r["pedido_id"]:
            raise HTTPException(400, "Esta venda já virou pedido na fábrica; para tirar, exclua o pedido.")
        conn.execute("UPDATE sac_vendas SET destino=?, decidido_por=?, decidido_em=?, atualizado_em=? WHERE venda=?",
                     (body.destino, current_user.get("nome"), _agora(), _agora(), venda))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


class CancelIn(BaseModel):
    acao: str   # 'excluido' (o pedido foi excluído) | 'mantido'


@router.post("/vendas/{venda}/cancelamento")
def resolver_cancelamento(venda: str, body: CancelIn, current_user: dict = Depends(_so_gestor)):
    conn = get_conn()
    try:
        tabelas(conn)
        _sincronizar_com_pedidos(conn)
        r = conn.execute("SELECT pedido_id FROM sac_vendas WHERE venda=?", (venda,)).fetchone()
        if not r:
            raise HTTPException(404, "Venda não encontrada")
        if body.acao == "excluido":
            if r["pedido_id"]:
                raise HTTPException(400, "O pedido ainda existe no PRATIC.")
            conn.execute("""UPDATE sac_vendas SET destino='cancelado', cancel_resolvido=1, decidido_por=?, decidido_em=?
                            WHERE venda=?""", (current_user.get("nome"), _agora(), venda))
        else:
            conn.execute("UPDATE sac_vendas SET cancel_resolvido=1, decidido_por=?, decidido_em=? WHERE venda=?",
                         (current_user.get("nome") + " (mantido)", _agora(), venda))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# ─── robô (leitura automática do SAC) ─────────────────────────────────────────
# A leitura automática fica em rotas/sac_robo.py e precisa do login do SAC nas variáveis
# SAC_USUARIO / SAC_SENHA do Coolify. Aqui só as configurações e o status.
def status_robo() -> dict:
    conn = get_conn()
    try:
        cfg = {r["chave"]: r["valor"] for r in conn.execute(
            "SELECT chave, valor FROM configuracoes WHERE chave LIKE 'sac_%'")}
    finally:
        conn.close()
    configurado = bool((os.environ.get("SAC_USUARIO") or "").strip() and (os.environ.get("SAC_SENHA") or "").strip())
    desligado, automatico, resumo = "", False, None
    try:
        from rotas import sac_robo
        disponivel = getattr(sac_robo, "DISPONIVEL", False)
        desligado = sac_robo.motivo_desligado()
        automatico = sac_robo.automatico()
    except Exception:
        disponivel = False
    try:
        resumo = json.loads(cfg.get("sac_ultimo_resumo") or "null")
    except ValueError:
        resumo = None
    return {"configurado": configurado, "disponivel": disponivel, "desligado": desligado, "automatico": automatico,
            "importar_desde": cfg.get("sac_importar_desde") or datetime.date.today().isoformat(),
            "ultima_leitura": cfg.get("sac_ultima_leitura"), "ultimo_erro": cfg.get("sac_ultimo_erro"),
            "ultimo_resumo": resumo, "intervalo_min": 15}


class ConfigIn(BaseModel):
    importar_desde: str


@router.post("/config")
def salvar_config(body: ConfigIn, current_user: dict = Depends(_so_gestor)):
    try:
        datetime.date.fromisoformat(body.importar_desde)
    except ValueError:
        raise HTTPException(400, "Data inválida")
    conn = get_conn()
    try:
        conn.execute("""INSERT INTO configuracoes (chave, valor, descricao) VALUES ('sac_importar_desde', ?, 'Pedidos SAC: importar vendas a partir desta data')
                        ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor""", (body.importar_desde,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/sincronizar")
async def sincronizar_agora(current_user: dict = Depends(_so_gestor)):
    st = status_robo()
    if not st["disponivel"]:
        raise HTTPException(400, "A leitura automática do SAC ainda está sendo preparada. Por enquanto, envie os PDFs pelo botão “Enviar PDFs do SAC”.")
    if st["desligado"]:
        raise HTTPException(400, st["desligado"])
    if not st["configurado"]:
        raise HTTPException(400, "Falta o login do SAC nas variáveis SAC_USUARIO e SAC_SENHA do Coolify.")
    from rotas import sac_robo
    r = await sac_robo.sincronizar("manual")
    if not r.get("ok"):
        raise HTTPException(400, r.get("mensagem") or "Não consegui ler o SAC.")
    return r


@router.on_event("startup")
async def _iniciar_robo():
    try:
        from rotas import sac_robo
        sac_robo.iniciar()
    except Exception as e:  # o sistema sobe mesmo se o robô falhar
        print("[sac] robô não iniciou:", e)
