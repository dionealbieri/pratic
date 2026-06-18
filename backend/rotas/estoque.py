from fastapi import APIRouter, HTTPException
import sqlite3
import re
import unicodedata
from pydantic import BaseModel
from typing import Optional
from database import get_conn

router = APIRouter()



def _prefixo_categoria(conn, categoria_id: Optional[int]) -> str:
    """Retorna 3 letras limpas da categoria em MAIÚSCULO. Ex.: Matéria Prima -> MAT."""
    nome = None
    if categoria_id:
        row = conn.execute("SELECT nome FROM estoque_categorias WHERE id=?", (categoria_id,)).fetchone()
        if row:
            nome = row["nome"]
    base = nome or "GERAL"
    sem_acento = unicodedata.normalize("NFD", str(base))
    sem_acento = "".join(ch for ch in sem_acento if unicodedata.category(ch) != "Mn")
    letras = re.sub(r"[^A-Za-z0-9]", "", sem_acento).upper()
    return (letras[:3] or "GER").ljust(3, "X")


def _proximo_codigo_automatico(conn, categoria_id: Optional[int], excluir_id: Optional[int] = None) -> str:
    """Gera código sequencial por categoria: CAT-001, CAT-002, CAT-003...

    A leitura considera códigos antigos e novos como COP001, cop-001, COP_002 ou COP 001
    para continuar a sequência sem reiniciar a contagem.
    """
    prefixo = _prefixo_categoria(conn, categoria_id)
    params = [f"{prefixo}%"]
    query = "SELECT id, codigo FROM estoque_produtos WHERE UPPER(COALESCE(codigo,'')) LIKE UPPER(?)"
    if excluir_id:
        query += " AND id<>?"
        params.append(excluir_id)
    rows = conn.execute(query, params).fetchall()

    maior = 0
    # Aceita formatos antigos e novos: COP001, COP-001-AL, COP_001, COP 001.
    padrao = re.compile(rf"^{re.escape(prefixo)}[^0-9]*(\d+)", re.IGNORECASE)
    for row in rows:
        codigo_existente = str(row["codigo"] or "").strip().upper()
        m = padrao.match(codigo_existente)
        if m:
            maior = max(maior, int(m.group(1)))

    proximo = maior + 1
    while True:
        codigo = f"{prefixo}-{proximo:03d}"
        params_check = [codigo]
        query_check = "SELECT id FROM estoque_produtos WHERE UPPER(COALESCE(codigo,'')) = UPPER(?)"
        if excluir_id:
            query_check += " AND id<>?"
            params_check.append(excluir_id)
        if not conn.execute(query_check, params_check).fetchone():
            return codigo
        proximo += 1

def _normalizar_codigo(codigo: Optional[str]) -> Optional[str]:
    if codigo is None:
        return None
    codigo = str(codigo).strip()
    return codigo.upper() or None

class CategoriaIn(BaseModel):
    nome: str
    descricao: Optional[str] = None
    tipo: Optional[str] = "producao"  # 'producao' (fabricado) ou 'revenda' (comprado pronto)

class ProdutoIn(BaseModel):
    codigo: Optional[str] = None
    categoria_id: Optional[int] = None
    nome: str
    marca: Optional[str] = None
    unidade: Optional[str] = "unidade"
    estoque_minimo: Optional[float] = 0

class MovimentacaoIn(BaseModel):
    produto_id: int
    tipo: str  # entrada, saida, perda, ajuste
    quantidade: float
    motivo: Optional[str] = None
    tipo_perda: Optional[str] = None
    responsavel: Optional[str] = None
    fornecedor: Optional[str] = None
    custo_unitario: Optional[float] = None
    observacao: Optional[str] = None
    data: Optional[str] = None

# ─── CATEGORIAS ───────────────────────────────────────────────────────────────

@router.get("/categorias")
def listar_categorias():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM estoque_categorias ORDER BY nome").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/categorias")
def criar_categoria(c: CategoriaIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO estoque_categorias (nome, descricao, tipo) VALUES (?, ?, ?)", (c.nome, c.descricao, (c.tipo or "producao")))
    conn.commit()
    id = cur.lastrowid
    conn.close()
    return {"id": id, "mensagem": "Categoria criada"}

@router.put("/categorias/{id}")
def atualizar_categoria(id: int, c: CategoriaIn):
    conn = get_conn()
    conn.execute("UPDATE estoque_categorias SET nome=?, descricao=?, tipo=? WHERE id=?", (c.nome, c.descricao, (c.tipo or "producao"), id))
    conn.commit()
    conn.close()
    return {"mensagem": "Categoria atualizada"}

@router.delete("/categorias/{id}")
def deletar_categoria(id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM estoque_categorias WHERE id=?", (id,))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Não é possível remover esta categoria, pois existem produtos vinculados a ela.")
    finally:
        conn.close()
    return {"mensagem": "Categoria removida"}

# ─── PRODUTOS ─────────────────────────────────────────────────────────────────

@router.get("/produtos")
def listar_produtos(categoria_id: Optional[int] = None):
    conn = get_conn()
    query = """
        SELECT p.*, c.nome as categoria_nome, c.tipo as categoria_tipo,
               COALESCE(e.quantidade, 0) as quantidade_atual
        FROM estoque_produtos p
        LEFT JOIN estoque_categorias c ON p.categoria_id = c.id
        LEFT JOIN estoque_saldo e ON e.produto_id = p.id
        WHERE p.ativo = 1
    """
    params = []
    if categoria_id:
        query += " AND p.categoria_id = ?"
        params.append(categoria_id)
    query += " ORDER BY c.nome, p.codigo, p.nome"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["alerta"] = d["quantidade_atual"] <= d["estoque_minimo"]
        result.append(d)
    return result

@router.post("/produtos")
def criar_produto(p: ProdutoIn):
    conn = get_conn()
    try:
        cur = conn.cursor()
        codigo = _normalizar_codigo(p.codigo)
        if not codigo:
            codigo = _proximo_codigo_automatico(conn, p.categoria_id)
        existente = conn.execute("SELECT id FROM estoque_produtos WHERE codigo=? AND ativo=1", (codigo,)).fetchone()
        if existente:
            raise HTTPException(400, "Já existe um produto ativo com este Código/ID")
        cur.execute("""INSERT INTO estoque_produtos (codigo, categoria_id, nome, marca, unidade, estoque_minimo)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (codigo, p.categoria_id, p.nome, p.marca, p.unidade, p.estoque_minimo))
        produto_id = cur.lastrowid
        cur.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, 0)", (produto_id,))
        conn.commit()
        return {"id": produto_id, "codigo": codigo, "mensagem": "Produto criado"}
    except HTTPException:
        conn.rollback()
        raise
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(400, f"Não foi possível salvar o produto. Verifique Código/ID, categoria e dados obrigatórios. Detalhe: {e}")
    finally:
        conn.close()

@router.get("/produtos/{id}")
def obter_produto(id: int):
    conn = get_conn()
    row = conn.execute("""
        SELECT p.*, c.nome as categoria_nome, c.tipo as categoria_tipo, COALESCE(e.quantidade, 0) as quantidade_atual
        FROM estoque_produtos p
        LEFT JOIN estoque_categorias c ON p.categoria_id = c.id
        LEFT JOIN estoque_saldo e ON e.produto_id = p.id
        WHERE p.id = ?
    """, (id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Produto não encontrado")
    d = dict(row)
    d["alerta"] = d["quantidade_atual"] <= d["estoque_minimo"]
    return d

@router.put("/produtos/{id}")
def atualizar_produto(id: int, p: ProdutoIn):
    conn = get_conn()
    try:
        produto = conn.execute("SELECT id FROM estoque_produtos WHERE id=?", (id,)).fetchone()
        if not produto:
            raise HTTPException(404, "Produto não encontrado")

        codigo = _normalizar_codigo(p.codigo)
        if not codigo:
            codigo = _proximo_codigo_automatico(conn, p.categoria_id, excluir_id=id)
        existente = conn.execute("SELECT id FROM estoque_produtos WHERE codigo=? AND id<>? AND ativo=1", (codigo, id)).fetchone()
        if existente:
            raise HTTPException(400, "Já existe outro produto ativo com este Código/ID")

        cur = conn.execute("""UPDATE estoque_produtos SET codigo=?, categoria_id=?, nome=?, marca=?, unidade=?, estoque_minimo=?
                            WHERE id=?""", (codigo, p.categoria_id, p.nome, p.marca, p.unidade, p.estoque_minimo, id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Produto não encontrado")
        conn.commit()
        return {"codigo": codigo, "mensagem": "Produto atualizado"}
    except HTTPException:
        conn.rollback()
        raise
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(400, f"Não foi possível atualizar o produto. Verifique se o Código/ID já existe ou se a categoria é válida. Detalhe: {e}")
    finally:
        conn.close()

@router.delete("/produtos/{id}")
def deletar_produto(id: int):
    conn = get_conn()
    conn.execute("UPDATE estoque_produtos SET ativo=0 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Produto desativado"}

# ─── MOVIMENTAÇÕES ────────────────────────────────────────────────────────────

@router.get("/movimentacoes")
def listar_movimentacoes(produto_id: Optional[int] = None, tipo: Optional[str] = None, data_inicio: Optional[str] = None, data_fim: Optional[str] = None, categoria_id: Optional[int] = None):
    conn = get_conn()
    query = """
        SELECT m.*, p.codigo as produto_codigo, p.nome as produto_nome, p.unidade,
               p.categoria_id as produto_categoria_id, cat.nome as categoria_nome
        FROM estoque_movimentacoes m
        JOIN estoque_produtos p ON m.produto_id = p.id
        LEFT JOIN estoque_categorias cat ON p.categoria_id = cat.id
        WHERE 1=1
    """
    params = []
    if produto_id:
        query += " AND m.produto_id = ?"
        params.append(produto_id)
    if tipo:
        query += " AND m.tipo = ?"
        params.append(tipo)
    if categoria_id:
        query += " AND p.categoria_id = ?"
        params.append(categoria_id)
    if data_inicio:
        query += " AND m.data >= ?"
        params.append(data_inicio)
    if data_fim:
        query += " AND m.data <= ?"
        params.append(data_fim)
    query += " ORDER BY m.data DESC, m.criado_em DESC LIMIT 200"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/movimentacoes")
def registrar_movimentacao(m: MovimentacaoIn):
    from datetime import date
    if m.tipo not in ("entrada", "saida", "perda", "ajuste", "sobra"):
        raise HTTPException(400, "Tipo inválido")
    conn = get_conn()

    saldo_row = conn.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (m.produto_id,)).fetchone()
    saldo_atual = saldo_row["quantidade"] if saldo_row else 0

    data = m.data or str(date.today())

    if m.tipo in ("entrada", "sobra"):
        novo_saldo = saldo_atual + m.quantidade
    elif m.tipo in ("saida", "perda"):
        if m.quantidade > saldo_atual:
            conn.close()
            raise HTTPException(400, f"Saldo insuficiente. Saldo atual: {saldo_atual}")
        novo_saldo = saldo_atual - m.quantidade
    elif m.tipo == "ajuste":
        novo_saldo = m.quantidade
    else:
        novo_saldo = saldo_atual

    cur = conn.cursor()
    cur.execute("""INSERT INTO estoque_movimentacoes
                   (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                    motivo, tipo_perda, responsavel, fornecedor, custo_unitario, observacao, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (m.produto_id, m.tipo, m.quantidade, saldo_atual, novo_saldo,
                 m.motivo, m.tipo_perda, m.responsavel, m.fornecedor,
                 m.custo_unitario, m.observacao, data))

    if saldo_row:
        conn.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                     (novo_saldo, m.produto_id))
    else:
        conn.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)", (m.produto_id, novo_saldo))

    conn.commit()
    id = cur.lastrowid
    conn.close()
    return {"id": id, "saldo_anterior": saldo_atual, "saldo_atual": novo_saldo, "mensagem": "Movimentação registrada"}

@router.delete("/movimentacoes/{id}")
def deletar_movimentacao(id: int):
    conn = get_conn()
    try:
        mov = conn.execute("SELECT * FROM estoque_movimentacoes WHERE id = ?", (id,)).fetchone()
        if not mov:
            raise HTTPException(404, "Movimentação não encontrada")
        
        produto_id = mov["produto_id"]
        saldo_anterior = mov["saldo_anterior"] if mov["saldo_anterior"] is not None else 0
        saldo_posterior = mov["saldo_posterior"] if mov["saldo_posterior"] is not None else 0
        diff = saldo_posterior - saldo_anterior
        
        saldo_row = conn.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id = ?", (produto_id,)).fetchone()
        saldo_atual = saldo_row["quantidade"] if saldo_row else 0
        
        novo_saldo = saldo_atual - diff
        if novo_saldo < 0:
            raise HTTPException(400, f"Não é possível excluir esta movimentação, pois o saldo do produto ficaria negativo ({novo_saldo})")
            
        conn.execute("UPDATE estoque_saldo SET quantidade = ?, ultima_atualizacao = datetime('now') WHERE produto_id = ?", (novo_saldo, produto_id))
        conn.execute("DELETE FROM estoque_movimentacoes WHERE id = ?", (id,))
        conn.commit()
        return {"mensagem": "Movimentação removida", "saldo_atual": novo_saldo}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Erro ao remover movimentação: {str(e)}")
    finally:
        conn.close()

# ─── ALERTAS ─────────────────────────────────────────────────────────────────

@router.get("/alertas")
def listar_alertas():
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.id, p.codigo, p.nome, p.marca, p.unidade, p.estoque_minimo,
               cat.nome as categoria_nome,
               COALESCE(e.quantidade, 0) as quantidade_atual
        FROM estoque_produtos p
        LEFT JOIN estoque_categorias cat ON p.categoria_id = cat.id
        LEFT JOIN estoque_saldo e ON e.produto_id = p.id
        WHERE p.ativo = 1
          AND COALESCE(e.quantidade, 0) <= p.estoque_minimo
        ORDER BY (COALESCE(e.quantidade, 0) - p.estoque_minimo) ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── RESUMO DASHBOARD ────────────────────────────────────────────────────────

@router.get("/resumo")
def resumo_estoque():
    conn = get_conn()
    total_produtos = conn.execute("SELECT COUNT(*) FROM estoque_produtos WHERE ativo=1").fetchone()[0]
    alertas = conn.execute("""
        SELECT COUNT(*) FROM estoque_produtos p
        LEFT JOIN estoque_saldo e ON e.produto_id = p.id
        WHERE p.ativo=1 AND COALESCE(e.quantidade,0) <= p.estoque_minimo
    """).fetchone()[0]
    movs_hoje = conn.execute("""
        SELECT COUNT(*) FROM estoque_movimentacoes WHERE date(data) = date('now')
    """).fetchone()[0]
    perdas_mes = conn.execute("""
        SELECT COALESCE(SUM(quantidade),0) FROM estoque_movimentacoes
        WHERE tipo='perda' AND strftime('%Y-%m', data) = strftime('%Y-%m', 'now')
    """).fetchone()[0]
    conn.close()
    return {
        "total_produtos": total_produtos,
        "alertas_minimo": alertas,
        "movimentacoes_hoje": movs_hoje,
        "perdas_mes": perdas_mes
    }

# ─── RELATÓRIO PERDAS ────────────────────────────────────────────────────────

@router.get("/relatorio-perdas")
def relatorio_perdas(mes: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT p.codigo as produto_codigo, p.nome as produto, p.unidade, cat.nome as categoria,
               m.tipo_perda, m.data, m.quantidade, m.responsavel, m.observacao
        FROM estoque_movimentacoes m
        JOIN estoque_produtos p ON m.produto_id = p.id
        LEFT JOIN estoque_categorias cat ON p.categoria_id = cat.id
        WHERE m.tipo = 'perda'
    """
    params = []
    if mes:
        query += " AND strftime('%Y-%m', m.data) = ?"
        params.append(mes)
    query += " ORDER BY m.data DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── SALDO VS DEMANDA ────────────────────────────────────────────────────────

@router.get("/saldo-vs-demanda")
def saldo_vs_demanda(categoria_id: Optional[int] = None):
    conn = get_conn()
    # Buscar todos os produtos ativos com saldo
    query = """
        SELECT 
            ep.id, ep.codigo, ep.nome, ep.marca, ep.unidade,
            ep.estoque_minimo, ec.nome as categoria_nome, ec.tipo as categoria_tipo,
            ep.categoria_id,
            COALESCE(es.quantidade, 0) as saldo_atual
        FROM estoque_produtos ep
        LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
        LEFT JOIN estoque_saldo es ON es.produto_id = ep.id
        WHERE ep.ativo = 1
    """
    params = []
    if categoria_id:
        query += " AND ep.categoria_id = ?"
        params.append(categoria_id)
    query += " ORDER BY ec.nome, ep.nome"
    produtos = conn.execute(query, params).fetchall()

    resultado = []
    for p in produtos:
        pid = p["id"]
        # Demanda: pedidos abertos e em produção
        demanda = conn.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN ped.status IN ('aberto') THEN pi.quantidade - pi.qtd_produzida ELSE 0 END), 0) as qtd_aberto,
                COALESCE(SUM(CASE WHEN ped.status = 'em_producao' THEN pi.quantidade - pi.qtd_produzida ELSE 0 END), 0) as qtd_em_producao,
                COALESCE(SUM(CASE WHEN ped.status IN ('aberto','em_producao') THEN pi.quantidade - pi.qtd_produzida ELSE 0 END), 0) as total_demanda
            FROM pedidos_itens pi
            JOIN pedidos ped ON pi.pedido_id = ped.id
            WHERE pi.produto_id = ? AND ped.status IN ('aberto','em_producao')
              AND pi.quantidade > pi.qtd_produzida
        """, (pid,)).fetchone()

        # Prazo mais urgente
        prazo_urgente = conn.execute("""
            SELECT 
                MIN(ped.prazo_entrega) as prazo_mais_urgente,
                CAST(MIN(julianday(ped.prazo_entrega) - julianday('now')) AS INTEGER) as dias_restantes
            FROM pedidos_itens pi
            JOIN pedidos ped ON pi.pedido_id = ped.id
            WHERE pi.produto_id = ? AND ped.status IN ('aberto','em_producao')
              AND pi.quantidade > pi.qtd_produzida
        """, (pid,)).fetchone()

        saldo = p["saldo_atual"]
        total_demanda = demanda["total_demanda"] or 0
        saldo_projetado = saldo - total_demanda
        cobertura = round((saldo / total_demanda * 100), 1) if total_demanda > 0 else 100

        if total_demanda == 0:
            situacao = "sem_demanda"
        elif saldo_projetado < 0 or cobertura < 20:
            situacao = "critico"
        elif cobertura < 50:
            situacao = "atencao"
        else:
            situacao = "ok"

        resultado.append({
            "id": pid,
            "codigo": p["codigo"],
            "nome": p["nome"],
            "marca": p["marca"],
            "unidade": p["unidade"],
            "categoria": p["categoria_nome"] or "—",
            "categoria_id": p["categoria_id"],
            "categoria_tipo": p["categoria_tipo"] or "producao",
            "estoque_minimo": p["estoque_minimo"],
            "saldo_atual": saldo,
            "qtd_aberto": demanda["qtd_aberto"] or 0,
            "qtd_em_producao": demanda["qtd_em_producao"] or 0,
            "total_demanda": total_demanda,
            "saldo_projetado": saldo_projetado,
            "cobertura": cobertura,
            "situacao": situacao,
            "prazo_urgente": prazo_urgente["prazo_mais_urgente"],
            "dias_urgente": int(prazo_urgente["dias_restantes"]) if prazo_urgente["dias_restantes"] is not None else None,
        })

    conn.close()
    return resultado

@router.get("/saldo-vs-demanda/{produto_id}/pedidos")
def detalhe_produto_pedidos(produto_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT 
            ped.numero_pedido, ped.prazo_entrega, ped.status,
            pc.razao_social as cliente,
            pi.descricao, pi.quantidade, pi.qtd_produzida, pi.unidade,
            pi.quantidade - pi.qtd_produzida as saldo_item,
            CAST(julianday(ped.prazo_entrega) - julianday('now') AS INTEGER) as dias_restantes
        FROM pedidos_itens pi
        JOIN pedidos ped ON pi.pedido_id = ped.id
        LEFT JOIN pedidos_clientes pc ON ped.cliente_id = pc.id
        WHERE pi.produto_id = ? AND ped.status IN ('aberto','em_producao')
          AND pi.quantidade > pi.qtd_produzida
        ORDER BY ped.prazo_entrega ASC
    """, (produto_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
