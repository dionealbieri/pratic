from fastapi import APIRouter
from typing import Optional
from datetime import datetime
from database import get_conn

router = APIRouter()


def _mes_anterior(mes: str) -> str:
    ano, m = int(mes[:4]), int(mes[5:7])
    if m == 1:
        return f"{ano - 1}-12"
    return f"{ano}-{m - 1:02d}"


def _ultimos_meses(mes: str, n: int) -> list:
    """Lista de mês (mais antigo -> mais recente) terminando em `mes`, tamanho n."""
    meses = [mes]
    atual = mes
    for _ in range(n - 1):
        atual = _mes_anterior(atual)
        meses.append(atual)
    return list(reversed(meses))


# Query base reaproveitada em vários agregados: soma quantidade/perda/sobra por
# produto e colaborador, dando preferência aos itens (producao_diaria_itens)
# quando o lançamento é multi-produto, e caindo para os campos do lançamento
# principal (producao_diaria) quando ele não tem itens — evita tanto perder
# dado de lançamentos antigos quanto contar em dobro os que já têm itens.
_BASE_CTE = """
    WITH base AS (
        SELECT p.id as producao_diaria_id, p.colaborador_id, p.mes_referencia,
               COALESCE(pdi.produto_estoque_id, p.produto_estoque_id) as produto_id,
               COALESCE(pdi.quantidade, CASE WHEN pdi.id IS NULL THEN p.producao ELSE 0 END) as qtd,
               COALESCE(pdi.perda_quantidade, CASE WHEN pdi.id IS NULL THEN p.perda_quantidade ELSE 0 END) as perda,
               COALESCE(pdi.sobra_quantidade, CASE WHEN pdi.id IS NULL THEN p.sobra_quantidade ELSE 0 END) as sobra
        FROM producao_diaria p
        LEFT JOIN producao_diaria_itens pdi ON pdi.producao_diaria_id = p.id
        WHERE p.mes_referencia = ?
    )
"""


@router.get("/resumo")
def resumo_gerencial(mes: Optional[str] = None):
    if not mes:
        mes = datetime.now().strftime("%Y-%m")
    mes_ant = _mes_anterior(mes)
    conn = get_conn()

    # ── KPIs ────────────────────────────────────────────────────────────
    def _totais_mes(m):
        r = conn.execute("""
            SELECT COALESCE(SUM(producao), 0) as producao,
                   COALESCE(SUM(perda_quantidade), 0) as perda,
                   COALESCE(SUM(sobra_quantidade), 0) as sobra
            FROM producao_diaria WHERE mes_referencia = ?
        """, (m,)).fetchone()
        despachados = conn.execute("""
            SELECT COUNT(*) FROM pedidos WHERE strftime('%Y-%m', data_despacho) = ?
        """, (m,)).fetchone()[0]
        return r["producao"] or 0, r["perda"] or 0, r["sobra"] or 0, despachados

    prod_atual, perda_atual, sobra_atual, desp_atual = _totais_mes(mes)
    prod_ant, perda_ant, sobra_ant, desp_ant = _totais_mes(mes_ant)
    perdas_pct_atual = round(perda_atual / prod_atual * 100, 1) if prod_atual else 0.0
    perdas_pct_ant = round(perda_ant / prod_ant * 100, 1) if prod_ant else 0.0

    produto_top = conn.execute(_BASE_CTE + """
        SELECT ep.nome as nome, ep.codigo as codigo, SUM(base.qtd) as total
        FROM base
        JOIN estoque_produtos ep ON base.produto_id = ep.id
        GROUP BY ep.id ORDER BY total DESC LIMIT 1
    """, (mes,)).fetchone()

    # ── Quantidade produzida por produto ──────────────────────────────
    producao_por_produto = conn.execute(_BASE_CTE + """
        SELECT ep.nome as nome, ep.codigo as codigo, SUM(base.qtd) as total
        FROM base
        JOIN estoque_produtos ep ON base.produto_id = ep.id
        GROUP BY ep.id
        HAVING total > 0
        ORDER BY total DESC LIMIT 10
    """, (mes,)).fetchall()

    # ── Produção por operador, com categorias que ele produziu ────────
    # (só operadores com produção > 0 no mês selecionado — já é "ativo no mês")
    linhas_operador = conn.execute(_BASE_CTE + """
        SELECT c.id as colaborador_id, c.nome as colaborador,
               ec.nome as categoria, SUM(base.qtd) as total
        FROM base
        JOIN colaboradores c ON base.colaborador_id = c.id
        LEFT JOIN estoque_produtos ep ON base.produto_id = ep.id
        LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
        GROUP BY c.id, ec.id
        HAVING total > 0
        ORDER BY c.nome, total DESC
    """, (mes,)).fetchall()

    producao_por_operador = {}
    ordem_operadores = []
    for r in linhas_operador:
        cid = r["colaborador_id"]
        if cid not in producao_por_operador:
            producao_por_operador[cid] = {"colaborador": r["colaborador"], "total": 0, "categorias": []}
            ordem_operadores.append(cid)
        producao_por_operador[cid]["total"] += r["total"] or 0
        producao_por_operador[cid]["categorias"].append({
            "categoria": r["categoria"] or "Sem categoria",
            "total": r["total"] or 0
        })
    producao_por_operador_lista = sorted(
        (producao_por_operador[cid] for cid in ordem_operadores),
        key=lambda x: x["total"], reverse=True
    )
    operadores_ativos_ids = list(producao_por_operador.keys())

    # ── Perdas x Sobras por produto ────────────────────────────────────
    # Alias da soma não pode se chamar igual à coluna do CTE ("perda"/"sobra")
    # — o SQLite resolve o HAVING contra a coluna não agregada nesse caso,
    # dando resultado errado (só o primeiro grupo passava no filtro).
    perdas_sobras = conn.execute(_BASE_CTE + """
        SELECT ep.nome as nome, ep.codigo as codigo,
               SUM(base.perda) as perda_total, SUM(base.sobra) as sobra_total
        FROM base
        JOIN estoque_produtos ep ON base.produto_id = ep.id
        GROUP BY ep.id
        HAVING perda_total > 0 OR sobra_total > 0
        ORDER BY (perda_total + sobra_total) DESC LIMIT 10
    """, (mes,)).fetchall()

    # ── Evolução mensal (últimos 6 meses) — produção total + meta total,
    # restrito aos operadores ativos no mês selecionado.
    # A meta é um alvo por colaborador/dia, não por lançamento — um dia com
    # vários produtos gera várias linhas em producao_diaria com a MESMA meta
    # repetida. Somar direto infla o total (ex: 872.000 em vez de 184.000
    # reais em julho). Por isso agregamos por (colaborador_id, data) antes de
    # somar, no mesmo padrão já usado na aderência à meta do dashboard.
    evolucao_mensal = []
    if operadores_ativos_ids:
        placeholders = ",".join("?" * len(operadores_ativos_ids))
        for m in _ultimos_meses(mes, 6):
            producao_row = conn.execute(f"""
                SELECT COALESCE(SUM(producao), 0) as producao
                FROM producao_diaria
                WHERE mes_referencia = ? AND colaborador_id IN ({placeholders})
            """, (m, *operadores_ativos_ids)).fetchone()
            meta_row = conn.execute(f"""
                SELECT COALESCE(SUM(meta_dia), 0) as meta FROM (
                    SELECT MAX(meta) as meta_dia
                    FROM producao_diaria
                    WHERE mes_referencia = ? AND colaborador_id IN ({placeholders})
                    GROUP BY colaborador_id, data
                )
            """, (m, *operadores_ativos_ids)).fetchone()
            evolucao_mensal.append({
                "mes": m,
                "producao": producao_row["producao"] or 0,
                "meta": meta_row["meta"] or 0
            })

    # ── Evolução anual (ano corrente) por operador ativo ───────────────
    ano = mes[:4]
    evolucao_anual = []
    if operadores_ativos_ids:
        placeholders = ",".join("?" * len(operadores_ativos_ids))
        rows = conn.execute(f"""
            SELECT c.nome as colaborador, COALESCE(SUM(p.producao), 0) as total
            FROM producao_diaria p
            JOIN colaboradores c ON p.colaborador_id = c.id
            WHERE p.mes_referencia LIKE ? AND p.colaborador_id IN ({placeholders})
            GROUP BY c.id ORDER BY total DESC
        """, (f"{ano}-%", *operadores_ativos_ids)).fetchall()
        evolucao_anual = [{"colaborador": r["colaborador"], "total": r["total"] or 0} for r in rows]

    conn.close()
    return {
        "mes": mes,
        "mes_anterior": mes_ant,
        "kpis": {
            "produzido_mes": prod_atual,
            "produzido_mes_anterior": prod_ant,
            "perdas_pct": perdas_pct_atual,
            "perdas_pct_mes_anterior": perdas_pct_ant,
            "pedidos_despachados": desp_atual,
            "pedidos_despachados_mes_anterior": desp_ant,
            "produto_mais_produzido": {
                "nome": produto_top["nome"], "codigo": produto_top["codigo"], "total": produto_top["total"]
            } if produto_top else None,
        },
        "producao_por_produto": [dict(r) for r in producao_por_produto],
        "producao_por_operador": producao_por_operador_lista,
        "perdas_sobras_por_produto": [
            {"nome": r["nome"], "codigo": r["codigo"], "perda": r["perda_total"], "sobra": r["sobra_total"]}
            for r in perdas_sobras
        ],
        "perdas_sobras_totais": {"perda": perda_atual, "sobra": sobra_atual},
        "evolucao_mensal": evolucao_mensal,
        "evolucao_anual": evolucao_anual,
    }
