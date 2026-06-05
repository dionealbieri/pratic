from fastapi import APIRouter
from typing import Optional
from database import get_conn

router = APIRouter()

def _periodo_where(alias: str = "p", mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    where = []
    params = []
    if mes_ini:
        where.append(f"{alias}.mes_referencia >= ?")
        params.append(mes_ini)
    if mes_fim:
        where.append(f"{alias}.mes_referencia <= ?")
        params.append(mes_fim)
    return where, params

@router.get("/evolucao-mensal")
def evolucao_mensal(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    conn = get_conn()
    extra_where, params = _periodo_where("p", mes_ini, mes_fim)
    where_sql = " AND ".join(["c.tipo = 'operador'"] + extra_where)
    rows = conn.execute(f"""
        SELECT 
            p.mes_referencia,
            c.id as colaborador_id,
            c.nome as colaborador,
            SUM(p.producao) as total_producao,
            COALESCE(SUM(p.perda_quantidade), 0) as total_perdas,
            COALESCE(SUM(p.sobra_quantidade), 0) as total_sobras,
            COUNT(CASE WHEN p.producao > 0 THEN 1 END) as dias_trabalhados,
            AVG(CASE WHEN p.producao > 0 THEN p.producao ELSE NULL END) as media_diaria,
            AVG(p.meta) as meta_media,
            SUM(CASE WHEN p.excedente > 0 THEN p.excedente ELSE 0 END) as excedente_positivo,
            SUM(CASE WHEN p.excedente < 0 THEN p.excedente ELSE 0 END) as excedente_negativo,
            SUM(p.excedente) as excedente_total,
            COUNT(CASE WHEN p.producao >= p.meta THEN 1 END) as dias_acima_meta,
            COUNT(CASE WHEN p.producao > 0 AND p.producao < p.meta THEN 1 END) as dias_abaixo_meta
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE {where_sql}
        GROUP BY p.mes_referencia, c.id
        ORDER BY p.mes_referencia ASC, c.nome ASC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/producao-diaria/{mes}")
def producao_diaria_mes(mes: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT 
            p.data,
            c.nome as colaborador,
            p.producao,
            COALESCE(p.perda_quantidade, 0) as perda_quantidade,
            COALESCE(p.sobra_quantidade, 0) as sobra_quantidade,
            p.meta,
            p.excedente
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE p.mes_referencia = ? AND c.tipo = 'operador'
        ORDER BY p.data ASC, c.nome ASC
    """, (mes,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/comparativo-operadores")
def comparativo_operadores():
    conn = get_conn()
    meses = conn.execute("""
        SELECT DISTINCT mes_referencia FROM producao_diaria ORDER BY mes_referencia ASC
    """).fetchall()
    operadores = conn.execute("""
        SELECT DISTINCT c.id, c.nome FROM colaboradores c
        WHERE c.tipo = 'operador' AND c.ativo = 1 ORDER BY c.nome
    """).fetchall()

    resultado = []
    for mes_row in meses:
        mes = mes_row[0]
        entry = {"mes": mes, "operadores": {}}
        for op in operadores:
            row = conn.execute("""
                SELECT 
                    AVG(CASE WHEN p.producao > 0 THEN p.producao ELSE NULL END) as media,
                    SUM(p.producao) as total,
                    COUNT(p.id) as dias
                FROM producao_diaria p
                WHERE p.colaborador_id = ? AND p.mes_referencia = ?
            """, (op[0], mes)).fetchone()
            entry["operadores"][op[1]] = {
                "media": round(row[0] or 0, 0),
                "total": row[1] or 0,
                "dias": row[2] or 0
            }
        resultado.append(entry)
    conn.close()
    return resultado

@router.get("/ranking-historico")
def ranking_historico(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    conn = get_conn()
    extra_where, params = _periodo_where("p", mes_ini, mes_fim)
    where_sql = " AND ".join(["c.tipo = 'operador'"] + extra_where)
    rows = conn.execute(f"""
        SELECT 
            c.nome as colaborador,
            COUNT(DISTINCT p.mes_referencia) as meses_trabalhados,
            SUM(p.producao) as total_geral,
            COALESCE(SUM(p.perda_quantidade), 0) as total_perdas,
            COALESCE(SUM(p.sobra_quantidade), 0) as total_sobras,
            AVG(CASE WHEN p.producao > 0 THEN p.producao ELSE NULL END) as media_geral,
            AVG(p.meta) as media_meta,
            SUM(p.excedente) as saldo_excedente,
            SUM(CASE WHEN p.excedente > 0 THEN p.excedente ELSE 0 END) as total_excedente_positivo,
            SUM(CASE WHEN p.excedente < 0 THEN p.excedente ELSE 0 END) as total_excedente_negativo,
            COUNT(CASE WHEN p.producao >= p.meta THEN 1 END) as dias_acima_meta,
            COUNT(CASE WHEN p.producao > 0 AND p.producao < p.meta THEN 1 END) as dias_abaixo_meta,
            COUNT(CASE WHEN p.producao > 0 THEN 1 END) as total_dias,
            MAX(p.producao) as melhor_dia,
            MIN(CASE WHEN p.producao > 0 THEN p.producao ELSE NULL END) as pior_dia
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE {where_sql}
        GROUP BY c.id
        ORDER BY media_geral DESC
    """, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        total_dias = d["total_dias"] or 1
        d["pct_acima_meta"] = round((d["dias_acima_meta"] / total_dias) * 100, 1)
        result.append(d)
    return result



@router.get("/resumo-periodo")
def resumo_periodo(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    conn = get_conn()
    extra_where, params = _periodo_where("p", mes_ini, mes_fim)
    where_sql = " AND ".join(["c.tipo = 'operador'"] + extra_where)

    resumo = conn.execute(f"""
        SELECT
            COALESCE(SUM(p.producao), 0) as total_producao,
            COALESCE(SUM(p.perda_quantidade), 0) as total_perdas,
            COALESCE(SUM(p.sobra_quantidade), 0) as total_sobras,
            COALESCE(SUM(p.excedente), 0) as saldo_excedente,
            COUNT(p.id) as total_lancamentos,
            COUNT(DISTINCT p.data) as dias_registrados
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE {where_sql}
    """, params).fetchone()

    melhor = conn.execute(f"""
        SELECT
            c.nome as colaborador,
            COALESCE(SUM(p.producao), 0) as total_producao,
            COUNT(CASE WHEN p.producao > 0 THEN 1 END) as dias_trabalhados,
            AVG(CASE WHEN p.producao > 0 THEN p.producao ELSE NULL END) as media_diaria,
            COALESCE(SUM(p.excedente), 0) as saldo_excedente
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE {where_sql}
        GROUP BY c.id
        HAVING total_producao > 0
        ORDER BY media_diaria DESC
        LIMIT 1
    """, params).fetchone()

    conn.close()

    d = dict(resumo) if resumo else {}
    total = d.get("total_producao") or 0
    dias = d.get("dias_registrados") or 0
    perdas = d.get("total_perdas") or 0
    d["media_diaria_geral"] = round(total / dias, 0) if dias else 0
    d["indice_perda"] = round((perdas / total) * 100, 2) if total else 0
    d["melhor_operador"] = dict(melhor) if melhor else None
    d["mes_ini"] = mes_ini
    d["mes_fim"] = mes_fim
    return d


@router.get("/meses-disponiveis")
def meses_disponiveis():
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT mes_referencia FROM producao_diaria ORDER BY mes_referencia DESC
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]

@router.get("/resumo-anual/{ano}")
def resumo_anual(ano: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT 
            mes_referencia,
            SUM(producao) as total_producao,
            COALESCE(SUM(perda_quantidade), 0) as total_perda,
            COALESCE(SUM(sobra_quantidade), 0) as total_sobra,
            SUM(excedente) as total_excedente,
            COUNT(DISTINCT data) as dias_registrados,
            CASE WHEN COUNT(DISTINCT data) > 0 THEN SUM(producao) / COUNT(DISTINCT data) ELSE 0 END as media_diaria
        FROM producao_diaria
        WHERE mes_referencia LIKE ?
        GROUP BY mes_referencia
        ORDER BY mes_referencia
    """, (ano+'%',)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
