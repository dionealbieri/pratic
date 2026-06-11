from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_conn

router = APIRouter()

class ProducaoIn(BaseModel):
    colaborador_id: int
    maquina_id: int
    data: str
    meta: float
    producao: float
    produto_estoque_id: Optional[int] = None
    perda_quantidade: Optional[float] = 0
    perda_tipo: Optional[str] = None
    perda_observacao: Optional[str] = None
    sobra_quantidade: Optional[float] = 0
    pedido_id: Optional[int] = None
    pedido_numero: Optional[str] = None

@router.get("/")
def listar(mes: Optional[str] = None, colaborador_id: Optional[int] = None):
    conn = get_conn()
    query = """
        SELECT p.*, c.nome as colaborador_nome, m.nome as maquina_nome
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        JOIN maquinas m ON p.maquina_id = m.id
        WHERE 1=1
    """
    params = []
    if mes:
        query += " AND p.mes_referencia = ?"
        params.append(mes)
    if colaborador_id:
        query += " AND p.colaborador_id = ?"
        params.append(colaborador_id)
    query += " ORDER BY p.data DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/")
def registrar(p: ProducaoIn):
    excedente = (p.producao - p.meta) if p.producao > 0 else 0
    mes = p.data[:7]
    conn = get_conn()

    # Verificar duplicata apenas se o mesmo produto for lançado duas vezes no mesmo dia
    # Permite múltiplos produtos diferentes no mesmo dia (novo comportamento do modal)
    if p.produto_estoque_id:
        existe = conn.execute("""
            SELECT id FROM producao_diaria 
            WHERE colaborador_id=? AND data=? AND produto_estoque_id=?
        """, (p.colaborador_id, p.data, p.produto_estoque_id)).fetchone()
        if existe:
            conn.close()
            raise HTTPException(400, "Já existe produção lançada para este colaborador com este produto nesta data")

    c = conn.cursor()

    # Buscar nome do colaborador para registrar nas perdas
    col = conn.execute("SELECT nome FROM colaboradores WHERE id=?", (p.colaborador_id,)).fetchone()
    col_nome = col["nome"] if col else "Operador"

    c.execute("""INSERT INTO producao_diaria 
                 (colaborador_id, maquina_id, data, mes_referencia, meta, producao, excedente, produto_estoque_id, perda_quantidade, sobra_quantidade, pedido_numero)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (p.colaborador_id, p.maquina_id, p.data, mes, p.meta, p.producao, excedente,
               p.produto_estoque_id, p.perda_quantidade or 0, p.sobra_quantidade or 0, p.pedido_numero))
    prod_id = c.lastrowid
    perda = p.perda_quantidade or 0

    # ── Baixa no estoque se produto vinculado
    if p.produto_estoque_id and p.producao > 0:
        saldo = conn.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?",
                             (p.produto_estoque_id,)).fetchone()
        saldo_atual = saldo["quantidade"] if saldo else 0
        consumo = p.producao
        total_baixa = consumo + perda
        novo_saldo = max(0, saldo_atual - total_baixa)

        # Saída da produção
        c.execute("""INSERT INTO estoque_movimentacoes
                     (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, responsavel, data)
                     VALUES (?, 'saida', ?, ?, ?, 'Produção diária automática', ?, ?)""",
                  (p.produto_estoque_id, consumo, saldo_atual, saldo_atual - consumo, col_nome, p.data))

        saldo_apos_consumo = saldo_atual - consumo

        # Sobra vinculada ao estoque (volta ao saldo)
        sobra = p.sobra_quantidade or 0
        if sobra > 0:
            c.execute("""INSERT INTO estoque_movimentacoes
                         (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                          motivo, responsavel, data)
                         VALUES (?, 'sobra', ?, ?, ?, 'Sobra de produção', ?, ?)""",
                      (p.produto_estoque_id, sobra,
                       saldo_atual - consumo,
                       saldo_atual - consumo + sobra,
                       col_nome, p.data))
            novo_saldo = novo_saldo + sobra

        # Perda vinculada ao estoque
        if perda > 0:
            c.execute("""INSERT INTO estoque_movimentacoes
                         (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                          motivo, tipo_perda, responsavel, observacao, data)
                         VALUES (?, 'perda', ?, ?, ?, 'Perda na produção', ?, ?, ?, ?)""",
                      (p.produto_estoque_id, perda, saldo_apos_consumo, novo_saldo,
                       p.perda_tipo or 'quebra', col_nome, p.perda_observacao, p.data))

        # Atualizar saldo
        if saldo:
            conn.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                         (novo_saldo, p.produto_estoque_id))
        else:
            conn.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)",
                         (p.produto_estoque_id, novo_saldo))

    # ── Registrar perda mesmo sem estoque vinculado
    elif perda > 0:
        # Tenta encontrar qualquer produto cadastrado para registrar a perda
        # Se não tiver produto, registra só na producao_diaria (já salvo acima)
        primeiro_produto = conn.execute(
            "SELECT id FROM estoque_produtos WHERE ativo=1 LIMIT 1"
        ).fetchone()
        if primeiro_produto:
            saldo = conn.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?",
                                 (primeiro_produto["id"],)).fetchone()
            saldo_atual = saldo["quantidade"] if saldo else 0
            novo_saldo = max(0, saldo_atual - perda)
            c.execute("""INSERT INTO estoque_movimentacoes
                         (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                          motivo, tipo_perda, responsavel, observacao, data)
                         VALUES (?, 'perda', ?, ?, ?, 'Perda registrada via mobile', ?, ?, ?, ?)""",
                      (primeiro_produto["id"], perda, saldo_atual, novo_saldo,
                       p.perda_tipo or 'quebra', col_nome, p.perda_observacao, p.data))
            if saldo:
                conn.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                             (novo_saldo, primeiro_produto["id"]))

    conn.commit()
    conn.close()
    return {"id": prod_id, "excedente": excedente, "mensagem": "Produção registrada com sucesso"}

def _reverter_estoque_producao(conn, prod_id: int):
    p = conn.execute("SELECT * FROM producao_diaria WHERE id = ?", (prod_id,)).fetchone()
    if not p:
        return
    
    colaborador_id = p["colaborador_id"]
    data = p["data"]
    
    col = conn.execute("SELECT nome FROM colaboradores WHERE id = ?", (colaborador_id,)).fetchone()
    col_nome = col["nome"] if col else "Operador"
    
    motivos = ('Produção diária automática', 'Sobra de produção', 'Perda na produção', 'Perda registrada via mobile')
    
    query = """
        SELECT * FROM estoque_movimentacoes 
        WHERE data = ? 
          AND responsavel = ? 
          AND motivo IN (?, ?, ?, ?)
    """
    movs = conn.execute(query, (data, col_nome, *motivos)).fetchall()
    
    for m in movs:
        m_id = m["id"]
        m_prod_id = m["produto_id"]
        m_tipo = m["tipo"]
        m_qtd = m["quantidade"]
        
        diff = 0
        if m_tipo in ("entrada", "sobra"):
            diff = m_qtd
        elif m_tipo in ("saida", "perda"):
            diff = -m_qtd
            
        saldo_row = conn.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id = ?", (m_prod_id,)).fetchone()
        saldo_atual = saldo_row["quantidade"] if saldo_row else 0
        novo_saldo = max(0, saldo_atual - diff)
        
        conn.execute("UPDATE estoque_saldo SET quantidade = ?, ultima_atualizacao = datetime('now') WHERE produto_id = ?", (novo_saldo, m_prod_id))
        conn.execute("DELETE FROM estoque_movimentacoes WHERE id = ?", (m_id,))

@router.put("/{id}")
def atualizar(id: int, p: ProducaoIn):
    conn = get_conn()
    try:
        cur = conn.cursor()
        existe = cur.execute("SELECT id FROM producao_diaria WHERE id = ?", (id,)).fetchone()
        if not existe:
            raise HTTPException(404, "Registro de produção não encontrado")
            
        # 1. Reverter estoque antigo
        _reverter_estoque_producao(cur, id)
        
        # 2. Atualizar registro de produção
        excedente = (p.producao - p.meta) if p.producao > 0 else 0
        mes = p.data[:7]
        cur.execute("""UPDATE producao_diaria 
                        SET colaborador_id=?, maquina_id=?, data=?, mes_referencia=?, 
                            meta=?, producao=?, excedente=?, produto_estoque_id=?, perda_quantidade=?, sobra_quantidade=?, pedido_numero=?
                        WHERE id=?""",
                     (p.colaborador_id, p.maquina_id, p.data, mes, p.meta, p.producao, excedente,
                      p.produto_estoque_id, p.perda_quantidade or 0, p.sobra_quantidade or 0, p.pedido_numero, id))
                      
        # 3. Registrar novos movimentos de estoque
        col = cur.execute("SELECT nome FROM colaboradores WHERE id=?", (p.colaborador_id,)).fetchone()
        col_nome = col["nome"] if col else "Operador"
        perda = p.perda_quantidade or 0
        
        if p.produto_estoque_id and p.producao > 0:
            saldo = cur.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?",
                                 (p.produto_estoque_id,)).fetchone()
            saldo_atual = saldo["quantidade"] if saldo else 0
            consumo = p.producao
            total_baixa = consumo + perda
            novo_saldo = max(0, saldo_atual - total_baixa)
    
            cur.execute("""INSERT INTO estoque_movimentacoes
                         (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, responsavel, data)
                         VALUES (?, 'saida', ?, ?, ?, 'Produção diária automática', ?, ?)""",
                      (p.produto_estoque_id, consumo, saldo_atual, saldo_atual - consumo, col_nome, p.data))
    
            saldo_apos_consumo = saldo_atual - consumo
    
            sobra = p.sobra_quantidade or 0
            if sobra > 0:
                cur.execute("""INSERT INTO estoque_movimentacoes
                             (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                              motivo, responsavel, data)
                             VALUES (?, 'sobra', ?, ?, ?, 'Sobra de produção', ?, ?)""",
                          (p.produto_estoque_id, sobra,
                           saldo_atual - consumo,
                           saldo_atual - consumo + sobra,
                           col_nome, p.data))
                novo_saldo = novo_saldo + sobra
    
            if perda > 0:
                cur.execute("""INSERT INTO estoque_movimentacoes
                             (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                              motivo, tipo_perda, responsavel, observacao, data)
                             VALUES (?, 'perda', ?, ?, ?, 'Perda na produção', ?, ?, ?, ?)""",
                          (p.produto_estoque_id, perda, saldo_apos_consumo, novo_saldo,
                           p.perda_tipo or 'quebra', col_nome, p.perda_observacao, p.data))
    
            if saldo:
                cur.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                             (novo_saldo, p.produto_estoque_id))
            else:
                cur.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)",
                             (p.produto_estoque_id, novo_saldo))
    
        elif perda > 0:
            primeiro_produto = cur.execute(
                "SELECT id FROM estoque_produtos WHERE ativo=1 LIMIT 1"
            ).fetchone()
            if primeiro_produto:
                saldo = cur.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?",
                                     (primeiro_produto["id"],)).fetchone()
                saldo_atual = saldo["quantidade"] if saldo else 0
                novo_saldo = max(0, saldo_atual - perda)
                cur.execute("""INSERT INTO estoque_movimentacoes
                             (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                              motivo, tipo_perda, responsavel, observacao, data)
                             VALUES (?, 'perda', ?, ?, ?, 'Perda registrada via mobile', ?, ?, ?, ?)""",
                          (primeiro_produto["id"], perda, saldo_atual, novo_saldo,
                           p.perda_tipo or 'quebra', col_nome, p.perda_observacao, p.data))
                if saldo:
                    cur.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                                 (novo_saldo, primeiro_produto["id"]))
                                 
        conn.commit()
        return {"mensagem": "Produção atualizada com sucesso"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Erro ao atualizar produção: {str(e)}")
    finally:
        conn.close()

@router.delete("/{id}")
def deletar(id: int):
    conn = get_conn()
    try:
        cur = conn.cursor()
        existe = cur.execute("SELECT id FROM producao_diaria WHERE id = ?", (id,)).fetchone()
        if not existe:
            raise HTTPException(404, "Registro de produção não encontrado")
            
        # 1. Reverter e deletar lançamentos de estoque
        _reverter_estoque_producao(cur, id)
        
        # 2. Deletar registro de produção
        cur.execute("DELETE FROM producao_diaria WHERE id = ?", (id,))
        conn.commit()
        return {"mensagem": "Registro removido com sucesso"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Erro ao remover produção: {str(e)}")
    finally:
        conn.close()

@router.get("/meses")
def listar_meses():
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT mes_referencia FROM producao_diaria
        ORDER BY mes_referencia DESC
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]

@router.get("/resumo/{mes}")
def resumo_mes(mes: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT 
            c.id as colaborador_id,
            c.nome as colaborador,
            c.tipo,
            COUNT(CASE WHEN p.producao > 0 THEN 1 END) as dias_trabalhados,
            SUM(p.producao) as total_producao,
            CASE WHEN COUNT(CASE WHEN p.producao > 0 THEN 1 END) > 0
                 THEN SUM(CASE WHEN p.producao > 0 THEN p.producao ELSE 0 END) / COUNT(CASE WHEN p.producao > 0 THEN 1 END)
                 ELSE 0 END as media_diaria,
            SUM(p.excedente) as excedente_total,
            SUM(p.perda_quantidade) as total_perdas,
            p.meta as meta
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE p.mes_referencia = ?
        GROUP BY c.id
        ORDER BY media_diaria DESC
    """, (mes,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["elegivel"] = (d["media_diaria"] or 0) >= (d["meta"] or 8000)
        result.append(d)
    return result
