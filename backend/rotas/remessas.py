"""Envio parcial (remessas) de um pedido.

Quando o cliente precisa de parte do pedido com urgência, o vendedor cria uma remessa com
as quantidades disponíveis (já produzidas / revenda já separada), a transportadora e o frete
cotados para ela. A Expedição lança a NF da remessa (com o PDF da nota) e despacha. O saldo
que falta segue o fluxo normal do pedido; quando tudo saiu, o pedido fica Enviado.
"""
import datetime
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth_utils import get_current_user
from database import get_conn
from rotas.pedidos import (
    NF_MAX_BYTES, _calcular_cotacao, _ler_numero_nf, _marcar_usuario_hist, _nome_usuario,
    _pasta_nf, _recalc_status_pedido, _remessado_por_item, exigir_permissao, verificar_permissao,
)

router = APIRouter()

STATUS_PENDENTES = ("aguardando_nf", "aguardando_retirada")
STATUS_FEITAS = ("enviado", "retirado")


class RemessaItemIn(BaseModel):
    pedido_item_id: int
    quantidade: float


class RemessaIn(BaseModel):
    itens: List[RemessaItemIn]
    modo: str                       # transportadora | retirada
    transportadora: Optional[str] = ""
    frete: Optional[float] = 0
    previsao_entrega: Optional[str] = ""
    retirada_prevista: Optional[str] = ""
    obs_vendedor: Optional[str] = ""
    cotacao_numero: Optional[str] = ""     # nº da cotação da transportadora


class CotacaoRemessaIn(BaseModel):
    itens: List[RemessaItemIn]


class DespachoRemessaIn(BaseModel):
    transportadora: Optional[str] = ""
    nota_fiscal: Optional[str] = ""
    rastreio: Optional[str] = ""
    volumes: Optional[int] = 0
    previsao_entrega: Optional[str] = ""
    frete: Optional[float] = 0
    obs_envio: Optional[str] = ""
    data_despacho: Optional[str] = ""
    entrega_cep: Optional[str] = None
    entrega_logradouro: Optional[str] = None
    entrega_numero: Optional[str] = None
    entrega_complemento: Optional[str] = None
    entrega_bairro: Optional[str] = None
    entrega_cidade: Optional[str] = None
    entrega_uf: Optional[str] = None
    atualizar_cadastro_cliente: Optional[bool] = False


class RetiradaRemessaIn(BaseModel):
    nota_fiscal: str
    data_retirada: Optional[str] = ""
    volumes: Optional[int] = 0
    obs: Optional[str] = ""


# ─── apoio ──────────────────────────────────────────────────────────────────

def _pedido(conn, pid: int):
    ped = conn.execute("SELECT * FROM pedidos WHERE id=?", (pid,)).fetchone()
    if not ped:
        raise HTTPException(404, "Pedido não encontrado")
    return ped


def _checar_acesso_pedido(ped, current_user: dict):
    if current_user.get("role") == "comercial" and ped["vendedor_usuario_id"] != current_user["id"]:
        raise HTTPException(403, "Este pedido não é seu.")


def _remessa(conn, rid: int):
    r = conn.execute("SELECT * FROM pedidos_remessas WHERE id=?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "Remessa não encontrada")
    return r


def _itens_disponiveis(conn, pid: int) -> list:
    """Por item: pedido, já produzido (revenda: separada = tudo), já em remessas e disponível agora."""
    remessado = _remessado_por_item(conn, pid)
    rows = conn.execute("""
        SELECT i.id, i.descricao, i.quantidade, i.unidade, i.qtd_produzida, i.status, i.produto_id,
               ep.nome AS produto_nome, ec.tipo AS categoria_tipo
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON ep.id = i.produto_id
        LEFT JOIN estoque_categorias ec ON ec.id = ep.categoria_id
        WHERE i.pedido_id = ? ORDER BY i.id
    """, (pid,)).fetchall()
    out = []
    for r in rows:
        revenda = r["categoria_tipo"] == "revenda"
        qtd = float(r["quantidade"] or 0)
        if revenda:
            separado = r["status"] == "entregue"
            pronto = qtd if separado else 0.0
        else:
            separado = None
            pronto = min(qtd, float(r["qtd_produzida"] or 0)) if r["status"] not in ("produzido", "entregue") else qtd
        ja = float(remessado.get(r["id"], 0))
        out.append({
            "pedido_item_id": r["id"], "descricao": r["descricao"] or r["produto_nome"] or "Item",
            "unidade": r["unidade"] or "", "quantidade": qtd, "pronto": pronto, "remessado": ja,
            "disponivel": max(0.0, pronto - ja), "restante": max(0.0, qtd - ja),
            "revenda": revenda, "separado": separado,
        })
    return out


def _restante_total(conn, pid: int) -> float:
    return sum(i["restante"] for i in _itens_disponiveis(conn, pid))


def _listar_remessas(conn, where: str, params: tuple) -> list:
    rows = conn.execute(f"""
        SELECT r.*, p.numero_pedido, p.cliente_id, p.vendedor, p.vendedor_usuario_id, p.status AS pedido_status,
               c.razao_social AS cliente_nome, uv.nome AS vendedor_usuario_nome,
               CAST(julianday('now','localtime') - julianday(r.status_desde) AS INTEGER) AS dias_na_etapa
        FROM pedidos_remessas r
        JOIN pedidos p ON p.id = r.pedido_id
        JOIN pedidos_clientes c ON c.id = p.cliente_id
        LEFT JOIN usuarios uv ON uv.id = p.vendedor_usuario_id
        WHERE {where}
        ORDER BY r.id DESC
    """, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["itens"] = [dict(x) for x in conn.execute("""
            SELECT ri.pedido_item_id, ri.quantidade, i.descricao, i.unidade
            FROM pedidos_remessa_itens ri JOIN pedidos_itens i ON i.id = ri.pedido_item_id
            WHERE ri.remessa_id = ? ORDER BY ri.id""", (r["id"],)).fetchall()]
        d["total_qtd"] = sum(x["quantidade"] or 0 for x in d["itens"])
        d["tem_nf_pdf"] = 1 if r["nf_arquivo"] else 0
        out.append(d)
    return out


def _concluir_pedido_se_tudo_enviado(conn, pid: int, current_user: dict):
    """Tudo o que foi pedido já saiu em remessas → pedido Enviado (ou Retirado, se todas foram retiradas)."""
    feito = _remessado_por_item(conn, pid, incluir_pendentes=False)
    itens = conn.execute("SELECT id, quantidade FROM pedidos_itens WHERE pedido_id=?", (pid,)).fetchall()
    if not itens or any(feito.get(i["id"], 0) + 1e-9 < (i["quantidade"] or 0) for i in itens):
        return False
    rems = conn.execute("""SELECT modo, status, nota_fiscal, data_despacho, transportadora FROM pedidos_remessas
                           WHERE pedido_id=? AND status IN ('enviado','retirado') ORDER BY id""", (pid,)).fetchall()
    status = "retirado" if rems and all(r["status"] == "retirado" for r in rems) else "enviado"
    nfs = ", ".join(dict.fromkeys(r["nota_fiscal"] for r in rems if r["nota_fiscal"]))
    data = max((r["data_despacho"] or "" for r in rems), default="")
    transp = next((r["transportadora"] for r in reversed(rems) if r["transportadora"]), None)
    conn.execute("""UPDATE pedidos SET status=?, nota_fiscal=?, data_despacho=?,
                    transportadora=COALESCE(?, transportadora), concluido_por=?, concluido_por_remessas=1 WHERE id=?""",
                 (status, nfs, data, transp, _nome_usuario(current_user), pid))
    _marcar_usuario_hist(conn, pid, current_user)
    return True


def _reabrir_pedido_se_concluido_por_remessas(conn, pid: int):
    ped = conn.execute("SELECT status, COALESCE(concluido_por_remessas,0) AS cpr FROM pedidos WHERE id=?", (pid,)).fetchone()
    if ped and ped["cpr"] and ped["status"] in STATUS_FEITAS:
        conn.execute("UPDATE pedidos SET status='aberto', concluido_por_remessas=0 WHERE id=?", (pid,))
        _recalc_status_pedido(conn.cursor(), pid)


# ─── consultas ──────────────────────────────────────────────────────────────

@router.get("/pedido/{pid}/disponivel")
def disponivel(pid: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        _checar_acesso_pedido(ped, current_user)
        return {"pedido_id": pid, "numero_pedido": ped["numero_pedido"], "status": ped["status"],
                "itens": _itens_disponiveis(conn, pid)}
    finally:
        conn.close()


@router.post("/pedido/{pid}/cotacao")
def cotacao_remessa(pid: int, body: CotacaoRemessaIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        _checar_acesso_pedido(ped, current_user)
        qtd = {i.pedido_item_id: i.quantidade for i in body.itens if (i.quantidade or 0) > 0}
        return _calcular_cotacao(conn, pid, qtd, usar_manuais=False)
    finally:
        conn.close()


@router.get("/pedido/{pid}")
def remessas_do_pedido(pid: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        _checar_acesso_pedido(ped, current_user)
        itens = _itens_disponiveis(conn, pid)
        feito = _remessado_por_item(conn, pid, incluir_pendentes=False)
        return {"remessas": _listar_remessas(conn, "r.pedido_id = ? AND r.status != 'cancelada'", (pid,)),
                "total_pedido": sum(i["quantidade"] for i in itens),
                "total_enviado": sum(feito.values()) if feito else 0,
                "total_reservado": sum(i["remessado"] for i in itens),
                "itens": itens}
    finally:
        conn.close()


@router.get("/fila")
def fila_remessas(current_user: dict = Depends(get_current_user)):
    """Remessas para a Expedição: pendentes e concluídas nos últimos 60 dias."""
    conn = get_conn()
    try:
        where = "(r.status IN ('aguardando_nf','aguardando_retirada') OR (r.status IN ('enviado','retirado') AND COALESCE(r.data_despacho, r.concluido_em, r.criado_em) >= date('now','localtime','-60 days')))"
        params = ()
        if current_user.get("role") == "gestor":   # Gestor também vê (e pode autorizar) as que esperam o cliente
            where = "(r.status = 'aguardando_cliente' OR " + where + ")"
        if current_user.get("role") == "comercial":
            where += " AND p.vendedor_usuario_id = ?"
            params = (current_user["id"],)
        return _listar_remessas(conn, where, params)
    finally:
        conn.close()


@router.get("/meus")
def minhas_remessas(current_user: dict = Depends(get_current_user)):
    """Portal do vendedor: remessas ativas e as concluídas nos últimos 15 dias, novidades
    (remessas concluídas desde o último 'visto') e o saldo que falta enviar por pedido."""
    conn = get_conn()
    try:
        uid = current_user["id"]
        rems = _listar_remessas(conn, """p.vendedor_usuario_id = ? AND (r.status IN ('aguardando_cliente','aguardando_nf','aguardando_retirada')
                                         OR (r.status IN ('enviado','retirado') AND COALESCE(r.concluido_em, r.criado_em) >= datetime('now','localtime','-15 days')))""",
                                (uid,))
        visto = conn.execute("SELECT meus_pedidos_visto_em FROM usuarios WHERE id=?", (uid,)).fetchone()
        visto_em = (visto["meus_pedidos_visto_em"] if visto else None) or ""
        novidades = [{"id": f"r{r['id']}", "remessa_id": r["id"], "status": "remessa_" + r["status"],
                      "em": r["concluido_em"], "pedido_id": r["pedido_id"], "numero_pedido": r["numero_pedido"],
                      "nota_fiscal": r["nota_fiscal"], "cliente_nome": r["cliente_nome"], "numero": r["numero"]}
                     for r in rems if r["status"] in STATUS_FEITAS and (r["concluido_em"] or "") > visto_em]
        pids = {r["pedido_id"] for r in conn.execute("""SELECT DISTINCT r.pedido_id FROM pedidos_remessas r
                    JOIN pedidos p ON p.id = r.pedido_id WHERE p.vendedor_usuario_id = ? AND r.status != 'cancelada'
                    AND p.status NOT IN ('enviado','retirado','entregue')""", (uid,)).fetchall()}
        restante = {pid: _restante_total(conn, pid) for pid in pids}
        return {"remessas": rems, "novidades": novidades, "restante": restante}
    finally:
        conn.close()


# ─── vendedor cria / cancela ────────────────────────────────────────────────

@router.post("/pedido/{pid}")
def criar_remessa(pid: int, body: RemessaIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ped = _pedido(conn, pid)
        role = current_user.get("role")
        if role == "comercial":
            _checar_acesso_pedido(ped, current_user)
        elif role != "gestor":
            raise HTTPException(403, "O envio parcial é pedido pelo vendedor (ou pelo Gestor).")
        if (ped["status"] or "aberto") not in ("aberto", "em_producao", "produzido"):
            raise HTTPException(400, "Este pedido não aceita mais envio parcial (já foi liberado ou concluído).")
        disp = {i["pedido_item_id"]: i for i in _itens_disponiveis(conn, pid)}
        itens = [i for i in body.itens if (i.quantidade or 0) > 0]
        if not itens:
            raise HTTPException(400, "Informe a quantidade de pelo menos um item.")
        for it in itens:
            d = disp.get(it.pedido_item_id)
            if not d:
                raise HTTPException(400, "Item não pertence a este pedido.")
            if d["revenda"] and not d["separado"]:
                raise HTTPException(400, f"{d['descricao']}: separe a revenda antes de incluir na remessa.")
            if it.quantidade > d["disponivel"] + 1e-9:
                raise HTTPException(400, f"{d['descricao']}: disponível agora {d['disponivel']:g}, pediu {it.quantidade:g}.")
        modo = (body.modo or "").strip().lower()
        transp = None
        if modo == "transportadora":
            transp = (body.transportadora or "").strip()
            cad = conn.execute("SELECT nome FROM transportadoras WHERE nome = ? COLLATE NOCASE AND ativo = 1", (transp,)).fetchone()
            if not cad:
                raise HTTPException(400, "Escolha uma transportadora cadastrada.")
            transp = cad["nome"]
            status = "aguardando_cliente"     # só vai para a Expedição quando o cliente autorizar o frete
        elif modo == "retirada":
            status = "aguardando_retirada"
        else:
            raise HTTPException(400, "Escolha transportadora ou retirada.")
        numero = (conn.execute("SELECT COALESCE(MAX(numero),0) FROM pedidos_remessas WHERE pedido_id=?", (pid,)).fetchone()[0] or 0) + 1
        cur = conn.cursor()
        cur.execute("""INSERT INTO pedidos_remessas (pedido_id, numero, modo, status, transportadora, frete, previsao_entrega,
                       retirada_prevista, obs_vendedor, criado_por) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (pid, numero, modo, status, transp, float(body.frete or 0) if modo == "transportadora" else 0,
                     (body.previsao_entrega or "").strip() if modo == "transportadora" else None,
                     (body.retirada_prevista or "").strip() if modo == "retirada" else None,
                     (body.obs_vendedor or "").strip(), _nome_usuario(current_user)))
        rid = cur.lastrowid
        if modo == "transportadora" and (body.cotacao_numero or "").strip():
            cur.execute("UPDATE pedidos_remessas SET cotacao_numero=? WHERE id=?", (body.cotacao_numero.strip()[:60], rid))
        for it in itens:
            cur.execute("INSERT INTO pedidos_remessa_itens (remessa_id, pedido_item_id, quantidade) VALUES (?,?,?)",
                        (rid, it.pedido_item_id, it.quantidade))
        conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                        VALUES (?, 'criar_remessa', 'pedidos', ?, ?, '', ?)""",
                     (_nome_usuario(current_user), pid, f"Pedido {ped['numero_pedido']}: remessa parcial {numero}",
                      ", ".join(f"{disp[i.pedido_item_id]['descricao']}: {i.quantidade:g}" for i in itens)))
        conn.commit()
        msg = (f"Remessa {numero} do pedido {ped['numero_pedido']}: cotação registrada. Quando o cliente autorizar, clique em 'Cliente autorizou'."
               if status == "aguardando_cliente" else f"Remessa {numero} do pedido {ped['numero_pedido']} enviada para a Expedição.")
        return {"mensagem": msg, "remessa_id": rid}
    finally:
        conn.close()


@router.post("/{rid}/cancelar")
def cancelar_remessa(rid: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        ped = _pedido(conn, r["pedido_id"])
        if current_user.get("role") == "comercial":
            _checar_acesso_pedido(ped, current_user)
        elif current_user.get("role") != "gestor":
            raise HTTPException(403, "Só o vendedor do pedido ou o Gestor cancela a remessa.")
        if r["status"] not in STATUS_PENDENTES + ("aguardando_cliente",):
            raise HTTPException(400, "A Expedição já lançou a NF desta remessa. Peça para ela desfazer.")
        conn.execute("UPDATE pedidos_remessas SET status='cancelada', status_desde=datetime('now','localtime') WHERE id=?", (rid,))
        conn.commit()
        return {"mensagem": f"Remessa {r['numero']} cancelada; as quantidades voltaram para o saldo do pedido."}
    finally:
        conn.close()


@router.post("/{rid}/autorizar")
def autorizar_remessa(rid: int, current_user: dict = Depends(get_current_user)):
    """Cliente autorizou o frete da remessa → vai para a fila da Expedição (aguardando NF)."""
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        ped = _pedido(conn, r["pedido_id"])
        if current_user.get("role") == "comercial":
            _checar_acesso_pedido(ped, current_user)
        elif current_user.get("role") != "gestor":
            raise HTTPException(403, "Só o vendedor do pedido ou o Gestor autoriza o frete.")
        if r["status"] != "aguardando_cliente":
            raise HTTPException(400, "Esta remessa não está aguardando a autorização do cliente.")
        conn.execute("""UPDATE pedidos_remessas SET status='aguardando_nf', status_desde=datetime('now','localtime'),
                        cotacao_autorizada_em=datetime('now','localtime'), cotacao_autorizada_por=? WHERE id=?""",
                     (_nome_usuario(current_user), rid))
        conn.commit()
        return {"mensagem": f"Cliente autorizou: remessa {r['numero']} enviada para a Expedição."}
    finally:
        conn.close()


# ─── Expedição ──────────────────────────────────────────────────────────────

def _checar_revenda_separada(conn, rid: int):
    pend = conn.execute("""
        SELECT i.descricao FROM pedidos_remessa_itens ri
        JOIN pedidos_itens i ON i.id = ri.pedido_item_id
        LEFT JOIN estoque_produtos ep ON ep.id = i.produto_id
        LEFT JOIN estoque_categorias ec ON ec.id = ep.categoria_id
        WHERE ri.remessa_id = ? AND ec.tipo = 'revenda' AND (i.status IS NULL OR i.status != 'entregue')
    """, (rid,)).fetchone()
    if pend:
        raise HTTPException(400, f"{pend['descricao']}: separe a revenda antes de lançar a NF.")


@router.post("/{rid}/despachar")
def despachar_remessa(rid: int, body: DespachoRemessaIn, current_user: dict = Depends(get_current_user)):
    exigir_permissao("expedicao", "despachar", current_user)
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        if r["status"] not in ("aguardando_nf", "enviado"):
            raise HTTPException(400, "Esta remessa não está aguardando NF.")
        if not (body.nota_fiscal or "").strip():
            raise HTTPException(400, "Informe o número da nota fiscal.")
        if not (body.transportadora or "").strip():
            raise HTTPException(400, "Informe a transportadora.")
        _checar_revenda_separada(conn, rid)
        data = (body.data_despacho or "").strip() or datetime.datetime.now().strftime("%Y-%m-%d")
        conn.execute("""UPDATE pedidos_remessas SET status='enviado', transportadora=?, nota_fiscal=?, rastreio=?, volumes=?,
                        previsao_entrega=?, frete=?, obs_envio=?, data_despacho=?, concluido_por=?,
                        concluido_em=COALESCE(concluido_em, datetime('now','localtime')),
                        status_desde=CASE WHEN status='enviado' THEN status_desde ELSE datetime('now','localtime') END
                        WHERE id=?""",
                     (body.transportadora.strip(), body.nota_fiscal.strip(), (body.rastreio or "").strip(),
                      int(body.volumes or 0), (body.previsao_entrega or "").strip(), float(body.frete or 0),
                      (body.obs_envio or "").strip(), data, _nome_usuario(current_user), rid))
        campos = ("cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf")
        if any(getattr(body, "entrega_" + c) is not None for c in campos):
            end = {c: (getattr(body, "entrega_" + c) or "").strip() for c in campos}
            end["cep"] = "".join(ch for ch in end["cep"] if ch.isdigit())
            end["uf"] = end["uf"].upper()[:2]
            conn.execute("""UPDATE pedidos SET entrega_cep=?, entrega_logradouro=?, entrega_numero=?, entrega_complemento=?,
                            entrega_bairro=?, entrega_cidade=?, entrega_uf=? WHERE id=?""",
                         (end["cep"], end["logradouro"], end["numero"], end["complemento"], end["bairro"],
                          end["cidade"], end["uf"], r["pedido_id"]))
            if body.atualizar_cadastro_cliente:
                ped = conn.execute("SELECT cliente_id FROM pedidos WHERE id=?", (r["pedido_id"],)).fetchone()
                conn.execute("""UPDATE pedidos_clientes SET cep=?, logradouro=?, numero=?, complemento=?, bairro=?, cidade=?, uf=?
                                WHERE id=?""", (end["cep"], end["logradouro"], end["numero"], end["complemento"],
                                                end["bairro"], end["cidade"], end["uf"], ped["cliente_id"]))
        concluiu = _concluir_pedido_se_tudo_enviado(conn, r["pedido_id"], current_user)
        conn.commit()
        return {"mensagem": f"Remessa {r['numero']} despachada" + (" — pedido concluído" if concluiu else ""),
                "pedido_concluido": concluiu}
    finally:
        conn.close()


@router.post("/{rid}/retirar")
def retirar_remessa(rid: int, body: RetiradaRemessaIn, current_user: dict = Depends(get_current_user)):
    exigir_permissao("expedicao", "despachar", current_user)
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        if r["status"] != "aguardando_retirada":
            raise HTTPException(400, "Esta remessa não está aguardando retirada.")
        if not (body.nota_fiscal or "").strip():
            raise HTTPException(400, "Informe o número da nota fiscal.")
        _checar_revenda_separada(conn, rid)
        data = (body.data_retirada or "").strip() or datetime.datetime.now().strftime("%Y-%m-%d")
        conn.execute("""UPDATE pedidos_remessas SET status='retirado', nota_fiscal=?, volumes=?, obs_envio=?, data_despacho=?,
                        transportadora='Retirada pelo cliente', concluido_por=?, concluido_em=datetime('now','localtime'),
                        status_desde=datetime('now','localtime') WHERE id=?""",
                     (body.nota_fiscal.strip(), int(body.volumes or 0), (body.obs or "").strip(), data,
                      _nome_usuario(current_user), rid))
        concluiu = _concluir_pedido_se_tudo_enviado(conn, r["pedido_id"], current_user)
        conn.commit()
        return {"mensagem": f"Retirada da remessa {r['numero']} registrada" + (" — pedido concluído" if concluiu else ""),
                "pedido_concluido": concluiu}
    finally:
        conn.close()


@router.post("/{rid}/desfazer")
def desfazer_remessa(rid: int, current_user: dict = Depends(get_current_user)):
    exigir_permissao("expedicao", "desfazer", current_user)
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        if r["status"] not in STATUS_FEITAS:
            raise HTTPException(400, "Esta remessa ainda não foi concluída.")
        volta = "aguardando_nf" if r["status"] == "enviado" else "aguardando_retirada"
        conn.execute("""UPDATE pedidos_remessas SET status=?, nota_fiscal=NULL, data_despacho=NULL, concluido_por=NULL,
                        concluido_em=NULL, status_desde=datetime('now','localtime') WHERE id=?""", (volta, rid))
        _reabrir_pedido_se_concluido_por_remessas(conn, r["pedido_id"])
        conn.commit()
        return {"mensagem": f"Remessa {r['numero']} voltou para a fila da Expedição."}
    finally:
        conn.close()


# ─── PDF da NF da remessa ───────────────────────────────────────────────────

@router.post("/{rid}/nf-arquivo")
async def anexar_nf_remessa(rid: int, arquivo: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not (current_user.get("role") == "gestor" or verificar_permissao("expedicao", "despachar", current_user)):
        raise HTTPException(403, "Só a Expedição (ou o Gestor) anexa a nota fiscal.")
    dados = await arquivo.read()
    if not dados.startswith(b"%PDF"):
        raise HTTPException(400, "Envie o PDF da nota fiscal.")
    if len(dados) > NF_MAX_BYTES:
        raise HTTPException(400, "Arquivo maior que 10 MB.")
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        nome = f"{r['pedido_id']}_r{rid}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        caminho = os.path.join(_pasta_nf(), nome)
        with open(caminho, "wb") as f:
            f.write(dados)
        antigo = r["nf_arquivo"]
        conn.execute("""UPDATE pedidos_remessas SET nf_arquivo=?, nf_arquivo_nome=?, nf_arquivo_em=datetime('now','localtime'),
                        nf_arquivo_por=? WHERE id=?""",
                     (nome, (arquivo.filename or "nota-fiscal.pdf")[:120], _nome_usuario(current_user), rid))
        conn.commit()
        if antigo and antigo != nome:
            try:
                os.remove(os.path.join(_pasta_nf(), os.path.basename(antigo)))
            except OSError:
                pass
        return {"mensagem": "Nota fiscal anexada", "numero_nf": _ler_numero_nf(caminho), "nome": arquivo.filename}
    finally:
        conn.close()


@router.get("/{rid}/nf-arquivo")
def ver_nf_remessa(rid: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        ped = _pedido(conn, r["pedido_id"])
    finally:
        conn.close()
    _checar_acesso_pedido(ped, current_user)
    if not r["nf_arquivo"]:
        raise HTTPException(404, "Esta remessa ainda não tem o PDF da nota fiscal.")
    caminho = os.path.join(_pasta_nf(), os.path.basename(r["nf_arquivo"]))
    if not os.path.isfile(caminho):
        raise HTTPException(404, "Arquivo da nota fiscal não encontrado no servidor.")
    nome = f"NF-{r['nota_fiscal'] or ped['numero_pedido'] + '-R' + str(r['numero'])}.pdf"
    return FileResponse(caminho, media_type="application/pdf", filename=nome,
                        headers={"Content-Disposition": f'inline; filename="{nome}"'})


@router.delete("/{rid}/nf-arquivo")
def remover_nf_remessa(rid: int, current_user: dict = Depends(get_current_user)):
    if not (current_user.get("role") == "gestor" or verificar_permissao("expedicao", "despachar", current_user)):
        raise HTTPException(403, "Só a Expedição (ou o Gestor) remove a nota fiscal.")
    conn = get_conn()
    try:
        r = _remessa(conn, rid)
        conn.execute("UPDATE pedidos_remessas SET nf_arquivo=NULL, nf_arquivo_nome=NULL, nf_arquivo_em=NULL, nf_arquivo_por=NULL WHERE id=?", (rid,))
        conn.commit()
        if r["nf_arquivo"]:
            try:
                os.remove(os.path.join(_pasta_nf(), os.path.basename(r["nf_arquivo"])))
            except OSError:
                pass
        return {"mensagem": "PDF da nota fiscal removido"}
    finally:
        conn.close()
