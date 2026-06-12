import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends
from database import get_conn

def hash_password(password: str, salt: bytes = None) -> str:
    if not salt:
        salt = secrets.token_bytes(16)
    else:
        if isinstance(salt, str):
            salt = bytes.fromhex(salt)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + "." + key.hex()

def verify_password(stored_password_hash: str, provided_password: str) -> bool:
    try:
        salt_hex, key_hex = stored_password_hash.split('.')
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False

def validar_sessao_db(session_id: str) -> dict:
    if not session_id:
        return None
    conn = get_conn()
    try:
        # Busca a sessão e o usuário associado
        row = conn.execute("""
            SELECT s.session_id, s.expira_em, u.id, u.username, u.role, u.nome, u.ativo, u.deve_alterar_senha
            FROM sessoes s
            JOIN usuarios u ON s.usuario_id = u.id
            WHERE s.session_id = ?
        """, (session_id,)).fetchone()
        
        if not row:
            return None
        
        # Verifica expiração
        try:
            exp_dt = datetime.strptime(row["expira_em"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            # Caso o formato esteja diferente
            exp_dt = datetime.fromisoformat(row["expira_em"])
            
        if datetime.now() > exp_dt:
            # Sessão expirada, remove do banco
            conn.execute("DELETE FROM sessoes WHERE session_id = ?", (session_id,))
            conn.commit()
            return None
            
        if not row["ativo"]:
            return None
            
        return dict(row)
    except Exception as e:
        print("Erro ao validar sessao:", e)
        return None
    finally:
        conn.close()

async def get_current_user(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Sessão não iniciada. Faça login.")
    
    user_info = validar_sessao_db(session_id)
    if not user_info:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada. Faça login novamente.")
        
    if user_info.get("deve_alterar_senha") == 1:
        path = request.url.path
        allowed = [
            "/api/auth/me",
            "/api/auth/usuarios/self/password",
            "/api/auth/logout"
        ]
        if path not in allowed:
            raise HTTPException(status_code=403, detail="Alteração de senha obrigatória no primeiro acesso.")
        
    return user_info
