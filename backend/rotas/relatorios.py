from fastapi import APIRouter
from typing import Optional
from database import get_conn
import datetime
import calendar

router = APIRouter()

def _feriados_no_intervalo(conn, inicio: datetime.date, fim: datetime.date) -> set:
    rows = conn.execute(
        "SELECT data FROM feriados WHERE data BETWEEN ? AND ?",
        (inicio.isoformat(), fim.isoformat())
    ).fetchall()
    return {r["data"] for r in rows}

def _dias_uteis_mes_inteiro(conn, ano: int, mes: int) -> int:
    """Conta os dias úteis (seg-sex, exceto feriados cadastrados) do mês inteiro."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = datetime.date(ano, mes, 1)
    fim = datetime.date(ano, mes, ultimo_dia)
    feriados = _feriados_no_intervalo(conn, inicio, fim)
    dias = 0
    d = inicio
    while d <= fim:
        if d.weekday() < 5 and d.isoformat() not in feriados:
            dias += 1
        d += datetime.timedelta(days=1)
    return dias

def _dias_uteis_restantes(conn, mes_fim: str):
    """Dias úteis restantes (incluindo hoje) até o fim do mes_fim informado.
    Retorna None se mes_fim já é um mês encerrado (no passado)."""
    hoje = datetime.date.today()
    ano, mes = map(int, mes_fim.split("-"))
    if (ano, mes) < (hoje.year, hoje.month):
        return None
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fim = datetime.date(ano, mes, ultimo_dia)
    inicio = hoje if (ano, mes) == (hoje.year, hoje.month) else datetime.date(ano, mes, 1)
    if inicio > fim:
        return 0
    feriados = _feriados_no_intervalo(conn, inicio, fim)
    dias = 0
    d = inicio
    while d <= fim:
        if d.weekday() < 5 and d.isoformat() not in feriados:
            dias += 1
        d += datetime.timedelta(days=1)
    return dias

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
    extra_where, params = _periodo_where("pd", mes_ini, mes_fim)
    where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
    # Agrega primeiro por (colaborador, dia) — um colaborador pode ter mais de um
    # lançamento no mesmo dia (ex: duas máquinas), e contar linhas direto inflava
    # "dias trabalhados" e distorcia médias/excedente (meta subtraída em dobro).
    rows = conn.execute(f"""
        WITH por_dia AS (
            SELECT
                p.colaborador_id,
                p.mes_referencia,
                p.data,
                SUM(p.producao) as producao_dia,
                COALESCE(SUM(p.perda_quantidade), 0) as perda_dia,
                COALESCE(SUM(p.sobra_quantidade), 0) as sobra_dia,
                MAX(p.meta) as meta_dia
            FROM producao_diaria p
            GROUP BY p.colaborador_id, p.data, p.mes_referencia
        )
        SELECT 
            pd.mes_referencia,
            c.id as colaborador_id,
            c.nome as colaborador,
            SUM(pd.producao_dia) as total_producao,
            SUM(pd.perda_dia) as total_perdas,
            SUM(pd.sobra_dia) as total_sobras,
            COUNT(CASE WHEN pd.producao_dia > 0 THEN 1 END) as dias_trabalhados,
            AVG(CASE WHEN pd.producao_dia > 0 THEN pd.producao_dia ELSE NULL END) as media_diaria,
            AVG(pd.meta_dia) as meta_media,
            SUM(CASE WHEN (pd.producao_dia - pd.meta_dia) > 0 THEN (pd.producao_dia - pd.meta_dia) ELSE 0 END) as excedente_positivo,
            SUM(CASE WHEN (pd.producao_dia - pd.meta_dia) < 0 THEN (pd.producao_dia - pd.meta_dia) ELSE 0 END) as excedente_negativo,
            SUM(pd.producao_dia - pd.meta_dia) as excedente_total,
            COUNT(CASE WHEN pd.producao_dia >= pd.meta_dia THEN 1 END) as dias_acima_meta,
            COUNT(CASE WHEN pd.producao_dia > 0 AND pd.producao_dia < pd.meta_dia THEN 1 END) as dias_abaixo_meta
        FROM por_dia pd
        JOIN colaboradores c ON pd.colaborador_id = c.id
        WHERE {where_sql}
        GROUP BY pd.mes_referencia, c.id
        ORDER BY pd.mes_referencia ASC, c.nome ASC
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
        WHERE p.mes_referencia = ? AND LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)
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
        WHERE LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1) AND c.ativo = 1 ORDER BY c.nome
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
    extra_where, params = _periodo_where("pd", mes_ini, mes_fim)
    where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
    rows = conn.execute(f"""
        WITH por_dia AS (
            SELECT
                p.colaborador_id,
                p.mes_referencia,
                p.data,
                SUM(p.producao) as producao_dia,
                COALESCE(SUM(p.perda_quantidade), 0) as perda_dia,
                COALESCE(SUM(p.sobra_quantidade), 0) as sobra_dia,
                MAX(p.meta) as meta_dia
            FROM producao_diaria p
            GROUP BY p.colaborador_id, p.data, p.mes_referencia
        )
        SELECT 
            c.nome as colaborador,
            COUNT(DISTINCT pd.mes_referencia) as meses_trabalhados,
            SUM(pd.producao_dia) as total_geral,
            COALESCE(SUM(pd.perda_dia), 0) as total_perdas,
            COALESCE(SUM(pd.sobra_dia), 0) as total_sobras,
            AVG(CASE WHEN pd.producao_dia > 0 THEN pd.producao_dia ELSE NULL END) as media_geral,
            AVG(pd.meta_dia) as media_meta,
            SUM(pd.producao_dia - pd.meta_dia) as saldo_excedente,
            SUM(CASE WHEN (pd.producao_dia - pd.meta_dia) > 0 THEN (pd.producao_dia - pd.meta_dia) ELSE 0 END) as total_excedente_positivo,
            SUM(CASE WHEN (pd.producao_dia - pd.meta_dia) < 0 THEN (pd.producao_dia - pd.meta_dia) ELSE 0 END) as total_excedente_negativo,
            COUNT(CASE WHEN pd.producao_dia >= pd.meta_dia THEN 1 END) as dias_acima_meta,
            COUNT(CASE WHEN pd.producao_dia > 0 AND pd.producao_dia < pd.meta_dia THEN 1 END) as dias_abaixo_meta,
            COUNT(CASE WHEN pd.producao_dia > 0 THEN 1 END) as total_dias,
            MAX(pd.producao_dia) as melhor_dia,
            MIN(CASE WHEN pd.producao_dia > 0 THEN pd.producao_dia ELSE NULL END) as pior_dia
        FROM por_dia pd
        JOIN colaboradores c ON pd.colaborador_id = c.id
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
    where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)

    resumo = conn.execute(f"""
        SELECT
            COALESCE(SUM(p.producao), 0) as total_producao,
            COALESCE(SUM(p.perda_quantidade), 0) as total_perdas,
            COALESCE(SUM(p.sobra_quantidade), 0) as total_sobras,
            COUNT(p.id) as total_lancamentos,
            COUNT(DISTINCT p.data) as dias_registrados
        FROM producao_diaria p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE {where_sql}
    """, params).fetchone()

    # Saldo excedente à parte: precisa agregar por (colaborador, dia) primeiro,
    # senão um colaborador com 2 lançamentos no mesmo dia (ex: duas máquinas)
    # teria a meta subtraída em dobro.
    extra_where_pd, params_pd = _periodo_where("pd", mes_ini, mes_fim)
    where_sql_pd = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where_pd)
    excedente_row = conn.execute(f"""
        WITH por_dia AS (
            SELECT p.colaborador_id, p.mes_referencia, p.data,
                   SUM(p.producao) as producao_dia, MAX(p.meta) as meta_dia
            FROM producao_diaria p
            GROUP BY p.colaborador_id, p.data, p.mes_referencia
        )
        SELECT COALESCE(SUM(pd.producao_dia - pd.meta_dia), 0) as saldo_excedente
        FROM por_dia pd
        JOIN colaboradores c ON pd.colaborador_id = c.id
        WHERE {where_sql_pd}
    """, params_pd).fetchone()

    melhor = conn.execute(f"""
        WITH por_dia AS (
            SELECT p.colaborador_id, p.mes_referencia, p.data,
                   SUM(p.producao) as producao_dia, MAX(p.meta) as meta_dia
            FROM producao_diaria p
            GROUP BY p.colaborador_id, p.data, p.mes_referencia
        )
        SELECT
            c.nome as colaborador,
            COALESCE(SUM(pd.producao_dia), 0) as total_producao,
            COUNT(CASE WHEN pd.producao_dia > 0 THEN 1 END) as dias_trabalhados,
            AVG(CASE WHEN pd.producao_dia > 0 THEN pd.producao_dia ELSE NULL END) as media_diaria,
            COALESCE(SUM(pd.producao_dia - pd.meta_dia), 0) as saldo_excedente
        FROM por_dia pd
        JOIN colaboradores c ON pd.colaborador_id = c.id
        WHERE {where_sql_pd}
        GROUP BY c.id
        HAVING total_producao > 0
        ORDER BY media_diaria DESC
        LIMIT 1
    """, params_pd).fetchone()

    conn.close()

    d = dict(resumo) if resumo else {}
    d["saldo_excedente"] = dict(excedente_row).get("saldo_excedente", 0) if excedente_row else 0
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

@router.get("/rendimento-insumos")
def relatorio_rendimento_insumos(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    conn = get_conn()
    extra_where, params = _periodo_where("p", mes_ini, mes_fim)
    
    # Filtramos apenas registros onde o produto de estoque está vinculado
    where_sql = " AND ".join(["p.produto_estoque_id IS NOT NULL"] + extra_where)
    
    query = f"""
        SELECT 
            ep.id as produto_id,
            ep.codigo as produto_codigo,
            ep.nome as produto_nome,
            ep.unidade,
            SUM(p.producao) as total_produzido,
            SUM(p.perda_quantidade) as total_perda,
            SUM(p.sobra_quantidade) as total_sobra,
            (SELECT COALESCE(AVG(custo_unitario), 0.0) FROM estoque_movimentacoes WHERE produto_id = ep.id AND custo_unitario IS NOT NULL) as custo_medio
        FROM producao_diaria p
        JOIN estoque_produtos ep ON p.produto_estoque_id = ep.id
        WHERE {where_sql}
        GROUP BY ep.id
        ORDER BY total_perda DESC
    """
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    resultado = []
    for r in rows:
        d = dict(r)
        prod = d["total_produzido"] or 0
        perda = d["total_perda"] or 0
        sobra = d["total_sobra"] or 0
        
        # Consumo do estoque = produção + perda - sobra
        consumo = prod + perda - sobra
        d["total_consumido"] = consumo
        d["indice_perda"] = round((perda / consumo * 100), 2) if consumo > 0 else 0.0
        
        custo_med = d["custo_medio"] or 0.0
        d["custo_total_perda"] = round(perda * custo_med, 2)
        resultado.append(d)
        
    return resultado

@router.get("/matriz-operador-categoria")
def matriz_operador_categoria(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    """Quanto cada operador produziu, por categoria de produção, no período.
    Usa producao_diaria_itens (detalhe por produto), que existe pra todo
    lançamento — único ou multi-produto — a partir da migração desta versão."""
    conn = get_conn()
    extra_where, params = _periodo_where("p", mes_ini, mes_fim)
    where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
    rows = conn.execute(f"""
        SELECT
            c.nome as colaborador,
            COALESCE(cat.nome, 'Não categorizado') as categoria,
            SUM(pdi.quantidade) as quantidade
        FROM producao_diaria_itens pdi
        JOIN producao_diaria p ON p.id = pdi.producao_diaria_id
        JOIN colaboradores c ON c.id = p.colaborador_id
        LEFT JOIN estoque_produtos ep ON ep.id = pdi.produto_estoque_id
        LEFT JOIN estoque_categorias cat ON cat.id = ep.categoria_id
        WHERE {where_sql}
        GROUP BY c.id, categoria
        ORDER BY c.nome ASC, categoria ASC
    """, params).fetchall()
    conn.close()

    categorias = sorted({r["categoria"] for r in rows})
    operadores = {}
    for r in rows:
        op = operadores.setdefault(r["colaborador"], {"colaborador": r["colaborador"], "valores": {}, "total": 0})
        op["valores"][r["categoria"]] = r["quantidade"] or 0
        op["total"] += r["quantidade"] or 0

    linhas = sorted(operadores.values(), key=lambda x: -x["total"])
    return {"categorias": categorias, "linhas": linhas}

@router.get("/resumo-diario-producao")
def resumo_diario_producao(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    """Um resumo por dia (não por mês) dentro do período: total produzido,
    perdas, sobras, lançamentos, colaboradores ativos e a categoria de maior
    volume naquele dia — útil pra achar dias fora do padrão."""
    conn = get_conn()
    extra_where, params = _periodo_where("p", mes_ini, mes_fim)
    where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
    dias = conn.execute(f"""
        SELECT
            p.data,
            SUM(p.producao) as total_producao,
            COALESCE(SUM(p.perda_quantidade), 0) as total_perdas,
            COALESCE(SUM(p.sobra_quantidade), 0) as total_sobras,
            COUNT(p.id) as total_lancamentos,
            COUNT(DISTINCT p.colaborador_id) as colaboradores_ativos
        FROM producao_diaria p
        JOIN colaboradores c ON c.id = p.colaborador_id
        WHERE {where_sql}
        GROUP BY p.data
        ORDER BY p.data ASC
    """, params).fetchall()

    extra_where2, params2 = _periodo_where("p", mes_ini, mes_fim)
    where_sql2 = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where2)
    cat_rows = conn.execute(f"""
        SELECT p.data, COALESCE(cat.nome, 'Não categorizado') as categoria, SUM(pdi.quantidade) as qtd
        FROM producao_diaria_itens pdi
        JOIN producao_diaria p ON p.id = pdi.producao_diaria_id
        JOIN colaboradores c ON c.id = p.colaborador_id
        LEFT JOIN estoque_produtos ep ON ep.id = pdi.produto_estoque_id
        LEFT JOIN estoque_categorias cat ON cat.id = ep.categoria_id
        WHERE {where_sql2}
        GROUP BY p.data, categoria
    """, params2).fetchall()
    conn.close()

    categorias_por_dia = {}
    for r in cat_rows:
        data = r["data"]
        categorias_por_dia.setdefault(data, []).append({"categoria": r["categoria"], "quantidade": r["qtd"] or 0})
    for data in categorias_por_dia:
        categorias_por_dia[data].sort(key=lambda x: -x["quantidade"])

    resultado = []
    for d in dias:
        item = dict(d)
        cats = categorias_por_dia.get(d["data"], [])
        item["categorias"] = cats
        item["categoria_destaque"] = cats[0]["categoria"] if cats else None
        item["categoria_destaque_qtd"] = cats[0]["quantidade"] if cats else 0
        resultado.append(item)
    return resultado

@router.get("/meta-producao")
def meta_producao(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    """Meta x Produzido por operador, total do período: quem está acima ou
    abaixo da meta esperada (dias trabalhados x meta diária), ordenado do
    pior saldo pro melhor."""
    conn = get_conn()
    extra_where, params = _periodo_where("pd", mes_ini, mes_fim)
    where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
    rows = conn.execute(f"""
        WITH por_dia AS (
            SELECT p.colaborador_id, p.mes_referencia, p.data,
                   SUM(p.producao) as producao_dia, MAX(p.meta) as meta_dia
            FROM producao_diaria p
            GROUP BY p.colaborador_id, p.data, p.mes_referencia
        )
        SELECT
            c.nome as colaborador,
            COUNT(CASE WHEN pd.producao_dia > 0 THEN 1 END) as dias_trabalhados,
            SUM(CASE WHEN pd.producao_dia > 0 THEN pd.producao_dia ELSE 0 END) as produzido,
            SUM(CASE WHEN pd.producao_dia > 0 THEN pd.meta_dia ELSE 0 END) as meta_periodo,
            SUM(CASE WHEN pd.producao_dia > 0 THEN pd.producao_dia - pd.meta_dia ELSE 0 END) as saldo
        FROM por_dia pd
        JOIN colaboradores c ON pd.colaborador_id = c.id
        WHERE {where_sql}
        GROUP BY c.id
        ORDER BY saldo ASC
    """, params).fetchall()
    conn.close()
    resultado = []
    for r in rows:
        d = dict(r)
        meta = d.get("meta_periodo") or 0
        d["aderencia"] = round((d.get("produzido") or 0) / meta * 100, 1) if meta else 0
        resultado.append(d)

    # Dias úteis restantes e o quanto falta produzir por dia pra fechar o mês
    # inteiro na meta — só faz sentido pro mês corrente (não dá pra "fechar"
    # um mês que já passou).
    conn2 = get_conn()
    dias_restantes = _dias_uteis_restantes(conn2, mes_fim) if mes_fim else None
    fabrica = {"dias_uteis_restantes": dias_restantes, "meta_mes_completo": 0, "produzido": 0, "falta": 0, "necessario_dia": None, "meta_batida": None}
    if dias_restantes is not None and mes_fim:
        ano, mes = map(int, mes_fim.split("-"))
        dias_uteis_mes = _dias_uteis_mes_inteiro(conn2, ano, mes)
        for d in resultado:
            meta_diaria = (d.get("meta_periodo") or 0) / d["dias_trabalhados"] if d.get("dias_trabalhados") else 0
            meta_mes_completo = dias_uteis_mes * meta_diaria
            falta = meta_mes_completo - (d.get("produzido") or 0)
            d["dias_uteis_restantes"] = dias_restantes
            d["meta_mes_completo"] = round(meta_mes_completo, 0)
            if falta <= 0:
                d["necessario_dia"] = 0
                d["meta_batida"] = True
            elif dias_restantes > 0:
                d["necessario_dia"] = round(falta / dias_restantes, 0)
                d["meta_batida"] = False
            else:
                d["necessario_dia"] = None
                d["meta_batida"] = False
            fabrica["meta_mes_completo"] += d["meta_mes_completo"]
            fabrica["produzido"] += d.get("produzido") or 0
        fabrica["falta"] = round(fabrica["meta_mes_completo"] - fabrica["produzido"], 0)
        if fabrica["falta"] <= 0:
            fabrica["necessario_dia"] = 0
            fabrica["meta_batida"] = True
        elif dias_restantes > 0:
            fabrica["necessario_dia"] = round(fabrica["falta"] / dias_restantes, 0)
            fabrica["meta_batida"] = False
    else:
        for d in resultado:
            d["dias_uteis_restantes"] = None
            d["necessario_dia"] = None
            d["meta_batida"] = None
    conn2.close()
    return {"linhas": resultado, "fabrica": fabrica}

def _periodo_data_bounds(mes_ini: Optional[str], mes_fim: Optional[str]):
    ini = f"{mes_ini}-01" if mes_ini else None
    fim = None
    if mes_fim:
        ano, mes = map(int, mes_fim.split("-"))
        ultimo = calendar.monthrange(ano, mes)[1]
        fim = f"{mes_fim}-{ultimo:02d}"
    return ini, fim

@router.get("/perdas-por-tipo")
def perdas_por_tipo(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    """Quanto se perdeu por tipo de motivo (Quebra, Defeito, Falta na
    embalagem...) no período — ajuda a atacar causa raiz em vez de só saber
    o total perdido. Fonte: estoque_movimentacoes (onde o tipo_perda é
    gravado tanto pra lançamento único quanto multi-produto)."""
    conn = get_conn()
    ini, fim = _periodo_data_bounds(mes_ini, mes_fim)
    where = ["tipo='perda'"]
    params = []
    if ini: where.append("data >= ?"); params.append(ini)
    if fim: where.append("data <= ?"); params.append(fim)
    rows = conn.execute(f"""
        SELECT COALESCE(tipo_perda, 'Não informado') as tipo_perda,
               SUM(quantidade) as quantidade, COUNT(*) as ocorrencias
        FROM estoque_movimentacoes
        WHERE {" AND ".join(where)}
        GROUP BY tipo_perda
        ORDER BY quantidade DESC
    """, params).fetchall()
    conn.close()
    total = sum((r["quantidade"] or 0) for r in rows)
    resultado = []
    for r in rows:
        d = dict(r)
        d["percentual"] = round((d["quantidade"] or 0) / total * 100, 1) if total else 0
        resultado.append(d)
    return resultado

def _filtros_perdas_sobras(data_inicio: Optional[str], data_fim: Optional[str],
                            produto_id: Optional[int], colaborador_id: Optional[int],
                            tipo_perda: Optional[str]):
    where = ["(i.perda_quantidade > 0 OR i.sobra_quantidade > 0)"]
    params = []
    if data_inicio:
        where.append("p.data >= ?"); params.append(data_inicio)
    if data_fim:
        where.append("p.data <= ?"); params.append(data_fim)
    if produto_id:
        where.append("i.produto_estoque_id = ?"); params.append(produto_id)
    if colaborador_id:
        where.append("p.colaborador_id = ?"); params.append(colaborador_id)
    if tipo_perda:
        where.append("i.tipo_perda = ?"); params.append(tipo_perda)
    return where, params

@router.get("/perdas-sobras-detalhado")
def perdas_sobras_detalhado(data_inicio: Optional[str] = None, data_fim: Optional[str] = None,
                             produto_id: Optional[int] = None, colaborador_id: Optional[int] = None,
                             tipo_perda: Optional[str] = None):
    """Cada ocorrência de perda/sobra com produto, data e operador — pra
    rastrear qual produto perdeu/sobrou, quando e com quem, em vez de só
    ver o total agregado por tipo."""
    conn = get_conn()
    where, params = _filtros_perdas_sobras(data_inicio, data_fim, produto_id, colaborador_id, tipo_perda)
    rows = conn.execute(f"""
        SELECT p.data, c.nome as colaborador_nome, m.nome as maquina_nome,
               ep.nome as produto_nome, i.tipo_perda,
               i.perda_quantidade, i.sobra_quantidade, p.pedido_numero
        FROM producao_diaria_itens i
        JOIN producao_diaria p ON p.id = i.producao_diaria_id
        JOIN colaboradores c ON c.id = p.colaborador_id
        JOIN maquinas m ON m.id = p.maquina_id
        LEFT JOIN estoque_produtos ep ON ep.id = i.produto_estoque_id
        WHERE {" AND ".join(where)}
        ORDER BY p.data DESC, p.id DESC
    """, params).fetchall()
    conn.close()
    ocorrencias = [dict(r) for r in rows]
    total_perda = sum((r["perda_quantidade"] or 0) for r in ocorrencias)
    total_sobra = sum((r["sobra_quantidade"] or 0) for r in ocorrencias)
    return {"ocorrencias": ocorrencias, "total_perda": total_perda, "total_sobra": total_sobra}

@router.get("/perdas-sobras-grafico")
def perdas_sobras_grafico(data_inicio: Optional[str] = None, data_fim: Optional[str] = None,
                           produto_id: Optional[int] = None, colaborador_id: Optional[int] = None,
                           tipo_perda: Optional[str] = None):
    """Perda x sobra agregado por dia, já com os mesmos filtros da tela
    detalhada — alimenta o gráfico combinado do dashboard."""
    conn = get_conn()
    where, params = _filtros_perdas_sobras(data_inicio, data_fim, produto_id, colaborador_id, tipo_perda)
    rows = conn.execute(f"""
        SELECT p.data,
               SUM(i.perda_quantidade) as total_perda,
               SUM(i.sobra_quantidade) as total_sobra
        FROM producao_diaria_itens i
        JOIN producao_diaria p ON p.id = i.producao_diaria_id
        WHERE {" AND ".join(where)}
        GROUP BY p.data
        ORDER BY p.data ASC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/produtividade-maquina")
def produtividade_maquina(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    """Desempenho por máquina: total produzido, perdas, sobras, quantos dias
    esteve em uso e quantos operadores diferentes passaram por ela. Hoje tudo
    é medido por pessoa; isso separa problema de máquina de problema de
    operador."""
    conn = get_conn()
    extra_where, params = _periodo_where("p", mes_ini, mes_fim)
    where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
    rows = conn.execute(f"""
        SELECT
            m.nome as maquina,
            COUNT(DISTINCT p.data) as dias_utilizada,
            COUNT(DISTINCT p.colaborador_id) as operadores_diferentes,
            COALESCE(SUM(p.producao), 0) as total_producao,
            COALESCE(SUM(p.perda_quantidade), 0) as total_perdas,
            COALESCE(SUM(p.sobra_quantidade), 0) as total_sobras
        FROM producao_diaria p
        JOIN maquinas m ON m.id = p.maquina_id
        JOIN colaboradores c ON c.id = p.colaborador_id
        WHERE {where_sql}
        GROUP BY m.id
        ORDER BY total_producao DESC
    """, params).fetchall()
    conn.close()
    resultado = []
    for r in rows:
        d = dict(r)
        d["media_dia"] = round((d["total_producao"] or 0) / d["dias_utilizada"], 0) if d["dias_utilizada"] else 0
        d["indice_perda"] = round((d["total_perdas"] or 0) / d["total_producao"] * 100, 2) if d["total_producao"] else 0
        resultado.append(d)
    return resultado

@router.get("/dias-sem-lancamento")
def dias_sem_lancamento(mes_ini: str, mes_fim: str):
    """Pra cada colaborador que produziu no período, lista quantos dias úteis
    ele NÃO tem lançamento nenhum — possível ausência que passou
    despercebida. Só entra quem trabalhou ao menos 1 dia no período (evita
    acusar falsamente quem foi contratado depois ou já saiu antes)."""
    conn = get_conn()
    ano_i, mes_i = map(int, mes_ini.split("-"))
    ano_f, mes_f = map(int, mes_fim.split("-"))
    inicio = datetime.date(ano_i, mes_i, 1)
    fim = datetime.date(ano_f, mes_f, calendar.monthrange(ano_f, mes_f)[1])
    feriados = _feriados_no_intervalo(conn, inicio, fim)
    dias_uteis = []
    d = inicio
    while d <= fim:
        if d.weekday() < 5 and d.isoformat() not in feriados:
            dias_uteis.append(d.isoformat())
        d += datetime.timedelta(days=1)

    colaboradores = conn.execute("""
        SELECT id, nome FROM colaboradores
        WHERE LOWER(tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao=1)
          AND ativo = 1
    """).fetchall()

    resultado = []
    for c in colaboradores:
        trabalhados = {r["data"] for r in conn.execute(
            "SELECT DISTINCT data FROM producao_diaria WHERE colaborador_id=? AND data BETWEEN ? AND ? AND producao > 0",
            (c["id"], inicio.isoformat(), fim.isoformat())
        ).fetchall()}
        if not trabalhados:
            continue
        faltando = [dia for dia in dias_uteis if dia not in trabalhados]
        resultado.append({
            "colaborador": c["nome"],
            "dias_uteis_periodo": len(dias_uteis),
            "dias_trabalhados": len(trabalhados),
            "dias_sem_lancamento": len(faltando),
            "datas_faltantes": faltando,
        })
    conn.close()
    resultado.sort(key=lambda x: -x["dias_sem_lancamento"])
    return resultado

@router.get("/comparativo-periodos")
def comparativo_periodos(mes_ini_a: str, mes_fim_a: str, mes_ini_b: str, mes_fim_b: str):
    """Compara dois períodos (ex: mês atual x mês anterior), geral e por
    operador, com a variação percentual."""
    conn = get_conn()

    def _totais(mes_ini, mes_fim):
        extra_where, params = _periodo_where("p", mes_ini, mes_fim)
        where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
        row = conn.execute(f"""
            SELECT COALESCE(SUM(p.producao),0) as producao, COALESCE(SUM(p.perda_quantidade),0) as perdas,
                   COALESCE(SUM(p.sobra_quantidade),0) as sobras, COUNT(DISTINCT p.data) as dias
            FROM producao_diaria p JOIN colaboradores c ON c.id = p.colaborador_id
            WHERE {where_sql}
        """, params).fetchone()
        return dict(row)

    def _por_colaborador(mes_ini, mes_fim):
        extra_where, params = _periodo_where("p", mes_ini, mes_fim)
        where_sql = " AND ".join(["LOWER(c.tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao = 1)"] + extra_where)
        rows = conn.execute(f"""
            SELECT c.nome as colaborador, COALESCE(SUM(p.producao),0) as producao
            FROM producao_diaria p JOIN colaboradores c ON c.id = p.colaborador_id
            WHERE {where_sql} GROUP BY c.id
        """, params).fetchall()
        return {r["colaborador"]: r["producao"] for r in rows}

    a = _totais(mes_ini_a, mes_fim_a)
    b = _totais(mes_ini_b, mes_fim_b)
    pa = _por_colaborador(mes_ini_a, mes_fim_a)
    pb = _por_colaborador(mes_ini_b, mes_fim_b)
    conn.close()

    def _variacao(x, y):
        if y:
            return round(((x - y) / y) * 100, 1)
        return 100.0 if x else 0.0

    geral = {
        "periodo_a": a,
        "periodo_b": b,
        "variacao_producao": _variacao(a["producao"], b["producao"]),
        "variacao_perdas": _variacao(a["perdas"], b["perdas"]),
    }

    nomes = set(pa.keys()) | set(pb.keys())
    linhas = []
    for nome in nomes:
        va, vb = pa.get(nome, 0), pb.get(nome, 0)
        linhas.append({"colaborador": nome, "periodo_a": va, "periodo_b": vb, "variacao": _variacao(va, vb)})
    linhas.sort(key=lambda x: (x["periodo_a"] - x["periodo_b"]))

    return {"geral": geral, "linhas": linhas}

@router.get("/painel-do-dia")
def painel_do_dia(data: Optional[str] = None):
    """Snapshot do último dia útil (ou de uma data específica): quem lançou
    produção, quem não lançou, e os totais do dia. Feito pra ser a primeira
    coisa que a liderança olha ao abrir o sistema."""
    conn = get_conn()
    if not data:
        d = datetime.date.today()
        feriados = _feriados_no_intervalo(conn, d - datetime.timedelta(days=20), d)
        while d.weekday() >= 5 or d.isoformat() in feriados:
            d -= datetime.timedelta(days=1)
        data = d.isoformat()

    colaboradores = conn.execute("""
        SELECT id, nome FROM colaboradores
        WHERE LOWER(tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao=1)
          AND ativo = 1
    """).fetchall()

    lancaram_rows = conn.execute(
        "SELECT DISTINCT colaborador_id FROM producao_diaria WHERE data=? AND producao > 0", (data,)
    ).fetchall()
    lancaram_ids = {r["colaborador_id"] for r in lancaram_rows}

    resumo = conn.execute("""
        SELECT COALESCE(SUM(producao),0) as total_producao, COALESCE(SUM(perda_quantidade),0) as total_perdas,
               COALESCE(SUM(sobra_quantidade),0) as total_sobras, COUNT(*) as total_lancamentos
        FROM producao_diaria WHERE data=?
    """, (data,)).fetchone()
    conn.close()

    return {
        "data": data,
        "total_producao": resumo["total_producao"],
        "total_perdas": resumo["total_perdas"],
        "total_sobras": resumo["total_sobras"],
        "total_lancamentos": resumo["total_lancamentos"],
        "colaboradores_lancaram": [c["nome"] for c in colaboradores if c["id"] in lancaram_ids],
        "colaboradores_sem_lancamento": [c["nome"] for c in colaboradores if c["id"] not in lancaram_ids],
    }

@router.get("/producao-hoje-por-operador")
def producao_hoje_por_operador(data: Optional[str] = None):
    """Produção do dia (hoje, ou uma data específica), por operador — pensado
    pra virar cards na tela de Meta x Produção, complementando a visão de
    período com o que está acontecendo agora."""
    conn = get_conn()
    if not data:
        data = datetime.date.today().isoformat()

    colaboradores = conn.execute("""
        SELECT id, nome FROM colaboradores
        WHERE LOWER(tipo) IN (SELECT LOWER(nome) FROM colaborador_tipos WHERE aparece_producao=1)
          AND ativo = 1
        ORDER BY nome ASC
    """).fetchall()

    lancamentos = conn.execute("""
        SELECT colaborador_id, SUM(producao) as producao, MAX(meta) as meta
        FROM producao_diaria WHERE data=?
        GROUP BY colaborador_id
    """, (data,)).fetchall()
    conn.close()

    por_colaborador = {r["colaborador_id"]: r for r in lancamentos}
    resultado = []
    for c in colaboradores:
        l = por_colaborador.get(c["id"])
        producao = l["producao"] if l else 0
        meta = l["meta"] if l else 0
        resultado.append({
            "colaborador": c["nome"],
            "lancou": l is not None,
            "producao": producao or 0,
            "meta": meta or 0,
            "saldo": (producao or 0) - (meta or 0) if l else None,
            "aderencia": round((producao or 0) / meta * 100, 1) if meta else None,
        })
    return {"data": data, "operadores": resultado}
