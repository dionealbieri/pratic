from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from database import get_conn
import httpx

router = APIRouter()

class ClienteIn(BaseModel):
    cnpj: Optional[str] = None
    razao_social: str
    nome_fantasia: Optional[str] = None
    ie: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    observacoes: Optional[str] = None

class ItemPedidoIn(BaseModel):
    produto_id: Optional[int] = None
    descricao: str
    quantidade: float
    unidade: Optional[str] = "unidade"

class PedidoIn(BaseModel):
    numero_pedido: str
    cliente_id: int
    prazo_entrega: str
    vendedor: Optional[str] = None
    observacoes: Optional[str] = None
    itens: List[ItemPedidoIn] = []

class StatusItemIn(BaseModel):
    status: str
    qtd_produzida: Optional[float] = None

# ─── BUSCA CNPJ ──────────────────────────────────────────────────────────────

@router.get("/busca-cnpj/{cnpj}")
async def buscar_cnpj(cnpj: str):
    cnpj_limpo = ''.join(filter(str.isdigit, cnpj))
    if len(cnpj_limpo) != 14:
        raise HTTPException(400, "CNPJ inválido")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_limpo}")
            data = r.json()
            if data.get("status") == "ERROR":
                raise HTTPException(404, data.get("message", "CNPJ não encontrado"))
            return {
                "cnpj": cnpj_limpo,
                "razao_social": data.get("nome", ""),
                "nome_fantasia": data.get("fantasia", ""),
                "email": data.get("email", ""),
                "telefone": data.get("telefone", ""),
                "cep": data.get("cep", "").replace(".", "").replace("-", "").replace(" ", ""),
                "logradouro": data.get("logradouro", ""),
                "numero": data.get("numero", ""),
                "complemento": data.get("complemento", ""),
                "bairro": data.get("bairro", ""),
                "cidade": data.get("municipio", ""),
                "uf": data.get("uf", ""),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar CNPJ: {str(e)}")

@router.get("/busca-cep/{cep}")
async def buscar_cep(cep: str):
    cep_limpo = ''.join(filter(str.isdigit, cep))
    if len(cep_limpo) != 8:
        raise HTTPException(400, "CEP inválido")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://viacep.com.br/ws/{cep_limpo}/json/")
            data = r.json()
            if data.get("erro"):
                raise HTTPException(404, "CEP não encontrado")
            return {
                "cep": cep_limpo,
                "logradouro": data.get("logradouro", ""),
                "bairro": data.get("bairro", ""),
                "cidade": data.get("localidade", ""),
                "uf": data.get("uf", ""),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar CEP: {str(e)}")

# ─── CLIENTES ─────────────────────────────────────────────────────────────────

@router.get("/clientes")
def listar_clientes(busca: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT c.*,
               COUNT(p.id) as total_pedidos,
               MAX(p.created_at) as ultimo_pedido
        FROM pedidos_clientes c
        LEFT JOIN pedidos p ON p.cliente_id = c.id
        WHERE c.ativo = 1
    """
    params = []
    if busca:
        query += " AND (c.razao_social LIKE ? OR c.nome_fantasia LIKE ? OR c.cnpj LIKE ?)"
        params += [f"%{busca}%", f"%{busca}%", f"%{busca}%"]
    query += " GROUP BY c.id ORDER BY c.razao_social"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/clientes/{id}")
def buscar_cliente(id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM pedidos_clientes WHERE id=?", (id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Cliente não encontrado")
    return dict(row)

@router.post("/clientes")
def criar_cliente(c: ClienteIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO pedidos_clientes
        (cnpj, razao_social, nome_fantasia, ie, email, telefone,
         cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (c.cnpj, c.razao_social, c.nome_fantasia, c.ie, c.email, c.telefone,
         c.cep, c.logradouro, c.numero, c.complemento, c.bairro, c.cidade, c.uf, c.observacoes))
    conn.commit()
    id = cur.lastrowid
    conn.close()
    return {"id": id, "mensagem": "Cliente cadastrado"}

@router.put("/clientes/{id}")
def atualizar_cliente(id: int, c: ClienteIn):
    conn = get_conn()
    conn.execute("""UPDATE pedidos_clientes SET
        cnpj=?, razao_social=?, nome_fantasia=?, ie=?, email=?, telefone=?,
        cep=?, logradouro=?, numero=?, complemento=?, bairro=?, cidade=?, uf=?, observacoes=?
        WHERE id=?""",
        (c.cnpj, c.razao_social, c.nome_fantasia, c.ie, c.email, c.telefone,
         c.cep, c.logradouro, c.numero, c.complemento, c.bairro, c.cidade, c.uf, c.observacoes, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Cliente atualizado"}

@router.delete("/clientes/{id}")
def deletar_cliente(id: int):
    conn = get_conn()
    conn.execute("UPDATE pedidos_clientes SET ativo=0 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Cliente desativado"}

# ─── PEDIDOS ──────────────────────────────────────────────────────────────────

@router.get("/")
def listar_pedidos(status: Optional[str] = None, cliente_id: Optional[int] = None):
    conn = get_conn()
    query = """
        SELECT p.*,
               c.razao_social as cliente_nome,
               c.nome_fantasia,
               COUNT(i.id) as total_itens,
               COUNT(CASE WHEN i.status = 'entregue' THEN 1 END) as itens_entregues,
               julianday(p.prazo_entrega) - julianday('now') as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        LEFT JOIN pedidos_itens i ON i.pedido_id = p.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND p.status = ?"
        params.append(status)
    if cliente_id:
        query += " AND p.cliente_id = ?"
        params.append(cliente_id)
    query += " GROUP BY p.id ORDER BY p.prazo_entrega ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{id}")
def buscar_pedido(id: int):
    conn = get_conn()
    pedido = conn.execute("""
        SELECT p.*, c.razao_social as cliente_nome, c.nome_fantasia,
               julianday(p.prazo_entrega) - julianday('now') as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.id=?
    """, (id,)).fetchone()
    if not pedido:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    itens = conn.execute("""
        SELECT i.*, ep.nome as produto_nome
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
        WHERE i.pedido_id=?
        ORDER BY i.id
    """, (id,)).fetchall()
    conn.close()
    result = dict(pedido)
    result["itens"] = [dict(i) for i in itens]
    return result

@router.post("/")
def criar_pedido(p: PedidoIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO pedidos
        (numero_pedido, cliente_id, prazo_entrega, vendedor, observacoes, status)
        VALUES (?,?,?,?,?,'aberto')""",
        (p.numero_pedido, p.cliente_id, p.prazo_entrega, p.vendedor, p.observacoes))
    pedido_id = cur.lastrowid
    for item in p.itens:
        cur.execute("""INSERT INTO pedidos_itens
            (pedido_id, produto_id, descricao, quantidade, unidade, qtd_produzida, status)
            VALUES (?,?,?,?,?,0,'aberto')""",
            (pedido_id, item.produto_id, item.descricao, item.quantidade, item.unidade))
    conn.commit()
    conn.close()
    return {"id": pedido_id, "mensagem": "Pedido criado"}

@router.put("/{id}")
def atualizar_pedido(id: int, p: PedidoIn):
    conn = get_conn()
    conn.execute("""UPDATE pedidos SET
        numero_pedido=?, cliente_id=?, prazo_entrega=?, vendedor=?, observacoes=?
        WHERE id=?""",
        (p.numero_pedido, p.cliente_id, p.prazo_entrega, p.vendedor, p.observacoes, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Pedido atualizado"}

@router.put("/{id}/status")
def atualizar_status_pedido(id: int, body: StatusItemIn):
    validos = ["aberto", "em_producao", "produzido", "entregue"]
    if body.status not in validos:
        raise HTTPException(400, f"Status inválido. Use: {validos}")
    conn = get_conn()
    conn.execute("UPDATE pedidos SET status=? WHERE id=?", (body.status, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Status atualizado"}

@router.delete("/{id}")
def deletar_pedido(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM pedidos_itens WHERE pedido_id=?", (id,))
    conn.execute("DELETE FROM pedidos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Pedido removido"}

# ─── ITENS ────────────────────────────────────────────────────────────────────

@router.put("/itens/{id}/status")
def atualizar_status_item(id: int, body: StatusItemIn):
    validos = ["aberto", "em_producao", "produzido", "entregue"]
    if body.status not in validos:
        raise HTTPException(400, f"Status inválido. Use: {validos}")
    conn = get_conn()
    cur = conn.cursor()
    if body.qtd_produzida is not None:
        cur.execute("UPDATE pedidos_itens SET status=?, qtd_produzida=? WHERE id=?",
                    (body.status, body.qtd_produzida, id))
    else:
        cur.execute("UPDATE pedidos_itens SET status=? WHERE id=?", (body.status, id))

    # Recalcular status do pedido pai
    item = cur.execute("SELECT pedido_id FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if item:
        pid = item["pedido_id"]
        counts = cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status='entregue' THEN 1 END) as entregues,
                COUNT(CASE WHEN status='produzido' THEN 1 END) as produzidos,
                COUNT(CASE WHEN status='em_producao' THEN 1 END) as em_prod
            FROM pedidos_itens WHERE pedido_id=?
        """, (pid,)).fetchone()
        if counts["total"] == counts["entregues"]:
            novo_status = "entregue"
        elif counts["produzidos"] + counts["entregues"] == counts["total"]:
            novo_status = "produzido"
        elif counts["em_prod"] > 0:
            novo_status = "em_producao"
        else:
            novo_status = "aberto"
        cur.execute("UPDATE pedidos SET status=? WHERE id=?", (novo_status, pid))

    conn.commit()
    conn.close()
    return {"mensagem": "Item atualizado"}

@router.delete("/itens/{id}")
def deletar_item(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM pedidos_itens WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Item removido"}

# ─── ALERTAS ─────────────────────────────────────────────────────────────────

@router.get("/alertas/resumo")
def alertas_pedidos():
    conn = get_conn()
    vencidos = conn.execute("""
        SELECT COUNT(*) FROM pedidos
        WHERE status NOT IN ('entregue')
        AND julianday(prazo_entrega) < julianday('now')
    """).fetchone()[0]
    urgentes = conn.execute("""
        SELECT COUNT(*) FROM pedidos
        WHERE status NOT IN ('entregue')
        AND julianday(prazo_entrega) - julianday('now') BETWEEN 0 AND 3
    """).fetchone()[0]
    em_aberto = conn.execute("""
        SELECT COUNT(*) FROM pedidos WHERE status = 'aberto'
    """).fetchone()[0]
    rows = conn.execute("""
        SELECT p.numero_pedido, c.razao_social as cliente,
               p.prazo_entrega, p.status,
               CAST(julianday(p.prazo_entrega) - julianday('now') AS INTEGER) as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.status NOT IN ('entregue')
        AND julianday(p.prazo_entrega) - julianday('now') <= 3
        ORDER BY p.prazo_entrega ASC
        LIMIT 5
    """).fetchall()
    conn.close()
    return {
        "vencidos": vencidos,
        "urgentes": urgentes,
        "em_aberto": em_aberto,
        "lista_urgentes": [dict(r) for r in rows]
    }

# ─── FILA PRODUÇÃO ───────────────────────────────────────────────────────────

@router.get("/fila/producao")
def fila_producao(status: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT i.*,
               p.numero_pedido, p.prazo_entrega, p.vendedor,
               c.razao_social as cliente_nome,
               CAST(julianday(p.prazo_entrega) - julianday('now') AS INTEGER) as dias_restantes,
               ep.nome as produto_nome_estoque
        FROM pedidos_itens i
        JOIN pedidos p ON i.pedido_id = p.id
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
        WHERE p.status NOT IN ('entregue')
    """
    params = []
    if status:
        query += " AND i.status = ?"
        params.append(status)
    query += " ORDER BY p.prazo_entrega ASC, i.id ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
