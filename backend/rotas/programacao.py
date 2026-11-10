"""Programação da Produção — etapa 1: chave geral, permissões e os campos novos do pedido
(informações para a produção, arte do verso da ficha e pagamento).

Regra da fase de TESTE: enquanto `programacao_liberada` = 0, só o GESTOR vê e usa
qualquer coisa daqui. Os setores continuam exatamente como estavam.
Depois de liberada:
  • tela de Programação: perfis com a página 'programacao' marcada no Controle de Acesso;
  • informações para a produção e arte: o vendedor do pedido ou quem edita pedidos;
  • pagamento: o vendedor do pedido (e o gestor) — nunca sai na ficha da produção.
"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

import database as _database
from database import get_conn
from auth_utils import get_current_user
from rotas.pedidos import verificar_permissao

router = APIRouter()

EXT_ARTE = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_ARTE = 25 * 1024 * 1024
CONDICOES_PAG = ("a_vista", "entrada_restante", "a_prazo", "pago_total", "outro")


# ─── utilidades ──────────────────────────────────────────────────────────────

def _cfg(conn, chave: str, padrao: str) -> str:
    r = conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
    return (r["valor"] if r and r["valor"] is not None else padrao)


def _int_cfg(conn, chave: str, padrao: int) -> int:
    try:
        return max(0, int(float(_cfg(conn, chave, str(padrao)))))
    except (TypeError, ValueError):
        return padrao


def _liberada(conn) -> bool:
    return _cfg(conn, "programacao_liberada", "0") == "1"


def _paginas_perfil(conn, role: str) -> list:
    r = conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (f"perm_{role}",)).fetchone()
    return [p.strip() for p in ((r["valor"] if r else "") or "").split(",") if p.strip()]


def _eh_gestor(u) -> bool:
    return (u or {}).get("role") == "gestor"


def _nome(u) -> str:
    return (u or {}).get("nome") or (u or {}).get("username") or "sistema"


def _pode_ver_programacao(conn, u) -> bool:
    if _eh_gestor(u):
        return True
    return _liberada(conn) and "programacao" in _paginas_perfil(conn, u.get("role") or "")


def _pode_info(conn, u, ped) -> bool:
    """Informações para a produção e arte."""
    if _eh_gestor(u):
        return True
    if not _liberada(conn):
        return False
    if u.get("role") == "comercial":
        return ped["vendedor_usuario_id"] == u.get("id")
    return verificar_permissao("pedidos", "editar", u)


def _pode_pagamento(conn, u, ped) -> bool:
    if _eh_gestor(u):
        return True
    return _liberada(conn) and u.get("role") == "comercial" and ped["vendedor_usuario_id"] == u.get("id")


def _pasta_artes() -> str:
    pasta = os.path.join(os.path.dirname(os.path.abspath(_database.DB_PATH)), "pedidos_artes")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _apagar(nome: Optional[str]):
    if not nome:
        return
    try:
        os.remove(os.path.join(_pasta_artes(), os.path.basename(nome)))
    except OSError:
        pass


def _gerar_previa_pdf(caminho_pdf: str) -> Optional[str]:
    """Primeira página do PDF da arte vira PNG, para sair impressa no verso da ficha.
    Sem a biblioteca (ou PDF com problema) segue sem prévia: o PDF continua guardado."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(caminho_pdf)
        try:
            pagina = pdf[0]
            largura = pagina.get_width() or 595
            escala = max(1.0, min(3.0, 1600.0 / float(largura)))
            img = pagina.render(scale=escala).to_pil()
        finally:
            pdf.close()
        nome = f"{uuid.uuid4().hex}_previa.png"
        img.save(os.path.join(_pasta_artes(), nome), "PNG", optimize=True)
        return nome
    except Exception:
        return None


def _pedido(conn, pid: int):
    ped = conn.execute("SELECT * FROM pedidos WHERE id=?", (pid,)).fetchone()
    if not ped:
        raise HTTPException(404, "Pedido não encontrado")
    return ped


# ─── status / chave geral ────────────────────────────────────────────────────

@router.get("/status")
def status(current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        return {
            "liberada": _liberada(conn),
            "gestor": _eh_gestor(current_user),
            "pode_ver": _pode_ver_programacao(conn, current_user),
            # campos novos do pedido aparecem para quem não é gestor só depois de liberar
            "campos_pedido": _eh_gestor(current_user) or _liberada(conn),
            "urgencia_dias": _int_cfg(conn, "urgencia_dias", 3),
            "prioridade_limite": _int_cfg(conn, "prioridade_limite", 3),
        }
    finally:
        conn.close()


# ─── informações do pedido para a produção ───────────────────────────────────

@router.get("/pedido/{pid}")
def dados_pedido(pid: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if current_user.get("role") == "comercial" and ped["vendedor_usuario_id"] != current_user.get("id"):
            raise HTTPException(403, "Pedido de outro vendedor")
        if not (_eh_gestor(current_user) or _liberada(conn)):
            raise HTTPException(403, "Programação da Produção ainda em teste (só o gestor).")
        out = {
            "pedido_id": pid,
            "numero_pedido": ped["numero_pedido"],
            "pode_editar_info": _pode_info(conn, current_user, ped),
            "pode_pagamento": _pode_pagamento(conn, current_user, ped),
            "info": {
                "cor_impressao": ped["info_cor_impressao"], "marca": ped["info_marca"],
                "arte_modo": ped["info_arte_modo"], "arte_ref": ped["info_arte_ref"],
                "observacao": ped["info_observacao"],
                "atualizado_por": ped["info_atualizado_por"], "atualizado_em": ped["info_atualizado_em"],
            },
            "arte": ({"nome": ped["arte_arquivo_nome"], "tem_previa": bool(ped["arte_previa"]),
                      "eh_pdf": (ped["arte_arquivo"] or "").lower().endswith(".pdf")}
                     if ped["arte_arquivo"] else None),
            "prioridade": {"status": ped["prioridade_status"], "motivo": ped["prioridade_motivo"],
                           "obs_gestor": ped["prioridade_obs_gestor"], "decidida_por": ped["prioridade_decidida_por"]},
            "status": ped["status"],
        }
        if out["pode_pagamento"]:
            out["pagamento"] = {"condicao": ped["pag_condicao"], "valor_pago": ped["pag_valor_pago"],
                                "data": ped["pag_data"], "observacao": ped["pag_observacao"],
                                "valor_total": ped["valor_total"] if "valor_total" in ped.keys() else None}
        return out
    finally:
        conn.close()


class InfoIn(BaseModel):
    cor_impressao: Optional[str] = None
    marca: Optional[str] = None
    arte_modo: Optional[str] = None      # 'nova' | 'igual' | 'sem'
    arte_ref: Optional[str] = None       # nº do pedido anterior quando 'igual'
    observacao: Optional[str] = None


def _limpo(v, tam=500):
    v = (v or "").strip()
    return v[:tam] or None


@router.put("/pedido/{pid}/info")
def salvar_info(pid: int, body: InfoIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if not _pode_info(conn, current_user, ped):
            raise HTTPException(403, "Sem permissão para alterar as informações deste pedido.")
        modo = (body.arte_modo or "").strip().lower() or None
        if modo and modo not in ("nova", "igual", "sem"):
            raise HTTPException(400, "Arte inválida")
        conn.execute("""UPDATE pedidos SET info_cor_impressao=?, info_marca=?, info_arte_modo=?, info_arte_ref=?,
                        info_observacao=?, info_atualizado_por=?, info_atualizado_em=datetime('now','localtime')
                        WHERE id=?""",
                     (_limpo(body.cor_impressao, 60), _limpo(body.marca, 80), modo,
                      _limpo(body.arte_ref, 30) if modo == "igual" else None,
                      _limpo(body.observacao, 2000), _nome(current_user), pid))
        conn.commit()
        return {"mensagem": "Informações para a produção salvas"}
    finally:
        conn.close()


class PagamentoIn(BaseModel):
    condicao: Optional[str] = None
    valor_pago: Optional[float] = None
    data: Optional[str] = None
    observacao: Optional[str] = None


@router.put("/pedido/{pid}/pagamento")
def salvar_pagamento(pid: int, body: PagamentoIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if not _pode_pagamento(conn, current_user, ped):
            raise HTTPException(403, "Sem permissão para o pagamento deste pedido.")
        cond = (body.condicao or "").strip() or None
        if cond and cond not in CONDICOES_PAG:
            raise HTTPException(400, "Condição de pagamento inválida")
        if body.valor_pago is not None and body.valor_pago < 0:
            raise HTTPException(400, "Valor pago não pode ser negativo")
        data = (body.data or "").strip() or None
        if data:
            try:
                datetime.strptime(data[:10], "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "Data do pagamento inválida")
        conn.execute("UPDATE pedidos SET pag_condicao=?, pag_valor_pago=?, pag_data=?, pag_observacao=? WHERE id=?",
                     (cond, body.valor_pago, data[:10] if data else None, _limpo(body.observacao, 1000), pid))
        conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao)
                        VALUES (?, 'pagamento_pedido', 'pedido', ?, ?)""",
                     (_nome(current_user), pid,
                      f"Pagamento do pedido {ped['numero_pedido']}: {cond or '—'}"
                      + (f", pago {body.valor_pago:.2f}" if body.valor_pago is not None else "")
                      + (f" em {data[:10]}" if data else "")))
        conn.commit()
        return {"mensagem": "Pagamento salvo"}
    finally:
        conn.close()


# ─── arte (verso da ficha) ───────────────────────────────────────────────────

@router.post("/pedido/{pid}/arte")
async def anexar_arte(pid: int, arquivo: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if not _pode_info(conn, current_user, ped):
            raise HTTPException(403, "Sem permissão para anexar a arte deste pedido.")
        ext = os.path.splitext(arquivo.filename or "")[1].lower()
        if ext not in EXT_ARTE:
            raise HTTPException(400, "Envie a arte em PDF ou imagem (JPG, PNG, WEBP).")
        dados = await arquivo.read()
        if not dados:
            raise HTTPException(400, "Arquivo vazio")
        if len(dados) > MAX_ARTE:
            raise HTTPException(400, "Arquivo muito grande (máx. 25 MB)")
        nome = f"{pid}_{uuid.uuid4().hex}{ext}"
        caminho = os.path.join(_pasta_artes(), nome)
        with open(caminho, "wb") as f:
            f.write(dados)
        previa = _gerar_previa_pdf(caminho) if ext == ".pdf" else None
        antigo, antiga_prev = ped["arte_arquivo"], ped["arte_previa"]
        conn.execute("UPDATE pedidos SET arte_arquivo=?, arte_arquivo_nome=?, arte_previa=? WHERE id=?",
                     (nome, os.path.basename(arquivo.filename or nome)[:200], previa, pid))
        conn.commit()
        _apagar(antigo)
        _apagar(antiga_prev)
        aviso = ""
        if ext == ".pdf" and not previa:
            aviso = " (não consegui gerar a imagem do PDF para o verso; a arte fica guardada para abrir)"
        return {"mensagem": "Arte anexada" + aviso, "tem_previa": bool(previa) or ext != ".pdf"}
    finally:
        conn.close()


def _arquivo_arte(pid: int, current_user: dict, previa: bool):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if current_user.get("role") == "comercial" and ped["vendedor_usuario_id"] != current_user.get("id"):
            raise HTTPException(403, "Pedido de outro vendedor")
        if not (_eh_gestor(current_user) or _liberada(conn)):
            raise HTTPException(403, "Programação da Produção ainda em teste (só o gestor).")
        nome = ped["arte_previa"] if (previa and ped["arte_previa"]) else ped["arte_arquivo"]
        nome_orig = ped["arte_arquivo_nome"]
    finally:
        conn.close()
    if not nome:
        raise HTTPException(404, "Este pedido não tem arte anexada")
    caminho = os.path.join(_pasta_artes(), os.path.basename(nome))
    if not os.path.exists(caminho):
        raise HTTPException(404, "Arquivo da arte não encontrado no servidor")
    ext = os.path.splitext(caminho)[1].lower()
    return FileResponse(caminho, media_type=EXT_ARTE.get(ext, "application/octet-stream"),
                        headers={"Content-Disposition": f'inline; filename="{os.path.basename(nome_orig or nome)}"'})


@router.get("/pedido/{pid}/arte")
def ver_arte(pid: int, current_user: dict = Depends(get_current_user)):
    return _arquivo_arte(pid, current_user, previa=False)


@router.get("/pedido/{pid}/arte-imagem")
def ver_arte_imagem(pid: int, current_user: dict = Depends(get_current_user)):
    """Imagem para o verso da ficha: a própria imagem, ou a prévia PNG quando a arte é PDF."""
    return _arquivo_arte(pid, current_user, previa=True)


@router.delete("/pedido/{pid}/arte")
def remover_arte(pid: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if not _pode_info(conn, current_user, ped):
            raise HTTPException(403, "Sem permissão")
        conn.execute("UPDATE pedidos SET arte_arquivo=NULL, arte_arquivo_nome=NULL, arte_previa=NULL WHERE id=?", (pid,))
        conn.commit()
        _apagar(ped["arte_arquivo"])
        _apagar(ped["arte_previa"])
        return {"mensagem": "Arte removida"}
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# Etapas 2 e 3: fila da produção (prioridade e urgência), programação do dia,
# pulos e a ficha impressa.
# ═════════════════════════════════════════════════════════════════════════════
from datetime import date, timedelta, timezone

BRT = timezone(timedelta(hours=-3))   # Brasil sem horário de verão desde 2019
SELOS = {
    "prioridade": {"ordem": 0, "rotulo": "PRIORIDADE"},
    "atrasado":   {"ordem": 1, "rotulo": "ATRASADO"},
    "urgente":    {"ordem": 2, "rotulo": "URGENTE"},
    "no_prazo":   {"ordem": 3, "rotulo": "NO PRAZO"},
}


def _hoje() -> date:
    return datetime.now(BRT).date()


def _data_param(d: Optional[str]) -> str:
    if not d:
        return _hoje().isoformat()
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise HTTPException(400, "Data inválida")


def _pode_programar(conn, u) -> bool:
    return _pode_ver_programacao(conn, u)


def _exigir_programar(conn, u):
    if not _pode_programar(conn, u):
        raise HTTPException(403, "Sem acesso à Programação da Produção.")


def _itens_dos_pedidos(conn, ids) -> dict:
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = conn.execute(f"""
        SELECT i.id, i.pedido_id, i.descricao, i.quantidade, COALESCE(i.qtd_produzida,0) AS qtd_produzida,
               i.unidade, i.produto_id, ep.codigo AS produto_codigo, ep.nome AS produto_nome,
               ec.tipo AS categoria_tipo
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON ep.id = i.produto_id
        LEFT JOIN estoque_categorias ec ON ec.id = ep.categoria_id
        WHERE i.pedido_id IN ({ph}) ORDER BY i.pedido_id, i.id""", tuple(ids)).fetchall()
    out = {}
    for r in rows:
        revenda = (r["categoria_tipo"] == "revenda")
        qtd = r["quantidade"] or 0
        falta = 0 if revenda else max(0, qtd - (r["qtd_produzida"] or 0))
        out.setdefault(r["pedido_id"], []).append({
            "id": r["id"], "descricao": r["descricao"], "produto": r["produto_nome"] or r["descricao"],
            "codigo": r["produto_codigo"] or (str(r["produto_id"]) if r["produto_id"] else ""),
            "quantidade": qtd, "produzido": r["qtd_produzida"] or 0, "a_produzir": falta,
            "unidade": r["unidade"] or "", "revenda": revenda,
        })
    return out


def _classificar(ped, hoje: date, urg_dias: int):
    dias = None
    if ped["prazo_entrega"]:
        try:
            dias = (datetime.strptime(str(ped["prazo_entrega"])[:10], "%Y-%m-%d").date() - hoje).days
        except ValueError:
            dias = None
    if ped["prioridade_status"] == "aprovada":
        selo = "prioridade"
    elif dias is not None and dias < 0:
        selo = "atrasado"
    elif dias is not None and dias <= urg_dias:
        selo = "urgente"
    else:
        selo = "no_prazo"
    return selo, dias


def _chave_regra(p):
    """Prioridade (pela aprovação) → Atrasado e Urgente (pelo prazo) → No prazo (ordem de chegada)."""
    s = SELOS[p["selo"]]["ordem"]
    if p["selo"] == "prioridade":
        return (s, p.get("prioridade_decidida_em") or "", p["id"])
    if p["selo"] in ("atrasado", "urgente"):
        return (s, p.get("prazo") or "9999", p["id"])
    return (s, p.get("criado_em") or "", p["id"])


def _montar_fila(conn, data: str, u) -> dict:
    hoje = _hoje()
    urg = _int_cfg(conn, "urgencia_dias", 3)
    rows = conn.execute("""
        SELECT p.*, c.razao_social, c.nome_fantasia, c.cidade, c.uf, uv.nome AS vendedor_nome
        FROM pedidos p
        JOIN pedidos_clientes c ON c.id = p.cliente_id
        LEFT JOIN usuarios uv ON uv.id = p.vendedor_usuario_id
        WHERE p.status IN ('aberto','em_producao')""").fetchall()
    itens = _itens_dos_pedidos(conn, [r["id"] for r in rows])
    pulos = {r["pedido_id"]: dict(r) for r in conn.execute(
        "SELECT id, pedido_id, motivo, usuario, criado_em FROM programacao_pulos WHERE data=? ORDER BY id", (data,))}
    ordem = {r["pedido_id"]: r["posicao"] for r in conn.execute(
        "SELECT pedido_id, posicao FROM programacao_ordem WHERE data=?", (data,))}
    lista = []
    for r in rows:
        its = itens.get(r["id"], [])
        a_prod = sum(i["a_produzir"] for i in its)
        if a_prod <= 0:
            continue   # nada a produzir (só revenda, ou já produzido)
        selo, dias = _classificar(r, hoje, urg)
        lista.append({
            "id": r["id"], "numero": r["numero_pedido"],
            "cliente": r["nome_fantasia"] or r["razao_social"], "razao_social": r["razao_social"],
            "cidade": r["cidade"], "uf": r["uf"],
            "vendedor": r["vendedor_nome"] or r["vendedor"] or "",
            "prazo": r["prazo_entrega"], "dias": dias, "criado_em": r["created_at"],
            "status": r["status"], "selo": selo, "selo_rotulo": SELOS[selo]["rotulo"],
            "prioridade_status": r["prioridade_status"], "prioridade_motivo": r["prioridade_motivo"],
            "prioridade_decidida_por": r["prioridade_decidida_por"], "prioridade_decidida_em": r["prioridade_decidida_em"],
            "cor_impressao": r["info_cor_impressao"], "marca": r["info_marca"],
            "arte_modo": r["info_arte_modo"], "tem_arte": bool(r["arte_arquivo"]),
            "itens": its, "a_produzir": a_prod,
            "pulo": pulos.get(r["id"]),
        })
    lista.sort(key=_chave_regra)
    for n, p in enumerate(lista, 1):
        p["posicao_regra"] = n
    # Ordem ajustada à mão (arrastar) vale para o dia; pedido novo entra pela regra, logo depois
    if ordem:
        # prioridade aprovada fica sempre no topo, mesmo com a ordem ajustada à mão
        lista.sort(key=lambda p: (0 if p["selo"] == "prioridade" else 1,
                                  (0, ordem[p["id"]]) if p["id"] in ordem else (1, p["posicao_regra"])))
    # Pulados no dia vão para o fim (voltam na próxima programação)
    lista.sort(key=lambda p: 1 if p["pulo"] else 0)
    pos = 0
    for p in lista:
        if not p["pulo"]:
            pos += 1
            p["posicao"] = pos
        else:
            p["posicao"] = None
    conf = conn.execute("SELECT confirmado_por, confirmado_em FROM programacao_confirmada WHERE data=?", (data,)).fetchone()
    cont = {k: 0 for k in SELOS}
    for p in lista:
        if not p["pulo"]:
            cont[p["selo"]] += 1
    out = {
        "data": data, "hoje": hoje.isoformat(), "fila": lista, "contadores": cont,
        "confirmada": dict(conf) if conf else None, "ordem_manual": bool(ordem),
        "urgencia_dias": urg, "prioridade_limite": _int_cfg(conn, "prioridade_limite", 3),
        "prioridades_ativas": _prioridades_ativas(conn),
        "gestor": _eh_gestor(u), "liberada": _liberada(conn),
    }
    if _eh_gestor(u):
        out["prioridades_pendentes"] = [dict(r) for r in conn.execute("""
            SELECT p.id, p.numero_pedido AS numero, COALESCE(c.nome_fantasia, c.razao_social) AS cliente,
                   p.prazo_entrega AS prazo, p.prioridade_motivo AS motivo, p.prioridade_pedida_por AS pedida_por,
                   p.prioridade_pedida_em AS pedida_em, COALESCE(uv.nome, p.vendedor) AS vendedor
            FROM pedidos p JOIN pedidos_clientes c ON c.id = p.cliente_id
            LEFT JOIN usuarios uv ON uv.id = p.vendedor_usuario_id
            WHERE p.prioridade_status = 'pedida' AND p.status IN ('aberto','em_producao')
            ORDER BY p.prioridade_pedida_em""")]
        posicoes = {p["id"]: p["posicao_regra"] for p in lista}
        for pp in out["prioridades_pendentes"]:
            pp["posicao_atual"] = posicoes.get(pp["id"])
    return out


def _prioridades_ativas(conn) -> int:
    return conn.execute("""SELECT COUNT(*) FROM pedidos WHERE prioridade_status='aprovada'
                           AND status IN ('aberto','em_producao')""").fetchone()[0]


@router.get("/fila")
def fila(data: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        _exigir_programar(conn, current_user)
        return _montar_fila(conn, _data_param(data), current_user)
    finally:
        conn.close()


@router.get("/pendencias")
def pendencias(current_user: dict = Depends(get_current_user)):
    """Contador do menu: prioridades esperando o gestor."""
    if not _eh_gestor(current_user):
        return {"prioridades_pendentes": 0}
    conn = get_conn()
    try:
        n = conn.execute("""SELECT COUNT(*) FROM pedidos WHERE prioridade_status='pedida'
                            AND status IN ('aberto','em_producao')""").fetchone()[0]
        return {"prioridades_pendentes": n}
    finally:
        conn.close()


class OrdemIn(BaseModel):
    data: Optional[str] = None
    pedido_ids: list


def _salvar_ordem(conn, data: str, ids: list):
    conn.execute("DELETE FROM programacao_ordem WHERE data=?", (data,))
    vistos = set()
    pos = 0
    for pid in ids:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if pid in vistos:
            continue
        vistos.add(pid)
        pos += 1
        conn.execute("INSERT INTO programacao_ordem (data, pedido_id, posicao) VALUES (?, ?, ?)", (data, pid, pos))


@router.put("/ordem")
def salvar_ordem(body: OrdemIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        _exigir_programar(conn, current_user)
        data = _data_param(body.data)
        _salvar_ordem(conn, data, body.pedido_ids or [])
        conn.commit()
        return {"mensagem": "Ordem salva"}
    finally:
        conn.close()


@router.delete("/ordem")
def voltar_regra(data: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Desfaz os ajustes à mão do dia: a fila volta a seguir só a regra."""
    conn = get_conn()
    try:
        _exigir_programar(conn, current_user)
        conn.execute("DELETE FROM programacao_ordem WHERE data=?", (_data_param(data),))
        conn.commit()
        return {"mensagem": "Fila voltou para a ordem da regra"}
    finally:
        conn.close()


@router.post("/confirmar")
def confirmar(body: OrdemIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        _exigir_programar(conn, current_user)
        data = _data_param(body.data)
        if body.pedido_ids:
            _salvar_ordem(conn, data, body.pedido_ids)
        conn.execute("""INSERT INTO programacao_confirmada (data, confirmado_por, confirmado_em)
                        VALUES (?, ?, datetime('now','localtime'))
                        ON CONFLICT(data) DO UPDATE SET confirmado_por=excluded.confirmado_por,
                                                        confirmado_em=excluded.confirmado_em""",
                     (data, _nome(current_user)))
        conn.commit()
        return {"mensagem": "Programação do dia confirmada"}
    finally:
        conn.close()


class PuloIn(BaseModel):
    pedido_id: int
    motivo: str
    data: Optional[str] = None


@router.post("/pular")
def pular(body: PuloIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        _exigir_programar(conn, current_user)
        motivo = (body.motivo or "").strip()
        if len(motivo) < 3:
            raise HTTPException(400, "Informe o motivo (ex.: faltou copo, máquina com outra cor).")
        data = _data_param(body.data)
        _pedido(conn, body.pedido_id)
        conn.execute("DELETE FROM programacao_pulos WHERE data=? AND pedido_id=?", (data, body.pedido_id))
        conn.execute("INSERT INTO programacao_pulos (data, pedido_id, motivo, usuario) VALUES (?, ?, ?, ?)",
                     (data, body.pedido_id, motivo[:300], _nome(current_user)))
        conn.commit()
        return {"mensagem": "Pedido pulado hoje. Ele volta na próxima programação."}
    finally:
        conn.close()


@router.delete("/pular/{pedido_id}")
def desfazer_pulo(pedido_id: int, data: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        _exigir_programar(conn, current_user)
        conn.execute("DELETE FROM programacao_pulos WHERE data=? AND pedido_id=?", (_data_param(data), pedido_id))
        conn.commit()
        return {"mensagem": "Pedido voltou para a fila"}
    finally:
        conn.close()


# ─── prioridade: o vendedor pede, só o gestor aprova ─────────────────────────

class PrioridadeIn(BaseModel):
    motivo: Optional[str] = None


class DecisaoIn(BaseModel):
    aprovar: bool
    obs: Optional[str] = None


def _auditar(conn, u, pid, acao, desc):
    conn.execute("INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao) VALUES (?, ?, 'pedido', ?, ?)",
                 (_nome(u), acao, pid, desc))


def _checar_limite(conn, pid):
    lim = _int_cfg(conn, "prioridade_limite", 3)
    ativas = conn.execute("""SELECT COUNT(*) FROM pedidos WHERE prioridade_status='aprovada'
                             AND status IN ('aberto','em_producao') AND id != ?""", (pid,)).fetchone()[0]
    if lim and ativas >= lim:
        raise HTTPException(409, f"Limite de {lim} prioridades ao mesmo tempo atingido. Tire a prioridade de um pedido antes de aprovar outro.")


@router.post("/pedido/{pid}/prioridade")
def pedir_prioridade(pid: int, body: PrioridadeIn, current_user: dict = Depends(get_current_user)):
    """Vendedor (ou quem edita pedidos) pede; o gestor, ao usar, já dá a prioridade."""
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if not _pode_info(conn, current_user, ped):
            raise HTTPException(403, "Sem permissão para pedir prioridade neste pedido.")
        if ped["status"] not in ("aberto", "em_producao"):
            raise HTTPException(400, "Prioridade só vale para pedido que ainda está na produção.")
        motivo = (body.motivo or "").strip()
        if len(motivo) < 5:
            raise HTTPException(400, "Escreva o motivo da prioridade.")
        if _eh_gestor(current_user):
            _checar_limite(conn, pid)
            conn.execute("""UPDATE pedidos SET prioridade_status='aprovada', prioridade_motivo=?,
                            prioridade_pedida_por=COALESCE(prioridade_pedida_por, ?),
                            prioridade_pedida_em=COALESCE(prioridade_pedida_em, datetime('now','localtime')),
                            prioridade_decidida_por=?, prioridade_decidida_em=datetime('now','localtime'),
                            prioridade_obs_gestor=NULL WHERE id=?""",
                         (motivo[:500], _nome(current_user), _nome(current_user), pid))
            _auditar(conn, current_user, pid, "prioridade_aprovada", f"Prioridade dada ao pedido {ped['numero_pedido']}: {motivo[:200]}")
            msg = "Prioridade dada: o pedido sobe para o topo da fila."
        else:
            if ped["prioridade_status"] == "aprovada":
                raise HTTPException(400, "Este pedido já está com prioridade.")
            conn.execute("""UPDATE pedidos SET prioridade_status='pedida', prioridade_motivo=?,
                            prioridade_pedida_por=?, prioridade_pedida_em=datetime('now','localtime'),
                            prioridade_decidida_por=NULL, prioridade_decidida_em=NULL, prioridade_obs_gestor=NULL
                            WHERE id=?""", (motivo[:500], _nome(current_user), pid))
            _auditar(conn, current_user, pid, "prioridade_pedida", f"Prioridade pedida para o pedido {ped['numero_pedido']}: {motivo[:200]}")
            msg = "Pedido de prioridade enviado ao gestor."
        conn.commit()
        return {"mensagem": msg}
    finally:
        conn.close()


@router.post("/pedido/{pid}/prioridade/decidir")
def decidir_prioridade(pid: int, body: DecisaoIn, current_user: dict = Depends(get_current_user)):
    if not _eh_gestor(current_user):
        raise HTTPException(403, "Só o gestor aprova prioridade.")
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if ped["prioridade_status"] != "pedida":
            raise HTTPException(400, "Este pedido não tem prioridade esperando aprovação.")
        if body.aprovar:
            _checar_limite(conn, pid)
        novo = "aprovada" if body.aprovar else "recusada"
        conn.execute("""UPDATE pedidos SET prioridade_status=?, prioridade_decidida_por=?,
                        prioridade_decidida_em=datetime('now','localtime'), prioridade_obs_gestor=? WHERE id=?""",
                     (novo, _nome(current_user), _limpo(body.obs, 300), pid))
        _auditar(conn, current_user, pid, "prioridade_" + novo,
                 f"Prioridade {novo} no pedido {ped['numero_pedido']}" + (f": {body.obs.strip()[:200]}" if body.obs and body.obs.strip() else ""))
        conn.commit()
        return {"mensagem": "Prioridade aprovada" if body.aprovar else "Prioridade recusada"}
    finally:
        conn.close()


@router.delete("/pedido/{pid}/prioridade")
def remover_prioridade(pid: int, current_user: dict = Depends(get_current_user)):
    """Gestor tira a prioridade; quem pediu pode cancelar enquanto não foi decidida."""
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        if not _eh_gestor(current_user):
            if ped["prioridade_status"] != "pedida" or not _pode_info(conn, current_user, ped):
                raise HTTPException(403, "Só o gestor tira uma prioridade aprovada.")
        conn.execute("""UPDATE pedidos SET prioridade_status=NULL, prioridade_motivo=NULL, prioridade_pedida_por=NULL,
                        prioridade_pedida_em=NULL, prioridade_decidida_por=NULL, prioridade_decidida_em=NULL,
                        prioridade_obs_gestor=NULL WHERE id=?""", (pid,))
        _auditar(conn, current_user, pid, "prioridade_removida", f"Prioridade retirada do pedido {ped['numero_pedido']}")
        conn.commit()
        return {"mensagem": "Prioridade retirada"}
    finally:
        conn.close()


# ─── ficha impressa (frente e verso) ─────────────────────────────────────────

@router.get("/fichas")
def fichas(ids: str, data: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Dados das fichas de produção dos pedidos (na ordem pedida). A frente lista todos os
    itens numa folha só; o verso traz a arte."""
    conn = get_conn()
    try:
        if not (_eh_gestor(current_user) or _liberada(conn)):
            raise HTTPException(403, "Programação da Produção ainda em teste (só o gestor).")
        lista_ids = []
        for x in (ids or "").split(","):
            try:
                lista_ids.append(int(x))
            except ValueError:
                pass
        if not lista_ids:
            raise HTTPException(400, "Informe os pedidos")
        if len(lista_ids) > 200:
            raise HTTPException(400, "Muitos pedidos de uma vez (máx. 200)")
        d = _data_param(data)
        posicoes = {}
        if _pode_programar(conn, current_user):
            for p in _montar_fila(conn, d, current_user)["fila"]:
                posicoes[p["id"]] = p["posicao"]
        hoje = _hoje()
        urg = _int_cfg(conn, "urgencia_dias", 3)
        itens = _itens_dos_pedidos(conn, lista_ids)
        out = []
        for pid in lista_ids:
            r = conn.execute("""
                SELECT p.*, c.razao_social, c.nome_fantasia, c.cidade, c.uf, uv.nome AS vendedor_nome
                FROM pedidos p JOIN pedidos_clientes c ON c.id = p.cliente_id
                LEFT JOIN usuarios uv ON uv.id = p.vendedor_usuario_id WHERE p.id=?""", (pid,)).fetchone()
            if not r:
                continue
            if current_user.get("role") == "comercial" and r["vendedor_usuario_id"] != current_user.get("id"):
                continue
            selo, dias = _classificar(r, hoje, urg)
            arte_img = bool(r["arte_previa"]) or (bool(r["arte_arquivo"]) and not (r["arte_arquivo"] or "").lower().endswith(".pdf"))
            out.append({
                "id": r["id"], "numero": r["numero_pedido"],
                "cliente": r["razao_social"], "fantasia": r["nome_fantasia"],
                "cidade": r["cidade"], "uf": r["uf"], "vendedor": r["vendedor_nome"] or r["vendedor"] or "",
                "lancado_em": r["created_at"], "prazo": r["prazo_entrega"], "dias": dias,
                "selo": selo, "selo_rotulo": SELOS[selo]["rotulo"],
                "prioridade_motivo": r["prioridade_motivo"] if selo == "prioridade" else None,
                "prioridade_decidida_por": r["prioridade_decidida_por"] if selo == "prioridade" else None,
                "posicao": posicoes.get(r["id"]),
                "info": {"cor_impressao": r["info_cor_impressao"], "marca": r["info_marca"],
                         "arte_modo": r["info_arte_modo"], "arte_ref": r["info_arte_ref"],
                         "observacao": r["info_observacao"]},
                "obs_pedido": r["observacoes"],
                "arte": {"tem": bool(r["arte_arquivo"]), "imagem": arte_img, "nome": r["arte_arquivo_nome"]},
                "itens": itens.get(r["id"], []),
            })
        return {"fichas": out, "impresso_em": datetime.now(BRT).strftime("%d/%m/%Y %H:%M"),
                "impresso_por": _nome(current_user)}
    finally:
        conn.close()


@router.get("/meus")
def minha_fila(current_user: dict = Depends(get_current_user)):
    """Para o portal do vendedor: posição na fila de hoje e selo dos pedidos dele."""
    conn = get_conn()
    try:
        if not (_eh_gestor(current_user) or _liberada(conn)):
            return {"liberada": False, "pedidos": {}}
        u_fila = {"role": "gestor"}  # a posição é a mesma para todos; filtra os do vendedor abaixo
        f = _montar_fila(conn, _hoje().isoformat(), u_fila)
        meus = {}
        for p in f["fila"]:
            meus[str(p["id"])] = {"posicao": p["posicao"], "selo": p["selo"], "selo_rotulo": p["selo_rotulo"],
                                  "pulado": bool(p["pulo"]), "total": len(f["fila"])}
        if current_user.get("role") == "comercial":
            ids = {str(r[0]) for r in conn.execute("SELECT id FROM pedidos WHERE vendedor_usuario_id=?", (current_user.get("id"),))}
            meus = {k: v for k, v in meus.items() if k in ids}
            pend = {str(r[0]): r[1] for r in conn.execute(
                "SELECT id, prioridade_status FROM pedidos WHERE vendedor_usuario_id=? AND prioridade_status IN ('pedida','recusada')",
                (current_user.get("id"),))}
            for k, st in pend.items():
                meus.setdefault(k, {})["prioridade_status"] = st
        return {"liberada": True, "pedidos": meus}
    finally:
        conn.close()
