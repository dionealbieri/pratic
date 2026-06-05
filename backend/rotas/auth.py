from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
import secrets

from database import get_conn
from auth_utils import verify_password, hash_password, get_current_user

router = APIRouter()

class LoginIn(BaseModel):
    username: str
    password: str

class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str
    nome: str

class UserUpdateIn(BaseModel):
    role: str
    nome: str
    ativo: int

class PasswordUpdateIn(BaseModel):
    password: str

@router.post("/login")
def login(data: LoginIn, response: Response):
    username_clean = data.username.strip().lower()
    
    conn = get_conn()
    try:
        user = conn.execute("""
            SELECT id, username, password_hash, role, nome, ativo 
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
        
        return {
            "mensagem": "Autenticado com sucesso",
            "usuario": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "nome": user["nome"]
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
                "gestor":   "dashboard,producao,premiacao,colaboradores,maquinas,pedidos,estoque,epi,graficos,relatorios,configuracoes,backup,permissoes,empresa,mobile,estoque_mobile",
                "producao": "dashboard,producao,premiacao,colaboradores,maquinas,epi,relatorios",
                "comercial":"dashboard,pedidos,relatorios",
                "estoque":  "dashboard,estoque,relatorios,estoque_mobile"
            }
            permissions = defaults.get(role, "")
            
        return {
            "id": current_user["id"],
            "username": current_user["username"],
            "role": role,
            "nome": current_user["nome"],
            "permissions": permissions
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
            SELECT id, username, role, nome, ativo, criado_em 
            FROM usuarios 
            ORDER BY nome
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@router.post("/usuarios")
def criar_usuario(data: UserCreateIn, current_user = Depends(verificar_gestor)):
    username_clean = data.username.strip().lower()
    
    if data.role not in ['gestor', 'producao', 'comercial', 'estoque']:
        raise HTTPException(status_code=400, detail="Perfil de acesso inválido.")
        
    conn = get_conn()
    try:
        # Verifica duplicidade
        dup = conn.execute("SELECT id FROM usuarios WHERE username = ?", (username_clean,)).fetchone()
        if dup:
            raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso.")
            
        password_hash = hash_password(data.password)
        
        conn.execute("""
            INSERT INTO usuarios (username, password_hash, role, nome)
            VALUES (?, ?, ?, ?)
        """, (username_clean, password_hash, data.role, data.nome.strip()))
        conn.commit()
        return {"mensagem": "Usuário criado com sucesso"}
    finally:
        conn.close()

@router.put("/usuarios/{id}")
def atualizar_usuario(id: int, data: UserUpdateIn, current_user = Depends(verificar_gestor)):
    if data.role not in ['gestor', 'producao', 'comercial', 'estoque']:
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
        conn.commit()
        return {"mensagem": "Usuário atualizado com sucesso"}
    finally:
        conn.close()

@router.put("/usuarios/{id}/password")
def alterar_senha_usuario(id: int, data: PasswordUpdateIn, current_user = Depends(verificar_gestor)):
    if not data.password or len(data.password.strip()) < 3:
        raise HTTPException(status_code=400, detail="A senha deve conter no mínimo 3 caracteres.")
        
    conn = get_conn()
    try:
        password_hash = hash_password(data.password)
        conn.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (password_hash, id))
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
        conn.commit()
        return {"mensagem": "Usuário excluído com sucesso"}
    finally:
        conn.close()
