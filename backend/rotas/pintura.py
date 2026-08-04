from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from database import get_conn

router = APIRouter()


class PinturaIn(BaseModel):
    colaborador_id: int
    data: str
    pedido_numero: Optional[str] = None
    produto_estoque_id: Optional[int] = None
    quantidade_cores: int = 1
    quantidade_pintada: float = 0
    perda_quantidade: float = 0
    perda_tipo: Optional[str] = None
    perda_observacao: Optional[str] = None
    sobra_quantidade: float = 0


def _mes_anterior_pintura(mes: str) -> str:
    ano, m = int(mes[:4]), int(mes[5:7])
    if m == 1:
        return f"{ano - 1}-12"
    return f"{ano}-{m - 1:02d}"


def _ultimos_meses_pintura(mes: str, n: int) -> list:
    meses = [mes]
    atual = mes
    for _ in range(n - 1):
        atual = _mes_anterior_pintura(atual)
        meses.append(atual)
    return list(reversed(meses))


@router.get("/gerencial-resumo")
def gerencial_resumo(mes: Optional[str] = None):
    if not mes:
        from datetime import datetime
        mes = datetime.now().strftime("%Y-%m")
    conn = get_conn()

    produtividade = conn.execute("""
        SELECT c.nome as colaborador, COUNT(*) as lancamentos,
               SUM(p.quantidade_pintada) as total_pintado
        FROM producao_pintura p
        JOIN colaboradores c ON p.colaborador_id = c.id
        WHERE p.mes_referencia = ?
        GROUP BY c.id
        ORDER BY total_pintado DESC
    """, (mes,)).fetchall()

    perdas_motivo = conn.execute("""
        SELECT COALESCE(perda_tipo, 'Não informado') as motivo,
               COUNT(*) as lancamentos, SUM(perda_quantidade) as total_perda
        FROM producao_pintura
        WHERE mes_referencia = ? AND perda_quantidade > 0
        GROUP BY perda_tipo
        ORDER BY total_perda DESC
    """, (mes,)).fetchall()

    cores = conn.execute("""
        SELECT quantidade_cores as cores, COUNT(*) as lancamentos,
               SUM(quantidade_pintada) as total_pintado
        FROM producao_pintura
        WHERE mes_referencia = ?
        GROUP BY quantidade_cores
        ORDER BY quantidade_cores
    """, (mes,)).fetchall()

    # Pedidos marcados como "precisa de pintura" que ainda não têm nenhum
    # lançamento de pintura vinculado — pendencia independe do mes filtrado
    # (um pedido antigo ainda pendente continua pendente).
    pendentes = conn.execute("""
        SELECT p.numero_pedido, c.razao_social as cliente, p.prazo_entrega, p.status
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.precisa_pintura = 1
          AND p.status != 'entregue'
          AND NOT EXISTS (
              SELECT 1 FROM producao_pintura pp WHERE pp.pedido_numero = p.numero_pedido
          )
        ORDER BY p.prazo_entrega ASC
    """).fetchall()

    evolucao = []
    for m in _ultimos_meses_pintura(mes, 6):
        r = conn.execute("""
            SELECT COALESCE(SUM(quantidade_pintada), 0) as total
            FROM producao_pintura WHERE mes_referencia = ?
        """, (m,)).fetchone()
        evolucao.append({"mes": m, "total_pintado": r["total"] or 0})

    conn.close()
    return {
        "mes": mes,
        "produtividade_por_colaborador": [dict(r) for r in produtividade],
        "perdas_por_motivo": [dict(r) for r in perdas_motivo],
        "distribuicao_cores": [dict(r) for r in cores],
        "pedidos_pendentes": [dict(r) for r in pendentes],
        "evolucao_mensal": evolucao,
    }


@router.get("/relatorio-por-produto")
def relatorio_por_produto(mes_ini: Optional[str] = None, mes_fim: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT
            COALESCE(ep.codigo, '—') as produto_codigo,
            COALESCE(ep.nome, 'Sem produto vinculado') as produto_nome,
            COUNT(*) as lancamentos,
            SUM(p.quantidade_pintada) as total_pintado,
            SUM(p.perda_quantidade) as total_perda,
            SUM(p.sobra_quantidade) as total_sobra
        FROM producao_pintura p
        LEFT JOIN estoque_produtos ep ON p.produto_estoque_id = ep.id
        WHERE 1=1
    """
    params = []
    if mes_ini:
        query += " AND p.mes_referencia >= ?"
        params.append(mes_ini)
    if mes_fim:
        query += " AND p.mes_referencia <= ?"
        params.append(mes_fim)
    query += " GROUP BY p.produto_estoque_id ORDER BY total_pintado DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/")
def listar(mes: Optional[str] = None, data: Optional[str] = None, pedido_numero: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT p.*, c.nome as colaborador_nome, ep.codigo as produto_codigo, ep.nome as produto_nome
        FROM producao_pintura p
        JOIN colaboradores c ON p.colaborador_id = c.id
        LEFT JOIN estoque_produtos ep ON p.produto_estoque_id = ep.id
        WHERE 1=1
    """
    params = []
    if mes:
        query += " AND p.mes_referencia = ?"
        params.append(mes)
    if data:
        query += " AND p.data = ?"
        params.append(data)
    if pedido_numero:
        query += " AND p.pedido_numero = ?"
        params.append(pedido_numero)
    query += " ORDER BY p.data DESC, p.criado_em DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/")
def criar(p: PinturaIn):
    if p.quantidade_cores not in (1, 2, 3):
        raise HTTPException(400, "Quantidade de cores deve ser 1, 2 ou 3")
    if p.quantidade_pintada < 0 or p.perda_quantidade < 0 or p.sobra_quantidade < 0:
        raise HTTPException(400, "Quantidades não podem ser negativas")

    conn = get_conn()
    mes = p.data[:7] if p.data else None
    cur = conn.cursor()
    # Registro de produtividade/perdas apenas — deliberadamente NÃO mexe em
    # estoque_saldo/estoque_movimentacoes nem em meta/premiação. A baixa de
    # estoque continua acontecendo só na etapa de impressão (Produção Diária).
    cur.execute("""
        INSERT INTO producao_pintura
            (colaborador_id, data, mes_referencia, pedido_numero, produto_estoque_id,
             quantidade_cores, quantidade_pintada, perda_quantidade, perda_tipo,
             perda_observacao, sobra_quantidade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (p.colaborador_id, p.data, mes, p.pedido_numero, p.produto_estoque_id,
          p.quantidade_cores, p.quantidade_pintada, p.perda_quantidade, p.perda_tipo,
          p.perda_observacao, p.sobra_quantidade))
    novo_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": novo_id, "mensagem": "Lançamento de pintura registrado"}


@router.put("/{id}")
def atualizar(id: int, p: PinturaIn):
    if p.quantidade_cores not in (1, 2, 3):
        raise HTTPException(400, "Quantidade de cores deve ser 1, 2 ou 3")
    if p.quantidade_pintada < 0 or p.perda_quantidade < 0 or p.sobra_quantidade < 0:
        raise HTTPException(400, "Quantidades não podem ser negativas")

    conn = get_conn()
    existe = conn.execute("SELECT id FROM producao_pintura WHERE id=?", (id,)).fetchone()
    if not existe:
        conn.close()
        raise HTTPException(404, "Lançamento não encontrado")

    mes = p.data[:7] if p.data else None
    conn.execute("""
        UPDATE producao_pintura SET
            colaborador_id=?, data=?, mes_referencia=?, pedido_numero=?, produto_estoque_id=?,
            quantidade_cores=?, quantidade_pintada=?, perda_quantidade=?, perda_tipo=?,
            perda_observacao=?, sobra_quantidade=?
        WHERE id=?
    """, (p.colaborador_id, p.data, mes, p.pedido_numero, p.produto_estoque_id,
          p.quantidade_cores, p.quantidade_pintada, p.perda_quantidade, p.perda_tipo,
          p.perda_observacao, p.sobra_quantidade, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Lançamento de pintura atualizado"}


@router.delete("/{id}")
def deletar(id: int):
    conn = get_conn()
    existe = conn.execute("SELECT id FROM producao_pintura WHERE id=?", (id,)).fetchone()
    if not existe:
        conn.close()
        raise HTTPException(404, "Lançamento não encontrado")
    conn.execute("DELETE FROM producao_pintura WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Lançamento removido"}
