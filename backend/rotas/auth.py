from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import secrets
import os

from database import get_conn
from auth_utils import verify_password, hash_password, get_current_user, validar_sessao_db
from vendedores import juntar_nomes, separar_nomes, vincular_pedidos_sem_vendedor

router = APIRouter()

PERFIS_VALIDOS = ['gestor', 'producao', 'comercial', 'estoque', 'expedicao']

# Modo treinador (só no servidor de treinamento): guarda a sessão do gestor que
# está conduzindo o treino, para ele poder "ver como" outro perfil e voltar.
TREINO_COOKIE = "treino_origem"

class LoginIn(BaseModel):
    username: str
    password: str

class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str
    nome: str
    vendedor_nomes: Optional[str] = ""

class UserUpdateIn(BaseModel):
    role: str
    nome: str
    ativo: int
    # None = não mexer (compatível com telas antigas que não enviam o campo)
    vendedor_nomes: Optional[str] = None

class PasswordUpdateIn(BaseModel):
    password: str

@router.post("/login")
def login(data: LoginIn, response: Response):
    username_clean = data.username.strip().lower()
    
    conn = get_conn()
    try:
        user = conn.execute("""
            SELECT id, username, password_hash, role, nome, ativo, deve_alterar_senha 
            FROM usuarios 
            WHERE username = ?
        """, (username_clean,)).fetchone()
        
        if not user:
            raise HTTPException(status_code=400, detail="Usuário ou senha incorretos")
            
        if not user["ativo"]:
            raise HTTPException(status_code=400, detail="Esta conta está desativada. Fale com o Gestor.")
            
        if not verify_password(user["password_hash"], data.password):
            raise HTTPException(status_code=400, detail="Usuário ou senha incorretos")
            
        # Gera sessão
        session_id = secrets.token_hex(32)
        expira_em = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        conn.execute("""
            INSERT INTO sessoes (session_id, usuario_id, expira_em)
            VALUES (?, ?, ?)
        """, (session_id, user["id"], expira_em))
        conn.commit()
        
        # Define cookie HTTPOnly
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=86400,
            path="/"
        )
        # Login novo encerra qualquer "Trocar perfil" do treinamento neste navegador
        response.delete_cookie(key=TREINO_COOKIE, path="/")
        
        return {
            "mensagem": "Autenticado com sucesso",
            "usuario": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "nome": user["nome"],
                "deve_alterar_senha": bool(user["deve_alterar_senha"])
            }
        }
    finally:
        conn.close()

@router.post("/logout")
def logout(response: Response, current_user = Depends(get_current_user)):
    conn = get_conn()
    try:
        # Pega a sessão atual do request para deletar do banco
        # (Opcional, mas limpa o banco)
        session_id = current_user.get("session_id")
        if session_id:
            conn.execute("DELETE FROM sessoes WHERE session_id = ?", (session_id,))
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
        
    # Limpa o cookie no navegador
    response.delete_cookie(key="session_id", path="/")
    response.delete_cookie(key=TREINO_COOKIE, path="/")
    return {"mensagem": "Sessão encerrada com sucesso"}

@router.get("/me")
def get_me(current_user = Depends(get_current_user)):
    role = current_user["role"]
    
    # Busca as permissões associadas a esta role nas configurações
    conn = get_conn()
    try:
        row = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (f"perm_{role}",)).fetchone()
        permissions = ""
        if row:
            permissions = row["valor"]
        else:
            # Fallback padrão caso não exista a chave no banco
            defaults = {
                "gestor":   "dashboard,producao,premiacao,pintura,colaboradores,maquinas,pedidos,estoque,epi,saldo-demanda,consumo-medio,gerencial,comunicacao,graficos,relatorios,configuracoes,backup,permissoes,empresa,mobile,estoque_mobile",
                "producao": "dashboard,producao,premiacao,pintura,colaboradores,maquinas,epi,relatorios",
                "comercial":"dashboard,pedidos,relatorios",
                "estoque":  "dashboard,estoque,consumo-medio,relatorios,estoque_mobile",
                "expedicao":"dashboard,pedidos"
            }
            permissions = defaults.get(role, "")

        # Comunicação é liberada por USUÁRIO (não por setor): remove o que veio do setor
        # e adiciona de volta só se for gestor ou se o usuário estiver marcado como participante.
        perms = [p.strip() for p in permissions.split(",") if p.strip()]
        perms = [p for p in perms if p != "comunicacao"]
        com_ativa = False
        canais = []
        try:
            urow = conn.execute("SELECT comunicacao_ativa, canais_permitidos FROM usuarios WHERE id = ?", (current_user["id"],)).fetchone()
            if urow:
                com_ativa = bool(urow["comunicacao_ativa"])
                if role == "gestor":
                    canais = ["geral", "producao", "comercial", "estoque"]
                elif urow["canais_permitidos"]:
                    canais = [c.strip() for c in urow["canais_permitidos"].split(",") if c.strip()]
        except Exception:
            com_ativa = False
        if role == "gestor" or com_ativa:
            perms.append("comunicacao")
        permissions = ",".join(perms)

        return {
            "id": current_user["id"],
            "username": current_user["username"],
            "role": role,
            "nome": current_user["nome"],
            "deve_alterar_senha": bool(current_user.get("deve_alterar_senha")),
            "permissions": permissions,
            "canais": canais
        }
    finally:
        conn.close()

# ─── ROTAS DE GESTÃO DE USUÁRIOS (Restritas a Gestor / Admin) ─────────────────

def verificar_gestor(current_user = Depends(get_current_user)):
    if current_user["role"] != "gestor":
        raise HTTPException(status_code=403, detail="Acesso restrito ao perfil de Gestor.")
    return current_user

@router.get("/usuarios")
def listar_usuarios(current_user = Depends(verificar_gestor)):
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT id, username, role, nome, ativo, criado_em,
                   COALESCE(vendedor_nomes, '') AS vendedor_nomes
            FROM usuarios 
            ORDER BY nome
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/vendedores")
def listar_vendedores(current_user = Depends(verificar_gestor)):
    """Usuários que podem ser vendedor de um pedido (para o Gestor atribuir)."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT id, nome, role, COALESCE(vendedor_nomes, '') AS vendedor_nomes
            FROM usuarios
            WHERE ativo = 1
            ORDER BY CASE WHEN role = 'comercial' THEN 0 ELSE 1 END, nome
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@router.post("/usuarios")
def criar_usuario(data: UserCreateIn, current_user = Depends(verificar_gestor)):
    username_clean = data.username.strip().lower()
    
    if data.role not in PERFIS_VALIDOS:
        raise HTTPException(status_code=400, detail="Perfil de acesso inválido.")
        
    conn = get_conn()
    try:
        # Verifica duplicidade
        dup = conn.execute("SELECT id FROM usuarios WHERE username = ?", (username_clean,)).fetchone()
        if dup:
            raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso.")
            
        password_hash = hash_password(data.password)
        
        conn.execute("""
            INSERT INTO usuarios (username, password_hash, role, nome, vendedor_nomes)
            VALUES (?, ?, ?, ?, ?)
        """, (username_clean, password_hash, data.role, data.nome.strip(),
              juntar_nomes(separar_nomes(data.vendedor_nomes))))
        vinculados = vincular_pedidos_sem_vendedor(conn)
        conn.commit()
        return {"mensagem": "Usuário criado com sucesso", "pedidos_vinculados": vinculados}
    finally:
        conn.close()

@router.put("/usuarios/{id}")
def atualizar_usuario(id: int, data: UserUpdateIn, current_user = Depends(verificar_gestor)):
    if data.role not in PERFIS_VALIDOS:
        raise HTTPException(status_code=400, detail="Perfil de acesso inválido.")
        
    conn = get_conn()
    try:
        # Não permite que o gestor se desative ou mude a própria role por acidente
        if id == current_user["id"]:
            if data.ativo == 0:
                raise HTTPException(status_code=400, detail="Você não pode desativar seu próprio usuário logado.")
            if data.role != "gestor":
                raise HTTPException(status_code=400, detail="Você não pode alterar o perfil do seu próprio usuário logado.")
                
        conn.execute("""
            UPDATE usuarios 
            SET role = ?, nome = ?, ativo = ?
            WHERE id = ?
        """, (data.role, data.nome.strip(), data.ativo, id))
        if data.vendedor_nomes is not None:
            conn.execute("UPDATE usuarios SET vendedor_nomes = ? WHERE id = ?",
                         (juntar_nomes(separar_nomes(data.vendedor_nomes)), id))
        vinculados = vincular_pedidos_sem_vendedor(conn)
        conn.commit()
        return {"mensagem": "Usuário atualizado com sucesso", "pedidos_vinculados": vinculados}
    finally:
        conn.close()

@router.put("/usuarios/self/password")
def alterar_senha_propria(data: PasswordUpdateIn, current_user = Depends(get_current_user)):
    if not data.password or len(data.password.strip()) < 3:
        raise HTTPException(status_code=400, detail="A senha deve conter no mínimo 3 caracteres.")
        
    conn = get_conn()
    try:
        password_hash = hash_password(data.password)
        conn.execute("""
            UPDATE usuarios 
            SET password_hash = ?, deve_alterar_senha = 0 
            WHERE id = ?
        """, (password_hash, current_user["id"]))
        conn.commit()
        return {"mensagem": "Senha alterada com sucesso"}
    finally:
        conn.close()

@router.put("/usuarios/{id}/password")
def alterar_senha_usuario(id: int, data: PasswordUpdateIn, current_user = Depends(verificar_gestor)):
    if not data.password or len(data.password.strip()) < 3:
        raise HTTPException(status_code=400, detail="A senha deve conter no mínimo 3 caracteres.")
        
    conn = get_conn()
    try:
        password_hash = hash_password(data.password)
        conn.execute("UPDATE usuarios SET password_hash = ?, deve_alterar_senha = 1 WHERE id = ?", (password_hash, id))
        conn.commit()
        return {"mensagem": "Senha alterada com sucesso"}
    finally:
        conn.close()

@router.delete("/usuarios/{id}")
def deletar_usuario(id: int, current_user = Depends(verificar_gestor)):
    if id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Você não pode excluir seu próprio usuário logado.")
        
    conn = get_conn()
    try:
        # Exclui usuário e deleta todas as sessões dele
        conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
        conn.execute("DELETE FROM sessoes WHERE usuario_id = ?", (id,))
        # Pedidos desse vendedor voltam para a lista "sem vendedor vinculado"
        conn.execute("UPDATE pedidos SET vendedor_usuario_id = NULL WHERE vendedor_usuario_id = ?", (id,))
        conn.commit()
        return {"mensagem": "Usuário excluído com sucesso"}
    finally:
        conn.close()

# ─── PERMISSÕES POR USUÁRIO ───────────────────────────────────────────────────

MODULOS_ACOES = {
    'dashboard':      ['ver'],
    'producao':       ['ver','criar','editar','deletar'],
    'premiacao':      ['ver','criar','editar','deletar'],
    'colaboradores':  ['ver','criar','editar','deletar'],
    'maquinas':       ['ver','criar','editar','deletar'],
    'pedidos':        ['ver','criar','editar','deletar','importar'],
    'estoque':        ['ver','criar','editar','deletar','movimentar'],
    'epi':            ['ver','criar','editar','deletar'],
    'saldo-demanda':  ['ver'],
    'graficos':       ['ver'],
    'relatorios':     ['ver','exportar'],
    'configuracoes':  ['ver','editar'],
    'backup':         ['backup','restaurar','limpar'],
    'permissoes':     ['ver','editar'],
    'empresa':        ['ver','editar'],
    'expedicao':      ['ver','despachar','desfazer'],
}

PERMISSOES_GESTOR = {modulo: acoes for modulo, acoes in MODULOS_ACOES.items()}

@router.get("/usuarios/{id}/permissoes")
def get_permissoes_usuario(id: int, current_user = Depends(verificar_gestor)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT modulo, acao, permitido FROM usuario_permissoes WHERE usuario_id = ?", (id,)
    ).fetchall()
    conn.close()
    # Se não tem permissões definidas, retornar estrutura vazia
    result = {}
    for modulo, acoes in MODULOS_ACOES.items():
        result[modulo] = {}
        for acao in acoes:
            result[modulo][acao] = False
    # Sobrescrever com o que está no banco
    for r in rows:
        if r['modulo'] in result and r['acao'] in result[r['modulo']]:
            result[r['modulo']][r['acao']] = bool(r['permitido'])
    return result

@router.put("/usuarios/{id}/permissoes")
def salvar_permissoes_usuario(id: int, body: dict, current_user = Depends(verificar_gestor)):
    conn = get_conn()
    # Verificar se usuário existe
    usr = conn.execute("SELECT id, role FROM usuarios WHERE id = ?", (id,)).fetchone()
    if not usr:
        conn.close()
        raise HTTPException(404, "Usuário não encontrado")
    # Salvar cada permissão
    for modulo, acoes in body.items():
        if modulo not in MODULOS_ACOES:
            continue
        for acao, permitido in acoes.items():
            if acao not in MODULOS_ACOES.get(modulo, []):
                continue
            conn.execute("""
                INSERT INTO usuario_permissoes (usuario_id, modulo, acao, permitido)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(usuario_id, modulo, acao) DO UPDATE SET permitido = excluded.permitido
            """, (id, modulo, acao, 1 if permitido else 0))
    conn.commit()
    conn.close()
    return {"mensagem": "Permissões salvas com sucesso"}

@router.get("/me/permissoes")
def get_minhas_permissoes(current_user = Depends(get_current_user)):
    conn = get_conn()
    usuario_id = current_user['id']
    role = current_user['role']
    rows = conn.execute(
        "SELECT modulo, acao, permitido FROM usuario_permissoes WHERE usuario_id = ?",
        (usuario_id,)
    ).fetchall()
    conn.close()

    # Gestor tem tudo liberado
    if role == 'gestor':
        result = {}
        for modulo, acoes in MODULOS_ACOES.items():
            result[modulo] = {acao: True for acao in acoes}
        return result

    # Se tem permissões definidas no banco, usar elas
    if rows:
        result = {}
        for modulo, acoes in MODULOS_ACOES.items():
            result[modulo] = {acao: False for acao in acoes}
        for r in rows:
            if r['modulo'] in result:
                result[r['modulo']][r['acao']] = bool(r['permitido'])
        return result

    # Sem permissões definidas — retornar tudo negado
    return {modulo: {acao: False for acao in acoes} for modulo, acoes in MODULOS_ACOES.items()}


# ─── MODO TREINADOR: TROCAR DE PERFIL COM UM CLIQUE ─────────────────────────────
# Só existe quando PRATIC_AMBIENTE=treinamento (Coolify). Na produção as rotas
# respondem 404 e nada muda. Quem pode trocar: um Gestor logado (ou o Gestor que
# começou a troca, guardado no cookie treino_origem).

ROTULOS_PERFIL = [
    ("gestor", "🖥️ Gestor"),
    ("comercial", "🏢 Comercial"),
    ("producao", "🏭 Produção"),
    ("estoque", "📦 Estoque"),
    ("expedicao", "🚚 Expedição"),
]


def _em_treinamento() -> bool:
    return (os.environ.get("PRATIC_AMBIENTE") or "").strip().lower() == "treinamento"


def _treinador(request: Request):
    """Devolve (usuario_gestor, session_id_do_gestor) ou (None, None)."""
    for sid in (request.cookies.get(TREINO_COOKIE), request.cookies.get("session_id")):
        u = validar_sessao_db(sid) if sid else None
        if u and u.get("role") == "gestor":
            return u, sid
    return None, None


def _exigir_treinador(request: Request):
    if not _em_treinamento():
        raise HTTPException(status_code=404, detail="Disponível só no ambiente de treinamento.")
    treinador, sid = _treinador(request)
    if not treinador:
        raise HTTPException(status_code=403, detail="Só o Gestor que conduz o treinamento pode trocar de perfil.")
    return treinador, sid


@router.get("/treino/perfis")
def treino_perfis(request: Request):
    treinador, _sid = _exigir_treinador(request)
    atual = validar_sessao_db(request.cookies.get("session_id")) or treinador
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT id, nome, username, role FROM usuarios
            WHERE ativo = 1 ORDER BY nome COLLATE NOCASE
        """).fetchall()
    finally:
        conn.close()
    perfis = []
    for role, rotulo in ROTULOS_PERFIL:
        perfis.append({
            "role": role,
            "rotulo": rotulo,
            "usuarios": [{"id": r["id"], "nome": r["nome"], "username": r["username"]}
                         for r in rows if r["role"] == role],
        })
    return {
        "treinador": {"id": treinador["id"], "nome": treinador["nome"]},
        "atual": {"id": atual["id"], "nome": atual["nome"], "role": atual["role"]},
        "perfis": perfis,
    }


class TreinoEntrarIn(BaseModel):
    usuario_id: Optional[int] = None
    role: Optional[str] = None


@router.post("/treino/entrar")
def treino_entrar(data: TreinoEntrarIn, request: Request, response: Response):
    treinador, sid_treinador = _exigir_treinador(request)
    conn = get_conn()
    try:
        alvo = None
        if data.usuario_id:
            alvo = conn.execute("SELECT id, nome, username, role, ativo FROM usuarios WHERE id = ?",
                                (data.usuario_id,)).fetchone()
            if not alvo or not alvo["ativo"]:
                raise HTTPException(status_code=404, detail="Usuário não encontrado ou desativado.")
        elif data.role in PERFIS_VALIDOS:
            alvo = conn.execute("""SELECT id, nome, username, role, ativo FROM usuarios
                                   WHERE role = ? AND ativo = 1 ORDER BY id LIMIT 1""", (data.role,)).fetchone()
            if not alvo:
                # Nenhum usuário com esse perfil no treino: cria um só para o treinamento
                rotulo = dict(ROTULOS_PERFIL).get(data.role, data.role).split(" ", 1)[-1]
                username = f"treino.{data.role}"
                conn.execute("""INSERT OR IGNORE INTO usuarios (username, password_hash, role, nome, deve_alterar_senha)
                                VALUES (?, ?, ?, ?, 0)""",
                             (username, hash_password(secrets.token_hex(16)), data.role, f"Treino {rotulo}"))
                alvo = conn.execute("SELECT id, nome, username, role, ativo FROM usuarios WHERE username = ?",
                                    (username,)).fetchone()
        else:
            raise HTTPException(status_code=400, detail="Informe o usuário ou o perfil.")

        sid_atual = request.cookies.get("session_id")
        # Sessão "emprestada" anterior (não é a do treinador): descarta
        if sid_atual and sid_atual != sid_treinador:
            conn.execute("DELETE FROM sessoes WHERE session_id = ?", (sid_atual,))

        if alvo["id"] == treinador["id"]:
            nova_sid = sid_treinador          # voltou para o próprio usuário
        else:
            # No treino ninguém fica preso na tela de "troque a senha"
            conn.execute("UPDATE usuarios SET deve_alterar_senha = 0 WHERE id = ?", (alvo["id"],))
            nova_sid = secrets.token_hex(32)
            expira_em = (datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO sessoes (session_id, usuario_id, expira_em) VALUES (?, ?, ?)",
                         (nova_sid, alvo["id"], expira_em))
        conn.commit()
    finally:
        conn.close()

    response.set_cookie(key="session_id", value=nova_sid, httponly=True, samesite="lax", max_age=86400, path="/")
    response.set_cookie(key=TREINO_COOKIE, value=sid_treinador, httponly=True, samesite="lax", max_age=86400, path="/")
    return {"usuario": {"id": alvo["id"], "nome": alvo["nome"], "username": alvo["username"], "role": alvo["role"]}}
