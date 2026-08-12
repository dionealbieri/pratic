from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from database import get_conn
from auth_utils import get_current_user

router = APIRouter()

class ProducaoItemIn(BaseModel):
    produto_estoque_id: Optional[int] = None
    quantidade: float = 0
    perda_quantidade: Optional[float] = 0
    sobra_quantidade: Optional[float] = 0
    tipo_perda: Optional[str] = None

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
    confirmado: Optional[bool] = False
    movimentacao_manual: Optional[bool] = False
    itens: Optional[List[ProducaoItemIn]] = None

def _salvar_itens_detalhe(cur, prod_id: int, p: "ProducaoIn"):
    """Grava o detalhe por produto de um lançamento em producao_diaria_itens.
    Se o frontend mandou a lista de itens (lançamento multi-produto), grava cada
    um. Senão, espelha o cabeçalho como um único item (lançamento de produto
    único) — assim todo lançamento, novo ou editado, sempre tem detalhe
    consultável pros relatórios por categoria/produto."""
    cur.execute("DELETE FROM producao_diaria_itens WHERE producao_diaria_id=?", (prod_id,))
    if p.itens:
        for item in p.itens:
            if (item.quantidade or 0) <= 0 and (item.perda_quantidade or 0) <= 0 and (item.sobra_quantidade or 0) <= 0:
                continue
            # tipo_perda só faz sentido quando há perda de fato; sem perda, fica NULL
            tipo_perda_item = (item.tipo_perda or p.perda_tipo) if (item.perda_quantidade or 0) > 0 else None
            cur.execute("""INSERT INTO producao_diaria_itens
                          (producao_diaria_id, produto_estoque_id, quantidade, perda_quantidade, sobra_quantidade, tipo_perda)
                          VALUES (?, ?, ?, ?, ?, ?)""",
                       (prod_id, item.produto_estoque_id, item.quantidade or 0,
                        item.perda_quantidade or 0, item.sobra_quantidade or 0, tipo_perda_item))
    else:
        tipo_perda_header = p.perda_tipo if (p.perda_quantidade or 0) > 0 else None
        cur.execute("""INSERT INTO producao_diaria_itens
                      (producao_diaria_id, produto_estoque_id, quantidade, perda_quantidade, sobra_quantidade, tipo_perda)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (prod_id, p.produto_estoque_id, p.producao,
                    p.perda_quantidade or 0, p.sobra_quantidade or 0, tipo_perda_header))

def _movimentar_estoque_item(c, prod_id: int, produto_id: int, quantidade: float,
                              perda: float, sobra: float, tipo_perda: Optional[str],
                              perda_observacao: Optional[str], col_nome: str, data: str):
    """Dá baixa da produção, devolve a sobra ao saldo e registra a perda de UM
    produto — todas as movimentações vinculadas ao lançamento via
    producao_diaria_id. Usada tanto para lançamento de produto único quanto
    para cada item de um lançamento multi-produto, para que a reversão
    (editar/excluir) sempre encontre o vínculo exato e nunca precise recorrer
    ao fallback por data+responsável, que podia atingir outros lançamentos do
    mesmo colaborador no mesmo dia."""
    consumo = quantidade or 0
    perda = perda or 0
    sobra = sobra or 0

    saldo = c.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (produto_id,)).fetchone()
    saldo_atual = saldo["quantidade"] if saldo else 0
    total_baixa = consumo + perda
    novo_saldo = max(0, saldo_atual - total_baixa)

    if consumo > 0:
        c.execute("""INSERT INTO estoque_movimentacoes
                     (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, responsavel, data, producao_diaria_id)
                     VALUES (?, 'saida', ?, ?, ?, 'Produção diária automática', ?, ?, ?)""",
                  (produto_id, consumo, saldo_atual, saldo_atual - consumo, col_nome, data, prod_id))

    saldo_apos_consumo = saldo_atual - consumo

    if sobra > 0:
        c.execute("""INSERT INTO estoque_movimentacoes
                     (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                      motivo, responsavel, data, producao_diaria_id)
                     VALUES (?, 'sobra', ?, ?, ?, 'Sobra de produção', ?, ?, ?)""",
                  (produto_id, sobra, saldo_apos_consumo, saldo_apos_consumo + sobra, col_nome, data, prod_id))
        novo_saldo = novo_saldo + sobra

    if perda > 0:
        c.execute("""INSERT INTO estoque_movimentacoes
                     (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                      motivo, tipo_perda, responsavel, observacao, data, producao_diaria_id)
                     VALUES (?, 'perda', ?, ?, ?, 'Perda na produção', ?, ?, ?, ?, ?)""",
                  (produto_id, perda, saldo_apos_consumo, novo_saldo,
                   tipo_perda or 'quebra', col_nome, perda_observacao, data, prod_id))

    if saldo:
        c.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                     (novo_saldo, produto_id))
    else:
        c.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)",
                     (produto_id, novo_saldo))

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
def registrar(p: ProducaoIn, current_user = Depends(get_current_user)):
    mes = p.data[:7]
    conn = get_conn()
    # Usuario comum nao define a meta: usa sempre a meta global da configuracao
    if current_user.get('role') != 'gestor':
        _mr = conn.execute("SELECT valor FROM configuracoes WHERE chave='meta_padrao'").fetchone()
        if _mr and _mr[0] not in (None, ''):
            p.meta = float(_mr[0])
    excedente = (p.producao - p.meta) if p.producao > 0 else 0

    _exigir = conn.execute("SELECT valor FROM configuracoes WHERE chave='exigir_pedido_producao_perfis'").fetchone()
    _perfis_exigidos = [x.strip() for x in (_exigir[0] if _exigir else '').split(',') if x.strip()]
    if current_user.get('role') in _perfis_exigidos and not (p.pedido_numero and str(p.pedido_numero).strip()):
        conn.close()
        raise HTTPException(400, "Número do pedido é obrigatório para lançar produção (configuração ativada para o seu perfil em Controle de Acesso).")

    # Aviso (nao bloqueio) de pedido repetido no mesmo dia: o frontend pede confirmacao.
    # Mesmo produto em pedidos diferentes e permitido; evitamos repetir o MESMO pedido.
    if p.pedido_numero and not p.confirmado:
        existe = conn.execute(
            "SELECT 1 FROM producao_diaria WHERE data=? AND pedido_numero=?",
            (p.data, p.pedido_numero)
        ).fetchone()
        if existe:
            conn.close()
            raise HTTPException(409, "pedido_duplicado")

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
    _salvar_itens_detalhe(c, prod_id, p)

    # ── Baixa no estoque: um item por produto (multi-produto) ou o produto único do cabeçalho
    itens_estoque = [it for it in (p.itens or []) if it.produto_estoque_id
                      and ((it.quantidade or 0) > 0 or (it.perda_quantidade or 0) > 0 or (it.sobra_quantidade or 0) > 0)]

    if itens_estoque:
        for item in itens_estoque:
            _movimentar_estoque_item(c, prod_id, item.produto_estoque_id, item.quantidade or 0,
                                      item.perda_quantidade or 0, item.sobra_quantidade or 0,
                                      item.tipo_perda or p.perda_tipo, p.perda_observacao, col_nome, p.data)

    elif p.produto_estoque_id and p.producao > 0:
        _movimentar_estoque_item(c, prod_id, p.produto_estoque_id, p.producao,
                                  perda, p.sobra_quantidade or 0,
                                  p.perda_tipo, p.perda_observacao, col_nome, p.data)

    # ── Registrar perda mesmo sem estoque vinculado
    # (pulado quando o frontend já fez as movimentações manualmente por produto —
    # caso legado de lançamento com múltiplos produtos sem nenhum item com produto_estoque_id)
    elif perda > 0 and not p.movimentacao_manual:
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
                          motivo, tipo_perda, responsavel, observacao, data, producao_diaria_id)
                         VALUES (?, 'perda', ?, ?, ?, 'Perda registrada via mobile', ?, ?, ?, ?, ?)""",
                      (primeiro_produto["id"], perda, saldo_atual, novo_saldo,
                       p.perda_tipo or 'quebra', col_nome, p.perda_observacao, p.data, prod_id))
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
    produto_estoque_id = p["produto_estoque_id"]
    perda_quantidade = p["perda_quantidade"] or 0

    col = conn.execute("SELECT nome FROM colaboradores WHERE id = ?", (colaborador_id,)).fetchone()
    col_nome = col["nome"] if col else "Operador"

    # Caminho correto: vínculo direto e exato pelo id do lançamento. Só cai no
    # "fuzzy" (operador+data+produto+motivo) para movimentações antigas,
    # criadas antes desse vínculo existir — nessas o match impreciso é o
    # melhor que dá pra fazer, mas para tudo criado a partir de agora isso
    # não é mais um problema (ver bug: editar/excluir um lançamento podia
    # reverter por engano a movimentação de OUTRO lançamento do mesmo
    # operador+produto no mesmo dia).
    movs = conn.execute(
        "SELECT * FROM estoque_movimentacoes WHERE producao_diaria_id = ?", (prod_id,)
    ).fetchall()

    if not movs:
        # Se for registro de produto único, filtramos por produto_id para não afetar outros lançamentos do mesmo operador no mesmo dia
        if produto_estoque_id:
            query = """
                SELECT * FROM estoque_movimentacoes 
                WHERE data = ? 
                  AND responsavel = ? 
                  AND produto_id = ?
                  AND producao_diaria_id IS NULL
                  AND (motivo LIKE 'Produção diária automática%' 
                       OR motivo LIKE 'Sobra de produção%' 
                       OR motivo LIKE 'Perda na produção%' 
                       OR motivo LIKE 'Perda registrada via mobile%')
            """
            params = (data, col_nome, produto_estoque_id)
            movs = conn.execute(query, params).fetchall()
        else:
            # Se produto_estoque_id for nulo, mas houver perda registrada no mobile (sem produto principal),
            # a perda foi vinculada ao primeiro_produto ativo.
            if perda_quantidade > 0:
                primeiro_produto = conn.execute("SELECT id FROM estoque_produtos WHERE ativo=1 LIMIT 1").fetchone()
                if primeiro_produto:
                    # Se for esse caso de perda avulsa, removemos apenas esse produto
                    query = """
                        SELECT * FROM estoque_movimentacoes 
                        WHERE data = ? 
                          AND responsavel = ? 
                          AND produto_id = ?
                          AND producao_diaria_id IS NULL
                          AND (motivo LIKE 'Produção diária automática%' 
                               OR motivo LIKE 'Sobra de produção%' 
                               OR motivo LIKE 'Perda na produção%' 
                               OR motivo LIKE 'Perda registrada via mobile%')
                    """
                    params = (data, col_nome, primeiro_produto["id"])
                    movs = conn.execute(query, params).fetchall()
            else:
                # Caso de múltiplos produtos (produto_estoque_id é nulo e sem perda avulsa):
                # Revertemos todos os movimentos daquele operador naquela data que comecem com os motivos de produção
                query = """
                    SELECT * FROM estoque_movimentacoes 
                    WHERE data = ? 
                      AND responsavel = ? 
                      AND producao_diaria_id IS NULL
                      AND (motivo LIKE 'Produção diária automática%' 
                           OR motivo LIKE 'Sobra de produção%' 
                           OR motivo LIKE 'Perda na produção%' 
                           OR motivo LIKE 'Perda registrada via mobile%')
                """
                params = (data, col_nome)
                movs = conn.execute(query, params).fetchall()

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
def atualizar(id: int, p: ProducaoIn, current_user = Depends(get_current_user)):
    conn = get_conn()
    try:
        cur = conn.cursor()
        existe = cur.execute("SELECT id FROM producao_diaria WHERE id = ?", (id,)).fetchone()
        if not existe:
            raise HTTPException(404, "Registro de produção não encontrado")

        _exigir = conn.execute("SELECT valor FROM configuracoes WHERE chave='exigir_pedido_producao_perfis'").fetchone()
        _perfis_exigidos = [x.strip() for x in (_exigir[0] if _exigir else '').split(',') if x.strip()]
        if current_user.get('role') in _perfis_exigidos and not (p.pedido_numero and str(p.pedido_numero).strip()):
            raise HTTPException(400, "Número do pedido é obrigatório para lançar produção (configuração ativada para o seu perfil em Controle de Acesso).")
            
        # 1. Reverter estoque antigo
        _reverter_estoque_producao(cur, id)
        
        # 2. Atualizar registro de produção
        if current_user.get('role') != 'gestor':
            _mr = conn.execute("SELECT valor FROM configuracoes WHERE chave='meta_padrao'").fetchone()
            if _mr and _mr[0] not in (None, ''):
                p.meta = float(_mr[0])
        excedente = (p.producao - p.meta) if p.producao > 0 else 0
        mes = p.data[:7]
        cur.execute("""UPDATE producao_diaria 
                        SET colaborador_id=?, maquina_id=?, data=?, mes_referencia=?, 
                            meta=?, producao=?, excedente=?, produto_estoque_id=?, perda_quantidade=?, sobra_quantidade=?, pedido_numero=?
                        WHERE id=?""",
                     (p.colaborador_id, p.maquina_id, p.data, mes, p.meta, p.producao, excedente,
                      p.produto_estoque_id, p.perda_quantidade or 0, p.sobra_quantidade or 0, p.pedido_numero, id))
        _salvar_itens_detalhe(cur, id, p)
                      
        # 3. Registrar novos movimentos de estoque
        col = cur.execute("SELECT nome FROM colaboradores WHERE id=?", (p.colaborador_id,)).fetchone()
        col_nome = col["nome"] if col else "Operador"
        perda = p.perda_quantidade or 0
        
        itens_estoque = [it for it in (p.itens or []) if it.produto_estoque_id
                          and ((it.quantidade or 0) > 0 or (it.perda_quantidade or 0) > 0 or (it.sobra_quantidade or 0) > 0)]

        if itens_estoque:
            for item in itens_estoque:
                _movimentar_estoque_item(cur, id, item.produto_estoque_id, item.quantidade or 0,
                                          item.perda_quantidade or 0, item.sobra_quantidade or 0,
                                          item.tipo_perda or p.perda_tipo, p.perda_observacao, col_nome, p.data)

        elif p.produto_estoque_id and p.producao > 0:
            _movimentar_estoque_item(cur, id, p.produto_estoque_id, p.producao,
                                      perda, p.sobra_quantidade or 0,
                                      p.perda_tipo, p.perda_observacao, col_nome, p.data)

        elif perda > 0 and not p.movimentacao_manual:
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
                              motivo, tipo_perda, responsavel, observacao, data, producao_diaria_id)
                             VALUES (?, 'perda', ?, ?, ?, 'Perda registrada via mobile', ?, ?, ?, ?, ?)""",
                          (primeiro_produto["id"], perda, saldo_atual, novo_saldo,
                           p.perda_tipo or 'quebra', col_nome, p.perda_observacao, p.data, id))
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
        cur.execute("DELETE FROM producao_diaria_itens WHERE producao_diaria_id = ?", (id,))
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

class FeriadoIn(BaseModel):
    data: str
    descricao: Optional[str] = None

@router.get("/feriados")
def listar_feriados(ano: Optional[str] = None):
    conn = get_conn()
    query = "SELECT * FROM feriados"
    params = []
    if ano:
        query += " WHERE data LIKE ?"
        params.append(f"{ano}-%")
    query += " ORDER BY data ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/feriados")
def criar_feriado(f: FeriadoIn):
    conn = get_conn()
    existe = conn.execute("SELECT id FROM feriados WHERE data=?", (f.data,)).fetchone()
    if existe:
        conn.close()
        raise HTTPException(409, "Já existe um feriado cadastrado nessa data")
    cur = conn.execute("INSERT INTO feriados (data, descricao) VALUES (?, ?)", (f.data, f.descricao))
    novo_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": novo_id, "mensagem": "Feriado cadastrado"}

@router.delete("/feriados/{id}")
def deletar_feriado(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM feriados WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Feriado removido"}

@router.get("/resumo/{mes}")
def resumo_mes(mes: str):
    conn = get_conn()
    _mr = conn.execute("SELECT valor FROM configuracoes WHERE chave='meta_padrao'").fetchone()
    meta_global = float(_mr[0]) if _mr and _mr[0] not in (None, '') else 8000
    rows = conn.execute("""
        SELECT 
            c.id as colaborador_id,
            c.nome as colaborador,
            c.tipo,
            COUNT(DISTINCT CASE WHEN p.producao > 0 THEN p.data END) as dias_trabalhados,
            SUM(p.producao) as total_producao,
            CASE WHEN COUNT(DISTINCT CASE WHEN p.producao > 0 THEN p.data END) > 0
                 THEN SUM(CASE WHEN p.producao > 0 THEN p.producao ELSE 0 END) / COUNT(DISTINCT CASE WHEN p.producao > 0 THEN p.data END)
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
        d["excedente_total"] = (d.get("total_producao") or 0) - (d.get("dias_trabalhados") or 0) * (d.get("meta") or meta_global)
        d["elegivel"] = (d["media_diaria"] or 0) >= (d["meta"] or meta_global)
        result.append(d)
    return result
