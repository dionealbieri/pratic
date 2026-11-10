from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from database import get_conn
from auth_utils import get_current_user

router = APIRouter()

class PerdaLinhaIn(BaseModel):
    quantidade: float = 0
    tipo_perda: Optional[str] = None
    observacao: Optional[str] = None
    nao_baixar_estoque: Optional[bool] = False

class ProducaoItemIn(BaseModel):
    produto_estoque_id: Optional[int] = None
    quantidade: float = 0
    perda_quantidade: Optional[float] = 0
    sobra_quantidade: Optional[float] = 0
    tipo_perda: Optional[str] = None
    observacao: Optional[str] = None
    perdas: Optional[List[PerdaLinhaIn]] = None

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
    perdas: Optional[List[PerdaLinhaIn]] = None
    sobra_quantidade: Optional[float] = 0
    pedido_id: Optional[int] = None
    pedido_numero: Optional[str] = None
    confirmado: Optional[bool] = False
    movimentacao_manual: Optional[bool] = False
    itens: Optional[List[ProducaoItemIn]] = None

def _normalizar_perdas(perdas_list, fallback_qtd, fallback_tipo, fallback_obs):
    """Um produto pode ter vários motivos de perda no mesmo lançamento (ex:
    5 unidades quebradas + 3 com falta na embalagem). Se o frontend já manda
    a lista nova (`perdas`), usa ela. Senão, cai no formato antigo de um
    valor só — mantém lançamentos e integrações anteriores funcionando.
    Cada linha vira uma tupla (quantidade, tipo, observação, não_baixa_estoque)."""
    if perdas_list:
        return [(pl.quantidade or 0, pl.tipo_perda, pl.observacao, bool(pl.nao_baixar_estoque)) for pl in perdas_list if (pl.quantidade or 0) > 0]
    if (fallback_qtd or 0) > 0:
        return [(fallback_qtd, fallback_tipo, fallback_obs, False)]
    return []

def _salvar_itens_detalhe(cur, prod_id: int, p: "ProducaoIn"):
    """Grava o detalhe por produto de um lançamento em producao_diaria_itens.
    Se o frontend mandou a lista de itens (lançamento multi-produto), grava cada
    um. Senão, espelha o cabeçalho como um único item (lançamento de produto
    único) — assim todo lançamento, novo ou editado, sempre tem detalhe
    consultável pros relatórios por categoria/produto.
    O detalhe fino por motivo (várias linhas de perda) fica só em
    estoque_movimentacoes; aqui grava-se a SOMA (pra relatórios que só
    precisam do total, como Painel Gerencial e Premiação) e o tipo mostrado
    vira 'Múltiplos' quando há mais de um motivo diferente."""
    cur.execute("DELETE FROM producao_diaria_itens WHERE producao_diaria_id=?", (prod_id,))
    if p.itens:
        for item in p.itens:
            perdas = _normalizar_perdas(item.perdas, item.perda_quantidade, item.tipo_perda, item.observacao)
            perda_total = sum(q for q, _, _, _ in perdas)
            if (item.quantidade or 0) <= 0 and perda_total <= 0 and (item.sobra_quantidade or 0) <= 0:
                continue
            tipos_distintos = {(t or p.perda_tipo or 'Quebra') for q, t, o, nb in perdas}
            tipo_perda_item = None
            if perda_total > 0:
                tipo_perda_item = next(iter(tipos_distintos)) if len(tipos_distintos) == 1 else 'Múltiplos'
            cur.execute("""INSERT INTO producao_diaria_itens
                          (producao_diaria_id, produto_estoque_id, quantidade, perda_quantidade, sobra_quantidade, tipo_perda)
                          VALUES (?, ?, ?, ?, ?, ?)""",
                       (prod_id, item.produto_estoque_id, item.quantidade or 0,
                        perda_total, item.sobra_quantidade or 0, tipo_perda_item))
    else:
        perdas = _normalizar_perdas(p.perdas, p.perda_quantidade, p.perda_tipo, p.perda_observacao)
        perda_total = sum(q for q, _, _, _ in perdas)
        tipos_distintos = {(t or 'Quebra') for q, t, o, nb in perdas}
        tipo_perda_header = None
        if perda_total > 0:
            tipo_perda_header = next(iter(tipos_distintos)) if len(tipos_distintos) == 1 else 'Múltiplos'
        cur.execute("""INSERT INTO producao_diaria_itens
                      (producao_diaria_id, produto_estoque_id, quantidade, perda_quantidade, sobra_quantidade, tipo_perda)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (prod_id, p.produto_estoque_id, p.producao,
                    perda_total, p.sobra_quantidade or 0, tipo_perda_header))

def _movimentar_estoque_item(c, prod_id: int, produto_id: int, quantidade: float,
                              perdas: list, sobra: float, col_nome: str, data: str):
    """Dá baixa da produção, devolve a sobra ao saldo e registra a(s) perda(s)
    de UM produto — todas as movimentações vinculadas ao lançamento via
    producao_diaria_id. `perdas` é uma lista de (quantidade, tipo_perda,
    observacao): cada motivo de perda vira sua própria movimentação de
    estoque, mas o desconto do saldo é sempre a SOMA de todas elas — o
    resultado final no estoque é idêntico a antes, só o registro fica mais
    detalhado. Usada tanto para lançamento de produto único quanto para cada
    item de um lançamento multi-produto, para que a reversão (editar/excluir)
    sempre encontre o vínculo exato e nunca precise recorrer ao fallback por
    data+responsável, que podia atingir outros lançamentos do mesmo
    colaborador no mesmo dia."""
    consumo = quantidade or 0
    sobra = sobra or 0
    perdas = [(q or 0, t, o, nb) for (q, t, o, nb) in (perdas or []) if (q or 0) > 0]
    # perda com "não baixar estoque" fica registrada (pra rastreio/relatório),
    # mas não entra na conta do que sai do saldo — usada quando a reposição é
    # resolvida com o cliente por fora (abatimento em fatura), não fisicamente.
    total_perda = sum(q for q, _, _, nb in perdas if not nb)

    saldo = c.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (produto_id,)).fetchone()
    saldo_atual = saldo["quantidade"] if saldo else 0
    total_baixa = consumo + total_perda
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

    # cada motivo de perda vira uma movimentação própria — dá pra ter quantas
    # linhas forem necessárias no mesmo lançamento (ex: 5 quebradas + 3 com
    # falta na embalagem), cada uma com seu tipo e observação. Se a linha
    # estiver marcada "não baixar estoque", ela fica registrada do mesmo jeito
    # (pro histórico), só que o saldo antes/depois não muda — não desconta.
    # a perda vem DEPOIS da sobra no extrato: parte do saldo já com a sobra
    # (antes partia do saldo pré-sobra e o "saldo anterior" da linha ficava errado)
    saldo_rodante = saldo_apos_consumo + sobra
    for qtd, tipo, obs, nao_baixar in perdas:
        if nao_baixar:
            saldo_rodante_depois = saldo_rodante
            motivo_mov = 'Perda na produção (sem baixa no estoque — resolvido com o cliente)'
        else:
            saldo_rodante_depois = saldo_rodante - qtd
            motivo_mov = 'Perda na produção'
        c.execute("""INSERT INTO estoque_movimentacoes
                     (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior,
                      motivo, tipo_perda, responsavel, observacao, data, producao_diaria_id)
                     VALUES (?, 'perda', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (produto_id, qtd, saldo_rodante, saldo_rodante_depois,
                   motivo_mov, tipo or 'quebra', col_nome, obs, data, prod_id))
        saldo_rodante = saldo_rodante_depois

    if saldo:
        c.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                     (novo_saldo, produto_id))
    else:
        c.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)",
                     (produto_id, novo_saldo))

def _baixar_insumo_vinculado(c, prod_id: int, produto_id: int, quantidade: float,
                             pedido_numero, col_nome: str, data: str):
    """Se a categoria do produto exige um insumo vinculado (ex.: Chinelos exige
    Palmilha) e o item do pedido já tem esse insumo escolhido (a cor definida
    na hora da venda), dá baixa dele também, na mesma quantidade (1 par de
    insumo por par produzido) e vinculada ao MESMO lançamento (producao_diaria_id)
    — assim, editar ou excluir a produção reverte os dois juntos automaticamente,
    reaproveitando o _reverter_estoque_producao que já existe."""
    if (quantidade or 0) <= 0 or not produto_id:
        return
    cat = c.execute("""
        SELECT ec.categoria_vinculada_id
        FROM estoque_produtos ep
        JOIN estoque_categorias ec ON ep.categoria_id = ec.id
        WHERE ep.id = ?
    """, (produto_id,)).fetchone()
    if not cat or not cat["categoria_vinculada_id"]:
        return
    if not pedido_numero:
        return
    item_pedido = c.execute("""
        SELECT pi.insumo_vinculado_id
        FROM pedidos_itens pi
        JOIN pedidos pe ON pi.pedido_id = pe.id
        WHERE pe.numero_pedido = ? AND pi.produto_id = ? AND pi.insumo_vinculado_id IS NOT NULL
        LIMIT 1
    """, (str(pedido_numero), produto_id)).fetchone()
    if not item_pedido:
        return
    insumo_id = item_pedido["insumo_vinculado_id"]

    saldo = c.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (insumo_id,)).fetchone()
    saldo_atual = saldo["quantidade"] if saldo else 0
    novo_saldo = max(0, saldo_atual - quantidade)
    c.execute("""INSERT INTO estoque_movimentacoes
                 (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, responsavel, data, producao_diaria_id)
                 VALUES (?, 'saida', ?, ?, ?, 'Baixa automática — insumo vinculado à produção', ?, ?, ?)""",
              (insumo_id, quantidade, saldo_atual, novo_saldo, col_nome, data, prod_id))
    if saldo:
        c.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                  (novo_saldo, insumo_id))
    else:
        c.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)", (insumo_id, novo_saldo))

def _sincronizar_pedido(cur, *numeros):
    """Acerta o progresso dos itens do(s) pedido(s) pelo histórico de produção."""
    try:
        from rotas.pedidos import sincronizar_progresso_por_numero
    except Exception:
        return
    for n in {str(x).strip() for x in numeros if x and str(x).strip()}:
        sincronizar_progresso_por_numero(cur, n)

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

    # Soma real da perda (lista de motivos, ou o campo antigo se vier no formato
    # legado) — precisa ser calculada ANTES do INSERT, pra gravar o total certo
    # na coluna de resumo (perda_quantidade), que outros relatórios ainda usam.
    perdas_header = _normalizar_perdas(p.perdas, p.perda_quantidade, p.perda_tipo, p.perda_observacao)
    perda = sum(q for q, _, _, _ in perdas_header)

    c.execute("""INSERT INTO producao_diaria 
                 (colaborador_id, maquina_id, data, mes_referencia, meta, producao, excedente, produto_estoque_id, perda_quantidade, sobra_quantidade, pedido_numero)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (p.colaborador_id, p.maquina_id, p.data, mes, p.meta, p.producao, excedente,
               p.produto_estoque_id, perda, p.sobra_quantidade or 0, p.pedido_numero))
    prod_id = c.lastrowid
    _salvar_itens_detalhe(c, prod_id, p)

    # ── Baixa no estoque: um item por produto (multi-produto) ou o produto único do cabeçalho
    itens_estoque = [it for it in (p.itens or []) if it.produto_estoque_id
                      and ((it.quantidade or 0) > 0 or (it.perdas or it.perda_quantidade or 0) or (it.sobra_quantidade or 0) > 0)]

    if itens_estoque:
        for item in itens_estoque:
            perdas_item = _normalizar_perdas(item.perdas, item.perda_quantidade, item.tipo_perda or p.perda_tipo, item.observacao or p.perda_observacao)
            _movimentar_estoque_item(c, prod_id, item.produto_estoque_id, item.quantidade or 0,
                                      perdas_item, item.sobra_quantidade or 0, col_nome, p.data)
            _baixar_insumo_vinculado(c, prod_id, item.produto_estoque_id, item.quantidade or 0,
                                      p.pedido_numero, col_nome, p.data)

    elif p.produto_estoque_id and p.producao > 0:
        _movimentar_estoque_item(c, prod_id, p.produto_estoque_id, p.producao,
                                  perdas_header, p.sobra_quantidade or 0, col_nome, p.data)
        _baixar_insumo_vinculado(c, prod_id, p.produto_estoque_id, p.producao,
                                  p.pedido_numero, col_nome, p.data)

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

def _registrar_estorno(c, produto_id: int, efeito: float, motivo: str, usuario: str,
                       observacao: str = None, data: str = None):
    """Desfaz no saldo um efeito já aplicado (efeito = o que a movimentação original
    fez no saldo: saída de 1000 => -1000) e grava uma linha 'estorno' no extrato,
    com saldo antes/depois reais. Sem isso, excluir/editar uma movimentação fazia o
    saldo "pular" sem nenhuma linha que explicasse. A linha de estorno não tem
    producao_diaria_id: não é revertida de novo numa próxima edição."""
    from datetime import date as _date
    if not efeito:
        return None
    r = c.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (produto_id,)).fetchone()
    saldo_atual = (r["quantidade"] or 0) if r else 0
    novo = max(0, saldo_atual - efeito)
    if r:
        c.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                  (novo, produto_id))
    else:
        c.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)", (produto_id, novo))
    cur = c.execute("""INSERT INTO estoque_movimentacoes
                 (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, responsavel, observacao, data)
                 VALUES (?, 'estorno', ?, ?, ?, ?, ?, ?, ?)""",
              (produto_id, abs(efeito), saldo_atual, novo, motivo, usuario, observacao, data or str(_date.today())))
    return cur.lastrowid


def _efeito_mov(m) -> float:
    """O que a movimentação fez no saldo (negativo = baixou). Usa o antes/depois
    gravado: uma perda "sem baixa" tem antes == depois e não devolve nada."""
    sa, sp = m["saldo_anterior"], m["saldo_posterior"]
    if sa is not None and sp is not None:
        return sp - sa
    q = m["quantidade"] or 0
    return q if m["tipo"] in ("entrada", "sobra") else (-q if m["tipo"] in ("saida", "perda") else 0)


def _reverter_estoque_producao(conn, prod_id: int, usuario: str = None, acao: str = "excluído"):
    """Devolve ao estoque o que o lançamento movimentou e apaga as movimentações dele,
    deixando no extrato UMA linha de estorno por produto (quem, quando, por quê).
    Retorna {"estornos": [ids], "movs": [(produto_id, tipo, quantidade)]}."""
    info = {"estornos": [], "movs": []}
    p = conn.execute("SELECT * FROM producao_diaria WHERE id = ?", (prod_id,)).fetchone()
    if not p:
        return info

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

    efeitos = {}
    for m in movs:
        efeitos[m["produto_id"]] = efeitos.get(m["produto_id"], 0) + _efeito_mov(m)
        info["movs"].append((m["produto_id"], m["tipo"], m["quantidade"]))
        conn.execute("DELETE FROM estoque_movimentacoes WHERE id = ?", (m["id"],))
    if efeitos:
        try:
            dt = "/".join(reversed(str(data or "")[:10].split("-")))
        except Exception:
            dt = data
        ped = f" · pedido {p['pedido_numero']}" if p["pedido_numero"] else ""
        motivo = f"Estorno: lançamento de produção #{prod_id} {acao}"
        obs = f"Produção de {dt} ({col_nome}){ped}"
        for pid, ef in efeitos.items():
            eid = _registrar_estorno(conn, pid, ef, motivo, usuario or "sistema", obs)
            if eid:
                info["estornos"].append(eid)
    return info

def _nome_usr(u) -> str:
    return (u or {}).get("nome") or (u or {}).get("username") or "sistema"


def _produtos_do_lancamento(c, prod_id: int) -> set:
    ids = {r[0] for r in c.execute("SELECT produto_estoque_id FROM producao_diaria_itens WHERE producao_diaria_id=? AND produto_estoque_id IS NOT NULL", (prod_id,))}
    if not ids:
        r = c.execute("SELECT produto_estoque_id FROM producao_diaria WHERE id=?", (prod_id,)).fetchone()
        if r and r[0]:
            ids = {r[0]}
    return ids


def _nomes_produtos(c, ids) -> str:
    if not ids:
        return "—"
    ph = ",".join("?" * len(ids))
    return ", ".join(r[0] for r in c.execute(f"SELECT nome FROM estoque_produtos WHERE id IN ({ph}) ORDER BY nome", tuple(ids)))

@router.put("/{id}")
def atualizar(id: int, p: ProducaoIn, current_user = Depends(get_current_user)):
    conn = get_conn()
    try:
        cur = conn.cursor()
        existe = cur.execute("SELECT id, pedido_numero FROM producao_diaria WHERE id = ?", (id,)).fetchone()
        if not existe:
            raise HTTPException(404, "Registro de produção não encontrado")

        _exigir = conn.execute("SELECT valor FROM configuracoes WHERE chave='exigir_pedido_producao_perfis'").fetchone()
        _perfis_exigidos = [x.strip() for x in (_exigir[0] if _exigir else '').split(',') if x.strip()]
        if current_user.get('role') in _perfis_exigidos and not (p.pedido_numero and str(p.pedido_numero).strip()):
            raise HTTPException(400, "Número do pedido é obrigatório para lançar produção (configuração ativada para o seu perfil em Controle de Acesso).")
            
        # 1. Reverter estoque antigo (fica uma linha de estorno no extrato)
        prods_antes = _produtos_do_lancamento(cur, id)
        rev = _reverter_estoque_producao(cur, id, _nome_usr(current_user), "editado")
        
        # 2. Atualizar registro de produção
        if current_user.get('role') != 'gestor':
            _mr = conn.execute("SELECT valor FROM configuracoes WHERE chave='meta_padrao'").fetchone()
            if _mr and _mr[0] not in (None, ''):
                p.meta = float(_mr[0])
        excedente = (p.producao - p.meta) if p.producao > 0 else 0
        mes = p.data[:7]

        # Soma real da perda ANTES do UPDATE, pelo mesmo motivo do POST: a
        # coluna de resumo precisa do total certo, não do campo antigo vazio.
        perdas_header = _normalizar_perdas(p.perdas, p.perda_quantidade, p.perda_tipo, p.perda_observacao)
        perda = sum(q for q, _, _, _ in perdas_header)

        cur.execute("""UPDATE producao_diaria 
                        SET colaborador_id=?, maquina_id=?, data=?, mes_referencia=?, 
                            meta=?, producao=?, excedente=?, produto_estoque_id=?, perda_quantidade=?, sobra_quantidade=?, pedido_numero=?
                        WHERE id=?""",
                     (p.colaborador_id, p.maquina_id, p.data, mes, p.meta, p.producao, excedente,
                      p.produto_estoque_id, perda, p.sobra_quantidade or 0, p.pedido_numero, id))
        _salvar_itens_detalhe(cur, id, p)
                      
        # 3. Registrar novos movimentos de estoque
        col = cur.execute("SELECT nome FROM colaboradores WHERE id=?", (p.colaborador_id,)).fetchone()
        col_nome = col["nome"] if col else "Operador"
        
        itens_estoque = [it for it in (p.itens or []) if it.produto_estoque_id
                          and ((it.quantidade or 0) > 0 or (it.perdas or it.perda_quantidade or 0) or (it.sobra_quantidade or 0) > 0)]

        if itens_estoque:
            for item in itens_estoque:
                perdas_item = _normalizar_perdas(item.perdas, item.perda_quantidade, item.tipo_perda or p.perda_tipo, item.observacao or p.perda_observacao)
                _movimentar_estoque_item(cur, id, item.produto_estoque_id, item.quantidade or 0,
                                          perdas_item, item.sobra_quantidade or 0, col_nome, p.data)
                _baixar_insumo_vinculado(cur, id, item.produto_estoque_id, item.quantidade or 0,
                                          p.pedido_numero, col_nome, p.data)

        elif p.produto_estoque_id and p.producao > 0:
            _movimentar_estoque_item(cur, id, p.produto_estoque_id, p.producao,
                                      perdas_header, p.sobra_quantidade or 0, col_nome, p.data)
            _baixar_insumo_vinculado(cur, id, p.produto_estoque_id, p.producao,
                                      p.pedido_numero, col_nome, p.data)

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
                                 
        # Edição que não mudou nada no estoque (ex.: só a meta ou a máquina):
        # tira o estorno, senão cada edição encheria o extrato de linhas que se anulam.
        novas = [(r["produto_id"], r["tipo"], r["quantidade"]) for r in cur.execute(
            "SELECT produto_id, tipo, quantidade FROM estoque_movimentacoes WHERE producao_diaria_id=?", (id,))]
        if rev["estornos"] and sorted(novas) == sorted(rev["movs"]):
            ph = ",".join("?" * len(rev["estornos"]))
            cur.execute(f"DELETE FROM estoque_movimentacoes WHERE id IN ({ph})", tuple(rev["estornos"]))
        # Marca trocada direto no lançamento: fica na Auditoria (antes não ficava registro)
        prods_depois = _produtos_do_lancamento(cur, id)
        if prods_antes and prods_depois and prods_antes != prods_depois:
            cur.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                           VALUES (?, 'trocar_produto_producao', 'producao', ?, ?, ?, ?)""",
                        (_nome_usr(current_user), id,
                         f"Lançamento de produção #{id} ({p.data}) teve o produto trocado na tela de Produção"
                         + (f" · pedido {p.pedido_numero}" if p.pedido_numero else ""),
                         _nomes_produtos(cur, prods_antes), _nomes_produtos(cur, prods_depois)))
        _sincronizar_pedido(cur, existe["pedido_numero"], p.pedido_numero)
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
def deletar(id: int, current_user = Depends(get_current_user)):
    conn = get_conn()
    try:
        cur = conn.cursor()
        existe = cur.execute("SELECT id, pedido_numero, data, producao FROM producao_diaria WHERE id = ?", (id,)).fetchone()
        if not existe:
            raise HTTPException(404, "Registro de produção não encontrado")
        prods = _produtos_do_lancamento(cur, id)

        # 1. Reverter e deletar lançamentos de estoque (fica a linha de estorno no extrato)
        _reverter_estoque_producao(cur, id, _nome_usr(current_user), "excluído")
        cur.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior)
                       VALUES (?, 'excluir_producao', 'producao', ?, ?, ?)""",
                    (_nome_usr(current_user), id,
                     f"Lançamento de produção #{id} ({existe['data']}, {existe['producao'] or 0:g} un.) excluído"
                     + (f" · pedido {existe['pedido_numero']}" if existe["pedido_numero"] else ""),
                     _nomes_produtos(cur, prods)))
        
        # 2. Deletar registro de produção
        cur.execute("DELETE FROM producao_diaria_itens WHERE producao_diaria_id = ?", (id,))
        cur.execute("DELETE FROM producao_diaria WHERE id = ?", (id,))
        # 3. O pedido volta a mostrar só o que ficou lançado (antes o "produzido" do item não baixava)
        _sincronizar_pedido(cur, existe["pedido_numero"])
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
