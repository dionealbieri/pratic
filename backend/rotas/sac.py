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


# Permissão "Pedidos SAC" (Controle de Acesso), para liberar a caixa a outros usuários:
#   ver     -> caixa, vendas e PDFs
#   buscar  -> + buscar venda pelo número / enviar PDFs / sincronizar agora
#   decidir -> + enviar à fábrica, terceirizado, ignorar e escolher o produto (de-para)
# Só o gestor: configurações do robô, preencher de-para pelo histórico e cancelamentos.
def perms_sac(u: dict) -> set:
    if u.get("role") == "gestor":
        return {"ver", "buscar", "decidir"}
    conn = get_conn()
    try:
        rows = conn.execute("""SELECT acao FROM usuario_permissoes
                               WHERE usuario_id=? AND modulo='pedidos_sac' AND permitido=1""", (u.get("id"),)).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    acoes = {r["acao"] for r in rows}
    if acoes:
        acoes.add("ver")
    return acoes


def _exigir_sac(acao: str):
    def dep(current_user: dict = Depends(get_current_user)):
        if acao not in perms_sac(current_user):
            raise HTTPException(403, "Pedidos SAC: sem permissão para esta ação (Controle de Acesso).")
        return current_user
    return dep


_sac_ver = _exigir_sac("ver")
_sac_buscar = _exigir_sac("buscar")
_sac_decidir = _exigir_sac("decidir")


def _agora() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pasta_pdfs() -> str:
    p = os.path.join(os.path.dirname(os.path.abspath(_database.DB_PATH)), "sac_pdfs")
    os.makedirs(p, exist_ok=True)
    return p


def _encurtar_itens_ja_criados(conn):
    """Uma vez só: pedidos criados pela caixa SAC antes desta versão ficaram com o texto enorme da arte."""
    try:
        if conn.execute("SELECT 1 FROM configuracoes WHERE chave='sac_itens_curtos_v1'").fetchone():
            return
        if not conn.execute("SELECT name FROM sqlite_master WHERE name='sac_vendas'").fetchone():
            conn.execute("INSERT OR IGNORE INTO configuracoes (chave, valor, descricao) VALUES ('sac_itens_curtos_v1','1','')")
            return
        conn.execute("""UPDATE pedidos_itens SET descricao = (SELECT nome FROM estoque_produtos ep WHERE ep.id = pedidos_itens.produto_id)
                        WHERE produto_id IS NOT NULL
                          AND pedido_id IN (SELECT pedido_id FROM sac_vendas WHERE pedido_id IS NOT NULL
                                              AND destino='fabrica' AND COALESCE(decidido_por,'') <> 'já importado')
                          AND EXISTS (SELECT 1 FROM estoque_produtos ep WHERE ep.id = pedidos_itens.produto_id)""")
        conn.execute("INSERT OR IGNORE INTO configuracoes (chave, valor, descricao) VALUES ('sac_itens_curtos_v1','1','Pedidos SAC: itens com nome do estoque')")
        conn.commit()
    except Exception as e:
        print("[sac] encurtar itens:", e)


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
    _encurtar_itens_ja_criados(conn)
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


def _historico(conn, ativos: set) -> dict:
    """O que os pedidos já importados ensinam: chave do produto -> produto do estoque mais usado.
    Só vale como SUGESTÃO (o gestor confirma), e só quando um produto domina (>= 70% das vezes)."""
    cont = {}
    for row in conn.execute("SELECT descricao, produto_id FROM pedidos_itens WHERE produto_id IS NOT NULL"):
        ch = chave_produto(row["descricao"])
        if ch and row["produto_id"] in ativos:
            c = cont.setdefault(ch, {})
            c[row["produto_id"]] = c.get(row["produto_id"], 0) + 1
    hist = {}
    for ch, c in cont.items():
        pid, n = max(c.items(), key=lambda x: x[1])
        if n / sum(c.values()) >= 0.7:
            hist[ch] = pid
    return hist


def _itens_do_pedido(conn, pedido_id):
    return conn.execute("""SELECT i.descricao, i.produto_id, ep.nome AS produto_nome FROM pedidos_itens i
                           LEFT JOIN estoque_produtos ep ON ep.id = i.produto_id
                           WHERE i.pedido_id = ? ORDER BY i.id""", (pedido_id,)).fetchall()


def _montar(conn, r, depara, produtos, nomes_prod, hist=None):
    try:
        dados = json.loads(r["dados_json"] or "{}")
    except ValueError:
        dados = {}
    itens = []
    pend = 0
    hist = hist or {}
    # venda que já virou pedido: mostra o produto que está no pedido de verdade
    no_pedido = {}
    if r["pedido_id"]:
        for pi in _itens_do_pedido(conn, r["pedido_id"]):
            if pi["produto_id"]:
                no_pedido.setdefault(chave_produto(pi["descricao"]), (pi["produto_id"], pi["produto_nome"]))
                no_pedido.setdefault("#" + str(pi["descricao"] or "").strip().upper(), (pi["produto_id"], pi["produto_nome"]))
    for it in dados.get("itens") or []:
        cod = str(it.get("codigo") or "")
        ch = chave_produto(it.get("descricao"))
        dp = depara.get(ch) if ch else None
        item = {"codigo": cod, "chave": ch, "descricao": it.get("descricao"), "quantidade": it.get("quantidade"),
                "unidade": it.get("unidade"), "valor_total": it.get("valor_total")}
        ped = no_pedido.get("#" + str(it.get("descricao") or "").strip().upper()) or no_pedido.get(ch)
        if r["pedido_id"] and ped:
            item["vinculo"] = "produto"
            item["produto_id"], item["produto_nome"] = ped
            item["do_pedido"] = True
        elif r["pedido_id"] and not dp:
            item["vinculo"] = "pedido_sem_produto"
        elif dp and dp["terceirizado"]:
            item["vinculo"] = "terceirizado"
        elif dp and dp["produto_id"]:
            item["vinculo"] = "produto"
            item["produto_id"] = dp["produto_id"]
            item["produto_nome"] = nomes_prod.get(dp["produto_id"], f"Produto #{dp['produto_id']}")
        else:
            item["vinculo"] = None
            item["sugestao_id"] = hist.get(ch) or _sugerir(produtos, ch or it.get("descricao"))
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
# Abas de histórico (fábrica, terceirizados, ignorados, cancelados) mostram só um período,
# senão a contagem e a lista crescem sem parar. "Aguardando" e cancelamentos pendentes
# são o que precisa de ação: esses contam sempre tudo.
PERIODOS = (7, 30, 90, 0)          # dias; 0 = tudo
_DATA_DECISAO = "COALESCE(decidido_em, atualizado_em, criado_em)"


@router.get("/caixa")
def caixa(aba: str = "aguardando", periodo: int = 7, busca: str = "",
          current_user: dict = Depends(_sac_ver)):
    if periodo not in PERIODOS:
        periodo = 7
    busca = (busca or "").strip()
    conn = get_conn()
    try:
        tabelas(conn)
        _sincronizar_com_pedidos(conn)
        filtro, params = "", []
        if busca:
            filtro = " AND (venda LIKE ? OR cliente LIKE ? OR CAST(pedido_id AS TEXT) = ?)"
            params = [f"%{busca}%", f"%{busca}%", busca]
        elif periodo:
            desde = (datetime.datetime.now() - datetime.timedelta(days=periodo)).strftime("%Y-%m-%d 00:00:00")
            filtro = f" AND {_DATA_DECISAO} >= ?"
            params = [desde]
        cont = {d: 0 for d in DESTINOS}
        cont["aguardando"] = conn.execute("SELECT COUNT(*) FROM sac_vendas WHERE destino='aguardando'").fetchone()[0]
        for x in conn.execute(f"""SELECT destino, COUNT(*) n FROM sac_vendas WHERE destino <> 'aguardando' {filtro}
                                  GROUP BY destino""", params):
            cont[x["destino"]] = x["n"]
        cont["cancelados_pendentes"] = conn.execute(
            "SELECT COUNT(*) FROM sac_vendas WHERE situacao='C' AND cancel_resolvido=0 AND cancelado_em IS NOT NULL").fetchone()[0]
        if aba == "cancelados":
            filtro_c = filtro.replace(_DATA_DECISAO, "cancelado_em")
            rows = conn.execute(f"""SELECT * FROM sac_vendas WHERE cancelado_em IS NOT NULL
                                    AND (cancel_resolvido = 0 OR (1=1 {filtro_c}))
                                    ORDER BY cancel_resolvido, cancelado_em DESC LIMIT 200""", params).fetchall()
        else:
            if aba not in DESTINOS:
                aba = "aguardando"
            if aba == "aguardando":
                rows = conn.execute("""SELECT * FROM sac_vendas WHERE destino = 'aguardando'
                                       ORDER BY CAST(venda AS INTEGER) DESC LIMIT 300""").fetchall()
            else:
                rows = conn.execute(f"""SELECT * FROM sac_vendas WHERE destino = ? {filtro}
                                        ORDER BY {_DATA_DECISAO} DESC, CAST(venda AS INTEGER) DESC LIMIT 200""",
                                    [aba] + params).fetchall()
        depara = {d["chave"]: d for d in conn.execute("SELECT * FROM sac_depara")}
        produtos = conn.execute("SELECT id, nome, marca FROM estoque_produtos WHERE ativo = 1").fetchall()
        nomes = {p["id"]: p["nome"] for p in produtos}
        hist = _historico(conn, set(nomes)) if aba == "aguardando" else {}
        vendas = [_montar(conn, r, depara, produtos, nomes, hist) for r in rows]
        alertas = [_montar(conn, r, depara, produtos, nomes) for r in conn.execute(
            """SELECT * FROM sac_vendas WHERE situacao='C' AND cancel_resolvido=0 AND cancelado_em IS NOT NULL
               ORDER BY cancelado_em DESC""")]
    finally:
        conn.close()
    return {"aba": aba, "contagem": cont, "vendas": vendas, "cancelamentos": alertas, "robo": status_robo(),
            "periodo": periodo, "busca": busca, "permissoes": sorted(perms_sac(current_user)),
            "gestor": current_user.get("role") == "gestor"}


@router.get("/resumo")
def resumo(current_user: dict = Depends(get_current_user)):
    """Contador do menu (só o gestor vê a página)."""
    if "ver" not in perms_sac(current_user):
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
async def upload(files: List[UploadFile] = File(...), current_user: dict = Depends(_sac_buscar)):
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
                rr = registrar_pdf(conn, tmp, nome, origem="manual")
                if rr.get("status") == "registrada" and rr.get("venda"):
                    auto = await decidir_automatico(conn, str(rr["venda"]))
                    if auto:
                        rr["automatico"] = auto
                res.append(rr)
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
def pdf_venda(venda: str, current_user: dict = Depends(_sac_ver)):
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
def listar_depara(current_user: dict = Depends(_sac_ver)):
    conn = get_conn()
    try:
        tabelas(conn)
        rows = conn.execute("""SELECT d.*, p.nome AS produto_nome FROM sac_depara d
                               LEFT JOIN estoque_produtos p ON p.id = d.produto_id ORDER BY d.chave""").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _sugestoes_historico(conn) -> list:
    """Vínculos seguros tirados dos pedidos já feitos: o mesmo produto do SAC ligado
    pelo menos 2 vezes, e SEMPRE ao mesmo produto do estoque (ativo). Só o que ainda não está no de-para."""
    ativos = {r["id"]: r["nome"] for r in conn.execute("SELECT id, nome FROM estoque_produtos WHERE ativo = 1")}
    ja = {r["chave"] for r in conn.execute("SELECT chave FROM sac_depara")}
    cont, exemplo = {}, {}
    for row in conn.execute("SELECT descricao, produto_id FROM pedidos_itens WHERE produto_id IS NOT NULL"):
        ch = chave_produto(row["descricao"])
        if not ch or ch in ja:
            continue
        cont.setdefault(ch, {}).setdefault(row["produto_id"], 0)
        cont[ch][row["produto_id"]] += 1
        exemplo.setdefault(ch, row["descricao"])
    out = []
    for ch, c in cont.items():
        if len(c) != 1:
            continue                       # já foi ligado a produtos diferentes: fica para o gestor
        pid, n = next(iter(c.items()))
        if n < 2 or pid not in ativos:
            continue
        out.append({"chave": ch, "produto_id": pid, "produto_nome": ativos[pid], "vezes": n,
                    "exemplo": (exemplo.get(ch) or "")[:120]})
    return sorted(out, key=lambda x: (-x["vezes"], x["chave"]))


@router.get("/depara/historico")
def depara_historico(current_user: dict = Depends(_so_gestor)):
    conn = get_conn()
    try:
        tabelas(conn)
        return {"sugestoes": _sugestoes_historico(conn)}
    finally:
        conn.close()


class AplicarHistIn(BaseModel):
    chaves: List[str]


@router.post("/depara/historico")
async def aplicar_depara_historico(body: AplicarHistIn, current_user: dict = Depends(_so_gestor)):
    """Grava os vínculos do histórico que o gestor confirmou e libera as vendas que só esperavam por eles."""
    conn = get_conn()
    enviadas = 0
    try:
        tabelas(conn)
        sug = {s["chave"]: s for s in _sugestoes_historico(conn)}
        n = 0
        for ch in body.chaves:
            sgt = sug.get(ch)
            if not sgt:
                continue
            _gravar_vinculo(conn, VinculoIn(chave=ch, descricao=sgt["exemplo"], produto_id=sgt["produto_id"],
                                            terceirizado=False), (current_user.get("nome") or "") + " (histórico)")
            n += 1
        conn.commit()
        for o in conn.execute("SELECT venda FROM sac_vendas WHERE destino='aguardando'").fetchall():
            if await decidir_automatico(conn, o["venda"]) == "fabrica":
                enviadas += 1
    finally:
        conn.close()
    return {"gravados": n, "enviadas": enviadas,
            "mensagem": f"{n} vínculo(s) gravado(s)" + (f" · {enviadas} venda(s) seguiram para a fábrica" if enviadas else "")}


@router.post("/depara")
def salvar_depara(v: VinculoIn, current_user: dict = Depends(_sac_decidir)):
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


class ErroFabrica(Exception):
    pass


async def _criar_na_fabrica(conn, r, current_user: dict, quem: str) -> dict:
    """Cria o pedido da venda com os itens ligados pelo de-para (itens 'não é da fábrica' ficam de fora).
    Não faz commit. Levanta ErroFabrica se falta vínculo ou se a importação falhar."""
    from rotas.pedidos import criar_pedido_de_arquivo
    venda = r["venda"]
    dados = json.loads(r["dados_json"] or "{}")
    depara = {d["chave"]: d for d in conn.execute("SELECT * FROM sac_depara")}
    faltam = [it.get("descricao") for it in dados.get("itens") or []
              if chave_produto(it.get("descricao")) and chave_produto(it.get("descricao")) not in depara]
    if faltam:
        raise ErroFabrica("Escolha o produto do estoque para: " + "; ".join(faltam[:5]))
    nomes_est = {x["id"]: x["nome"] for x in conn.execute("SELECT id, nome FROM estoque_produtos")}

    def resolver(it):
        d = depara.get(chave_produto(it.get("descricao")))
        if not d:
            return None
        if d["terceirizado"]:
            return "pular"
        # no pedido vai o nome limpo do estoque (o texto da arte continua no PDF e nas observações)
        return (d["produto_id"], nomes_est.get(d["produto_id"]))
    caminho = os.path.join(_pasta_pdfs(), os.path.basename(r["arquivo"] or ""))
    res = await criar_pedido_de_arquivo(conn, caminho, f"venda_{venda}.pdf", current_user,
                                        resolver_item=resolver, parsed=dados)
    if res["status"] == "erro":
        raise ErroFabrica(res.get("motivo") or "Não foi possível criar o pedido")
    pid = res.get("pedido_id")
    # o item ganhou o nome limpo do estoque; os detalhes de arte/cor vão para as observações do pedido
    detalhes = []
    for it in dados.get("itens") or []:
        if resolver(it) == "pular":
            continue
        desc = str(it.get("descricao") or "").strip()
        base = chave_produto(desc)
        if desc and len(re.sub(r"[^A-Z0-9]", "", desc.upper())) > len(re.sub(r"[^A-Z0-9]", "", base)) + 8:
            q = it.get("quantidade")
            qtxt = (f"{q:,.0f}".replace(",", ".") + " un · ") if isinstance(q, (int, float)) else ""
            detalhes.append(f"• {qtxt}{desc}")
    if pid and detalhes:
        obs_atual = (conn.execute("SELECT observacoes FROM pedidos WHERE id=?", (pid,)).fetchone() or {"observacoes": ""})["observacoes"] or ""
        novo = (obs_atual.rstrip() + "\n\n" if obs_atual.strip() else "") + "Detalhes dos itens (SAC):\n" + "\n".join(detalhes)
        conn.execute("UPDATE pedidos SET observacoes=? WHERE id=?", (novo, pid))
    conn.execute("""UPDATE sac_vendas SET destino='fabrica', pedido_id=?, decidido_por=?, decidido_em=?, atualizado_em=?
                    WHERE venda=?""", (pid, quem, _agora(), _agora(), venda))
    return res


def auto_fabrica_ligado(conn) -> bool:
    r = conn.execute("SELECT valor FROM configuracoes WHERE chave='sac_auto_fabrica'").fetchone()
    return (r["valor"] if r else "1") != "0"


async def decidir_automatico(conn, venda: str) -> str:
    """Venda nova cujos itens JÁ têm vínculo confirmado no de-para não espera o gestor:
    - todos os itens ligados a produto da fábrica (ou parte 'não é da fábrica') -> cria o pedido;
    - todos os itens marcados 'não é da fábrica' -> vai para Terceirizados.
    Item sem vínculo (produto novo) -> continua em Aguardando decisão. Faz commit."""
    if not auto_fabrica_ligado(conn):
        return ""
    r = conn.execute("SELECT * FROM sac_vendas WHERE venda=?", (venda,)).fetchone()
    if not r or r["destino"] != "aguardando" or r["pedido_id"] or (r["situacao"] or "A") != "A":
        return ""
    dados = json.loads(r["dados_json"] or "{}")
    itens = [it for it in dados.get("itens") or [] if chave_produto(it.get("descricao"))]
    if not itens:
        return ""
    depara = {d["chave"]: d for d in conn.execute("SELECT * FROM sac_depara")}
    ds = [depara.get(chave_produto(it.get("descricao"))) for it in itens]
    if any(d is None for d in ds):
        return ""
    if all(d["terceirizado"] for d in ds):
        conn.execute("""UPDATE sac_vendas SET destino='terceirizado', decidido_por='automático', decidido_em=?, atualizado_em=?
                        WHERE venda=?""", (_agora(), _agora(), venda))
        conn.commit()
        return "terceirizado"
    try:
        await _criar_na_fabrica(conn, r, {"id": None, "nome": "Pedidos SAC (automático)", "role": "gestor"}, "automático")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[sac] venda {venda} não foi automática para a fábrica:", e)
        return ""
    try:
        from rotas.pedidos import _auto_vincular_itens
        _auto_vincular_itens(conn)
        conn.commit()
    except Exception:
        conn.rollback()
    return "fabrica"


@router.post("/vendas/{venda}/fabrica")
async def enviar_fabrica(venda: str, body: FabricaIn, current_user: dict = Depends(_sac_decidir)):
    """Cria o pedido no PRATIC (mesma importação de sempre) com os itens já ligados ao estoque
    pelo de-para. Itens marcados 'não é da fábrica' ficam de fora do pedido."""
    from rotas.pedidos import _auto_vincular_itens
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
        try:
            res = await _criar_na_fabrica(conn, r, current_user, current_user.get("nome"))
        except ErroFabrica as e:
            conn.rollback()
            raise HTTPException(400, str(e))
        pid = res.get("pedido_id")
        conn.commit()
        try:
            _auto_vincular_itens(conn)   # itens sem código (raro) ainda tentam pelo nome
            conn.commit()
        except Exception:
            conn.rollback()
        # outras vendas que esperavam só por estes vínculos seguem sozinhas
        for o in conn.execute("SELECT venda FROM sac_vendas WHERE destino='aguardando'").fetchall():
            await decidir_automatico(conn, o["venda"])
    finally:
        conn.close()
    return {"status": res["status"], "pedido_id": pid, "qtd_itens": res.get("qtd_itens")}


class DestinoIn(BaseModel):
    destino: str


@router.post("/vendas/{venda}/destino")
def definir_destino(venda: str, body: DestinoIn, current_user: dict = Depends(_sac_decidir)):
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
            "ultimo_resumo": resumo, "intervalo_min": 15,
            "auto_fabrica": (cfg.get("sac_auto_fabrica") or "1") != "0"}


class ConfigIn(BaseModel):
    importar_desde: Optional[str] = None
    auto_fabrica: Optional[bool] = None


@router.post("/config")
async def salvar_config(body: ConfigIn, current_user: dict = Depends(_so_gestor)):
    if body.importar_desde is not None:
        try:
            datetime.date.fromisoformat(body.importar_desde)
        except ValueError:
            raise HTTPException(400, "Data inválida")
    conn = get_conn()
    enviadas = 0
    try:
        if body.importar_desde is not None:
            conn.execute("""INSERT INTO configuracoes (chave, valor, descricao) VALUES ('sac_importar_desde', ?, 'Pedidos SAC: importar vendas a partir desta data')
                            ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor""", (body.importar_desde,))
        if body.auto_fabrica is not None:
            conn.execute("""INSERT INTO configuracoes (chave, valor, descricao) VALUES ('sac_auto_fabrica', ?, 'Pedidos SAC: venda com todos os produtos vinculados vai direto para a fábrica')
                            ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor""", ("1" if body.auto_fabrica else "0",))
        conn.commit()
        if body.auto_fabrica:
            tabelas(conn)
            for o in conn.execute("SELECT venda FROM sac_vendas WHERE destino='aguardando'").fetchall():
                if await decidir_automatico(conn, o["venda"]) == "fabrica":
                    enviadas += 1
    finally:
        conn.close()
    return {"ok": True, "enviadas": enviadas}


@router.post("/sincronizar")
async def sincronizar_agora(current_user: dict = Depends(_sac_buscar)):
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


class BuscarIn(BaseModel):
    vendas: str      # "15811, 15812 15813"


@router.post("/buscar")
async def buscar_vendas(body: BuscarIn, current_user: dict = Depends(_sac_buscar)):
    """Importa vendas do SAC pelo número, na hora (não espera o robô nem a data inicial)."""
    nums = []
    for x in re.split(r"[\s,;]+", body.vendas or ""):
        x = re.sub(r"\D", "", x)
        if x and x not in nums:
            nums.append(x)
    if not nums:
        raise HTTPException(400, "Digite o número da venda do SAC.")
    if len(nums) > 20:
        raise HTTPException(400, "No máximo 20 vendas por vez.")
    from rotas import sac_robo
    r = await sac_robo.importar_numeros(nums)
    if not r.get("ok") and not r.get("resultados"):
        raise HTTPException(400, r.get("mensagem") or "Não consegui buscar no SAC.")
    return r


@router.on_event("startup")
async def _iniciar_robo():
    try:
        from rotas import sac_robo
        sac_robo.iniciar()
    except Exception as e:  # o sistema sobe mesmo se o robô falhar
        print("[sac] robô não iniciou:", e)
