from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_conn

router = APIRouter()

class PremiacaoAuxiliarIn(BaseModel):
    colaborador_id: int
    mes_referencia: str
    posicao: int
    valor_bonus: float
    observacao: Optional[str] = None

@router.get("/operadores/{mes}")
def premiacao_operadores(mes: str):
    conn = get_conn()

    configs = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()
    cfg = {}
    for r in configs:
        try:
            cfg[r["chave"]] = float(r["valor"])
        except (ValueError, TypeError):
            pass
    premio_1 = cfg.get("valor_premio_operador_1", cfg.get("valor_premio_operador", 300.0))
    premio_2 = cfg.get("valor_premio_operador_2", cfg.get("valor_premio_operador", 200.0))
    premios_por_posicao = {1: premio_1, 2: premio_2}

    rows = conn.execute("""
        SELECT 
            c.id as colaborador_id,
            c.nome as colaborador,
            COUNT(CASE WHEN p.producao > 0 THEN 1 END) as dias_trabalhados,
            SUM(CASE WHEN p.producao > 0 THEN p.producao ELSE 0 END) as total_producao,
            AVG(CASE WHEN p.producao > 0 THEN p.producao ELSE NULL END) as media_diaria,
            SUM(p.excedente) as excedente_total,
            p.meta as meta
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE p.mes_referencia = ? AND c.tipo = 'operador'
        GROUP BY c.id
        ORDER BY total_producao DESC
    """, (mes,)).fetchall()
    conn.close()

    result = []
    ranking = 1
    for r in rows:
        d = dict(r)
        media = d["media_diaria"] or 0
        d["elegivel"] = media >= (d["meta"] or 8000)
        valor = premios_por_posicao.get(ranking, premio_2) if d["elegivel"] else 0
        d["valor_premio"] = valor
        d["ranking"] = ranking
        ranking += 1
        result.append(d)
    return result

@router.get("/auxiliares/{mes}")
def premiacao_auxiliares(mes: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT pa.*, c.nome as colaborador_nome
        FROM premiacao_auxiliar pa
        JOIN colaboradores c ON pa.colaborador_id = c.id
        WHERE pa.mes_referencia = ?
        ORDER BY pa.posicao
    """, (mes,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/auxiliares")
def registrar_auxiliar(p: PremiacaoAuxiliarIn):
    conn = get_conn()
    existe = conn.execute(
        "SELECT id FROM premiacao_auxiliar WHERE colaborador_id=? AND mes_referencia=?",
        (p.colaborador_id, p.mes_referencia)
    ).fetchone()
    if existe:
        conn.execute("""UPDATE premiacao_auxiliar 
                        SET posicao=?, valor_bonus=?, observacao=?
                        WHERE colaborador_id=? AND mes_referencia=?""",
                     (p.posicao, p.valor_bonus, p.observacao, p.colaborador_id, p.mes_referencia))
    else:
        conn.execute("""INSERT INTO premiacao_auxiliar 
                        (colaborador_id, mes_referencia, posicao, valor_bonus, observacao)
                        VALUES (?, ?, ?, ?, ?)""",
                     (p.colaborador_id, p.mes_referencia, p.posicao, p.valor_bonus, p.observacao))
    conn.commit()
    conn.close()
    return {"mensagem": "Premiação de auxiliar registrada"}

@router.delete("/auxiliares/{id}")
def remover_auxiliar(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM premiacao_auxiliar WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Premiação removida"}

@router.get("/dashboard/{mes}")
def dashboard(mes: str):
    conn = get_conn()
    configs = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()
    cfg = {}
    for r in configs:
        try:
            cfg[r["chave"]] = float(r["valor"])
        except (ValueError, TypeError):
            pass
    premio_1 = cfg.get("valor_premio_operador_1", cfg.get("valor_premio_operador", 300.0))
    premio_2 = cfg.get("valor_premio_operador_2", cfg.get("valor_premio_operador", 200.0))
    premios_por_posicao = {1: premio_1, 2: premio_2}

    operadores = conn.execute("""
        SELECT 
            c.id as colaborador_id,
            c.nome as colaborador,
            COUNT(CASE WHEN p.producao > 0 THEN 1 END) as dias_trabalhados,
            SUM(p.producao) as total_producao,
            AVG(CASE WHEN p.producao > 0 THEN p.producao ELSE NULL END) as media_diaria,
            SUM(p.excedente) as excedente_total,
            p.meta as meta
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE p.mes_referencia = ? AND c.tipo = 'operador'
        GROUP BY c.id
        ORDER BY total_producao DESC
    """, (mes,)).fetchall()

    auxiliares = conn.execute("""
        SELECT pa.*, c.nome as colaborador_nome
        FROM premiacao_auxiliar pa
        JOIN colaboradores c ON pa.colaborador_id = c.id
        WHERE pa.mes_referencia = ?
        ORDER BY pa.posicao
    """, (mes,)).fetchall()

    total_dias = conn.execute("""
        SELECT COUNT(DISTINCT data) FROM producao_diaria WHERE mes_referencia = ?
    """, (mes,)).fetchone()[0]

    # ─── NOVAS MÉTRICAS OPERACIONAIS E GRÁFICOS
    import datetime
    hoje = datetime.date.today().isoformat()
    
    # 1. Total Perdas e Sobras Geral no mês
    perdas_sobras_row = conn.execute("""
        SELECT COALESCE(SUM(perda_quantidade), 0) as perdas,
               COALESCE(SUM(sobra_quantidade), 0) as sobras
        FROM producao_diaria
        WHERE mes_referencia = ?
    """, (mes,)).fetchone()
    total_perdas_geral = perdas_sobras_row["perdas"]
    total_sobras_geral = perdas_sobras_row["sobras"]
    
    # 2. Custo Financeiro Estimado das Perdas no mês (obtido de estoque_movimentacoes)
    custo_perdas_row = conn.execute("""
        SELECT COALESCE(SUM(quantidade * COALESCE(custo_unitario, 0.0)), 0.0) as custo
        FROM estoque_movimentacoes
        WHERE tipo = 'perda' AND strftime('%Y-%m', data) = ?
    """, (mes,)).fetchone()
    custo_perdas_geral = custo_perdas_row["custo"]
    
    # 3. Aderência à Meta
    dias_meta = conn.execute("""
        SELECT 
            COUNT(*) as total_dias,
            COUNT(CASE WHEN producao >= meta THEN 1 END) as batidas
        FROM producao_diaria
        WHERE mes_referencia = ? AND producao > 0
    """, (mes,)).fetchone()
    total_dias_meta = dias_meta["total_dias"]
    dias_meta_batidas = dias_meta["batidas"]
    aderencia_meta_percentual = round((dias_meta_batidas / total_dias_meta * 100), 1) if total_dias_meta > 0 else 0.0
    
    # 4. Pedidos Pendentes e Atrasados
    pedidos_pendentes = conn.execute("SELECT COUNT(*) FROM pedidos WHERE status != 'entregue'").fetchone()[0]
    pedidos_atrasados = conn.execute("SELECT COUNT(*) FROM pedidos WHERE status != 'entregue' AND prazo_entrega < ?", (hoje,)).fetchone()[0]
    
    # 5. Lista de Pedidos Críticos (Atrasados ou vencendo nos próximos 3 dias, não entregues)
    pedidos_criticos_rows = conn.execute("""
        SELECT p.numero_pedido, c.razao_social as cliente_nome, p.prazo_entrega, p.status,
               CAST(julianday(p.prazo_entrega) - julianday(?) AS INTEGER) as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.status != 'entregue'
          AND (p.prazo_entrega < ? OR julianday(p.prazo_entrega) - julianday(?) <= 3)
        ORDER BY p.prazo_entrega ASC
        LIMIT 5
    """, (hoje, hoje, hoje)).fetchall()
    pedidos_criticos_list = [dict(r) for r in pedidos_criticos_rows]
    
    # 6. EPIs Vencidos
    epi_vencidos_count = conn.execute("SELECT COUNT(*) FROM epi_entregas WHERE status = 'ativo' AND data_validade < ?", (hoje,)).fetchone()[0]
    
    # Lista de EPIs vencidos/vencendo em 3 dias
    epi_criticos_rows = conn.execute("""
        SELECT ee.id, c.nome as colaborador_nome, e.nome as epi_nome, ee.data_validade,
               CAST(julianday(ee.data_validade) - julianday(?) AS INTEGER) as dias_restantes
        FROM epi_entregas ee
        JOIN colaboradores c ON ee.colaborador_id = c.id
        JOIN epis e ON ee.epi_id = e.id
        WHERE ee.status = 'ativo'
          AND (ee.data_validade < ? OR julianday(ee.data_validade) - julianday(?) <= 3)
        ORDER BY ee.data_validade ASC
        LIMIT 5
    """, (hoje, hoje, hoje)).fetchall()
    epi_criticos_list = [dict(r) for r in epi_criticos_rows]
    
    # 7. Insumos Críticos
    estoque_alertas_count = conn.execute("""
        SELECT COUNT(*) FROM estoque_produtos p
        LEFT JOIN estoque_saldo e ON e.produto_id = p.id
        WHERE p.ativo = 1 AND COALESCE(e.quantidade, 0) <= p.estoque_minimo
    """).fetchone()[0]
    
    insumos_criticos_rows = conn.execute("""
        SELECT p.nome, p.unidade, COALESCE(e.quantidade, 0) as quantidade_atual, p.estoque_minimo
        FROM estoque_produtos p
        LEFT JOIN estoque_saldo e ON e.produto_id = p.id
        WHERE p.ativo = 1 AND COALESCE(e.quantidade, 0) <= p.estoque_minimo
        ORDER BY (COALESCE(e.quantidade, 0) - p.estoque_minimo) ASC
        LIMIT 5
    """).fetchall()
    insumos_criticos_list = [dict(r) for r in insumos_criticos_rows]
    
    # 8. Evolução Diária da Produção vs Perdas para Gráfico
    evolucao_diaria_rows = conn.execute("""
        SELECT data, 
               SUM(producao) as producao, 
               SUM(perda_quantidade) as perda
        FROM producao_diaria 
        WHERE mes_referencia = ? 
        GROUP BY data 
        ORDER BY data
    """, (mes,)).fetchall()
    evolucao_diaria_list = [dict(r) for r in evolucao_diaria_rows]
    
    # 9. Distribuição de Perdas por Categoria/Tipo para Gráfico de Pizza
    perdas_por_tipo_rows = conn.execute("""
        SELECT COALESCE(tipo_perda, 'Outros') as tipo_perda, 
               SUM(quantidade) as quantidade
        FROM estoque_movimentacoes
        WHERE tipo = 'perda' AND strftime('%Y-%m', data) = ?
        GROUP BY tipo_perda
        ORDER BY quantidade DESC
    """, (mes,)).fetchall()
    perdas_por_tipo_list = [dict(r) for r in perdas_por_tipo_rows]

    conn.close()

    ops = []
    total_premios = 0
    pos = 1
    for r in operadores:
        d = dict(r)
        media = d["media_diaria"] or 0
        d["elegivel"] = media >= (d["meta"] or 8000)
        d["valor_premio"] = premios_por_posicao.get(pos, premio_2) if d["elegivel"] else 0
        total_premios += d["valor_premio"]
        pos += 1
        ops.append(d)

    aux_list = [dict(r) for r in auxiliares]
    total_premios += sum(a["valor_bonus"] for a in aux_list)

    total_producao_geral = sum(o["total_producao"] or 0 for o in ops)
    media_geral = round(total_producao_geral / total_dias, 0) if total_dias > 0 else 0

    return {
        "mes": mes,
        "total_dias_registrados": total_dias,
        "total_producao_geral": total_producao_geral,
        "media_geral": media_geral,
        "operadores": ops,
        "auxiliares": aux_list,
        "total_premios": total_premios,
        "total_perdas_geral": total_perdas_geral,
        "total_sobras_geral": total_sobras_geral,
        "custo_perdas_geral": custo_perdas_geral,
        "aderencia_meta_percentual": aderencia_meta_percentual,
        "pedidos_pendentes": pedidos_pendentes,
        "pedidos_atrasados": pedidos_atrasados,
        "pedidos_criticos": pedidos_criticos_list,
        "epi_vencidos_count": epi_vencidos_count,
        "epi_criticos": epi_criticos_list,
        "estoque_alertas_count": estoque_alertas_count,
        "insumos_criticos": insumos_criticos_list,
        "evolucao_diaria": evolucao_diaria_list,
        "perdas_por_tipo": perdas_por_tipo_list
    }
