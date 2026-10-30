from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict
from database import get_conn
from auth_utils import get_current_user
import socket

router = APIRouter()

# Chaves que só o Gestor pode alterar (controle de acesso e regras do fluxo de pedidos)
CHAVES_SO_GESTOR = {
    "vendedor_mostrar_desde", "prazo_amarelo_dias", "prazo_vermelho_dias",
    "exigir_pedido_producao_perfis", "chat_p2p_permitido",
}
# Chaves ligadas a uma página específica: quem tem a página liberada no perfil pode alterar
CHAVE_PAGINA = {
    "svd_categorias_ocultas": "saldo-demanda",
}


def _paginas_do_perfil(role: str) -> list:
    conn = get_conn()
    try:
        r = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (f"perm_{role}",)).fetchone()
        return [p.strip() for p in ((r["valor"] if r else "") or "").split(",") if p.strip()]
    finally:
        conn.close()


def exigir_gestor_ou_pagina(current_user: dict, pagina: str = None):
    """Gestor sempre pode. Outros perfis só se a página estiver liberada para o perfil."""
    if current_user.get("role") == "gestor":
        return
    if pagina and pagina in _paginas_do_perfil(current_user.get("role") or ""):
        return
    raise HTTPException(403, "Acesso restrito ao Gestor.")

class ConfigIn(BaseModel):
    valor: str

# ── ROTAS ESPECÍFICAS PRIMEIRO (antes do /{chave})

@router.get("/permissoes/all")
def get_permissoes():
    conn = get_conn()
    rows = conn.execute("""
        SELECT chave, valor FROM configuracoes 
        WHERE chave LIKE 'perm_%'
        ORDER BY chave
    """).fetchall()
    conn.close()
    if not rows:
        return {
            "perm_gestor":   "dashboard,producao,premiacao,colaboradores,maquinas,pedidos,estoque,epi,graficos,relatorios,configuracoes,backup,permissoes,empresa,mobile,estoque_mobile",
            "perm_producao": "dashboard,producao,premiacao,colaboradores,maquinas,epi,relatorios",
            "perm_comercial":"dashboard,pedidos,relatorios",
            "perm_estoque":  "dashboard,estoque,relatorios,estoque_mobile",
            "perm_expedicao":"dashboard,pedidos"
        }
    return {r["chave"]: r["valor"] for r in rows}

@router.get("/local-ip")
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return {"ip": ip}
    except Exception:
        try:
            return {"ip": socket.gethostbyname(socket.gethostname())}
        except Exception:
            return {"ip": "127.0.0.1"}

@router.post("/permissoes/salvar")
async def salvar_permissoes(request: Request, current_user: dict = Depends(get_current_user)):
    exigir_gestor_ou_pagina(current_user)
    body = await request.json()
    conn = get_conn()
    perfis = {
        "perm_gestor":   "Gestor",
        "perm_producao": "Produção",
        "perm_comercial":"Comercial",
        "perm_estoque":  "Estoque",
        "perm_expedicao":"Expedição"
    }
    salvos = 0
    for chave, valor in body.items():
        if chave.startswith("perm_"):
            nome = perfis.get(chave, chave)
            conn.execute("""INSERT OR REPLACE INTO configuracoes (chave, valor, descricao)
                           VALUES (?, ?, ?)""",
                        (chave, str(valor), f"Permissões do perfil {nome}"))
            salvos += 1
    conn.commit()
    conn.close()
    return {"mensagem": f"Permissões salvas ({salvos} perfis)"}


@router.get("/empresa")
def buscar_empresa():
    """Retorna todos os Dados da Empresa em uma única chamada."""
    campos = ["nome", "cnpj", "telefone", "email", "cep", "logradouro", "numero", "bairro", "complemento", "cidade", "uf", "logo"]
    conn = get_conn()
    rows = conn.execute(
        "SELECT chave, valor FROM configuracoes WHERE chave LIKE 'empresa_%'"
    ).fetchall()
    conn.close()
    dados = {campo: "" for campo in campos}
    for row in rows:
        chave = row["chave"].replace("empresa_", "", 1)
        if chave in dados:
            dados[chave] = row["valor"] or ""
        elif chave == "endereco" and not dados.get("logradouro"):
            # Compatibilidade com banco antigo: se logradouro estiver vazio e endereco existir
            dados["logradouro"] = row["valor"] or ""
    return dados


def _salvar_empresa_payload(body: Dict):
    """Salva todos os Dados da Empresa em uma transação, preservando campos não enviados."""
    permitidos = {
        "nome": "Nome da empresa",
        "cnpj": "CNPJ da empresa",
        "telefone": "Telefone da empresa",
        "email": "E-mail da empresa",
        "cep": "CEP da empresa",
        "logradouro": "Logradouro da empresa",
        "numero": "Número da empresa",
        "bairro": "Bairro da empresa",
        "complemento": "Complemento da empresa",
        "cidade": "Cidade da empresa",
        "uf": "UF da empresa",
        "logo": "Logo da empresa em base64",
    }
    conn = get_conn()
    try:
        for campo, descricao in permitidos.items():
            if campo not in body:
                continue
            valor = body.get(campo)
            if valor is None:
                valor = ""
            conn.execute("""
                INSERT INTO configuracoes (chave, valor, descricao)
                VALUES (?, ?, ?)
                ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, descricao = excluded.descricao
            """, ("empresa_" + campo, str(valor), descricao))
        conn.commit()
    finally:
        conn.close()
    return {"mensagem": "Dados da empresa salvos"}

@router.post("/empresa")
async def salvar_empresa(request: Request, current_user: dict = Depends(get_current_user)):
    exigir_gestor_ou_pagina(current_user, "empresa")
    body = await request.json()
    return _salvar_empresa_payload(body)

@router.put("/empresa")
async def salvar_empresa_put(request: Request, current_user: dict = Depends(get_current_user)):
    # Rota de compatibilidade: evita erro 405 em versões do frontend/cache que enviem PUT.
    exigir_gestor_ou_pagina(current_user, "empresa")
    body = await request.json()
    return _salvar_empresa_payload(body)

@router.post("/empresa/salvar")
async def salvar_empresa_alias(request: Request, current_user: dict = Depends(get_current_user)):
    # Alias para evitar conflito com rotas genéricas antigas em atualizações parciais.
    exigir_gestor_ou_pagina(current_user, "empresa")
    body = await request.json()
    return _salvar_empresa_payload(body)

# ── ROTAS GENÉRICAS POR ÚLTIMO

@router.get("/")
def listar():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM configuracoes WHERE chave NOT LIKE 'perm_%' ORDER BY chave"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/limpar/{tipo}")
def limpar_dados(tipo: str, current_user: dict = Depends(get_current_user)):
    exigir_gestor_ou_pagina(current_user)
    conn = get_conn()
    try:
        if tipo == 'producao':
            conn.execute("DELETE FROM producao_diaria_itens")
            conn.execute("DELETE FROM producao_diaria")
            conn.execute("DELETE FROM producao_pintura")
            conn.execute("DELETE FROM premiacao_operador")
            conn.execute("DELETE FROM premiacao_auxiliar")
            msg = "Produção diária, pintura e premiações removidas"
        elif tipo == 'pedidos':
            conn.execute("DELETE FROM producao_programada")
            conn.execute("DELETE FROM pedidos_parcelas")
            conn.execute("DELETE FROM pedidos_itens")
            conn.execute("DELETE FROM pedidos")
            msg = "Pedidos e itens removidos"
        elif tipo == 'estoque_mov':
            conn.execute("DELETE FROM estoque_movimentacoes")
            # Zerar saldos
            conn.execute("UPDATE estoque_saldo SET quantidade = 0")
            msg = "Movimentações de estoque removidas e saldos zerados"
        elif tipo == 'tudo':
            conn.execute("DELETE FROM producao_diaria_itens")
            conn.execute("DELETE FROM producao_diaria")
            conn.execute("DELETE FROM producao_pintura")
            conn.execute("DELETE FROM premiacao_operador")
            conn.execute("DELETE FROM premiacao_auxiliar")
            conn.execute("DELETE FROM producao_programada")
            conn.execute("DELETE FROM pedidos_parcelas")
            conn.execute("DELETE FROM pedidos_itens")
            conn.execute("DELETE FROM pedidos")
            conn.execute("DELETE FROM estoque_movimentacoes")
            conn.execute("UPDATE estoque_saldo SET quantidade = 0")
            conn.execute("DELETE FROM epi_entregas")
            msg = "Todos os dados operacionais removidos"
        else:
            raise HTTPException(400, "Tipo inválido")
        conn.commit()
        return {"mensagem": msg}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

@router.put("/{chave}")
def atualizar(chave: str, config: ConfigIn, current_user: dict = Depends(get_current_user)):
    if chave.startswith("perm_") or chave.startswith("empresa_") or chave in CHAVES_SO_GESTOR:
        exigir_gestor_ou_pagina(current_user, "empresa" if chave.startswith("empresa_") else None)
    else:
        # Demais configurações (metas, bonificações...) são da página Configurações
        exigir_gestor_ou_pagina(current_user, CHAVE_PAGINA.get(chave, "configuracoes"))
    conn = get_conn()
    conn.execute("""
        INSERT INTO configuracoes (chave, valor, descricao)
        VALUES (?, ?, ?)
        ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
    """, (chave, config.valor, f"Configuração {chave}"))
    conn.commit()
    conn.close()
    return {"mensagem": "Configuração atualizada"}

@router.get("/{chave}")
def buscar(chave: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
    conn.close()
    if not row:
        return {"chave": chave, "valor": ""}
    return dict(row)

