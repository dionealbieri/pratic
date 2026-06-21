import os
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from database import get_conn, DB_PATH
from auth_utils import get_current_user

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(DB_PATH), "uploads", "comunicacao")
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
EXT_PERMITIDAS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv",
}
SETORES = ("producao", "comercial", "estoque")


class ResolverIn(BaseModel):
    resolvido: bool = True


class ParticipanteIn(BaseModel):
    ativa: bool = True


class ChatP2PConfigIn(BaseModel):
    p2p_permitido: bool


class CanaisPermitidosIn(BaseModel):
    canais: List[str]


def _row_to_dict(r):
    d = dict(r)
    d["tem_anexo"] = bool(d.get("anexo_arquivo"))
    d.pop("anexo_arquivo", None)
    return d


def _apagar_arquivo(nome_arquivo):
    if not nome_arquivo:
        return
    try:
        caminho = os.path.join(UPLOAD_DIR, nome_arquivo)
        if os.path.exists(caminho):
            os.remove(caminho)
    except Exception:
        pass


_SELECT = """SELECT id, texto, autor_id, autor_nome, autor_setor, criado_em,
                    resolvido, resolvido_por, resolvido_em,
                    anexo_nome, anexo_tipo, anexo_arquivo,
                    conversa_setor, conversa_usuario_id
             FROM comunicacao_recados"""


@router.get("/usuarios")
def listar_usuarios(current_user=Depends(get_current_user)):
    role = current_user.get("role")
    conn = get_conn()
    
    # Usuário comum deve estar com comunicação ativa
    if role != "gestor":
        urow = conn.execute("SELECT comunicacao_ativa FROM usuarios WHERE id=?", (current_user["id"],)).fetchone()
        if not urow or not urow["comunicacao_ativa"]:
            conn.close()
            raise HTTPException(403, "Você não tem acesso à Comunicação.")
            
    # Verificar se chat P2P geral está habilitado
    p2p_ok = False
    if role != "gestor":
        p2p_row = conn.execute("SELECT valor FROM configuracoes WHERE chave='chat_p2p_permitido'").fetchone()
        p2p_ok = p2p_row and p2p_row["valor"] == "1"
        
    if role == "gestor" or p2p_ok:
        # Pode ver todos os usuários ativos (gestores e colaboradores autorizados), exceto a si mesmo
        users = conn.execute(
            """SELECT id, nome, role FROM usuarios 
               WHERE ativo=1 AND id!=? AND (role='gestor' OR comunicacao_ativa=1) 
               ORDER BY CASE WHEN role='gestor' THEN 0 ELSE 1 END, role, nome""",
            (current_user["id"],)
        ).fetchall()
    else:
        # Se P2P estiver desativado, colaboradores comuns só podem ver e iniciar conversas com gestores (administradores)
        users = conn.execute(
            """SELECT id, nome, role FROM usuarios 
               WHERE ativo=1 AND id!=? AND role='gestor' 
               ORDER BY nome""",
            (current_user["id"],)
        ).fetchall()
        
    conn.close()
    return [dict(u) for u in users]


@router.get("/usuarios-todos")
def listar_usuarios_todos(current_user=Depends(get_current_user)):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Apenas o administrador.")
    conn = get_conn()
    users = conn.execute(
        "SELECT id, nome, role, comunicacao_ativa, canais_permitidos FROM usuarios WHERE ativo=1 AND role!='gestor' ORDER BY role, nome"
    ).fetchall()
    conn.close()
    return [{
        "id": u["id"],
        "nome": u["nome"],
        "role": u["role"],
        "participa": bool(u["comunicacao_ativa"]),
        "canais": [c.strip() for c in (u["canais_permitidos"] or "").split(",") if c.strip()]
    } for u in users]


@router.put("/usuarios/{usuario_id}/participante")
def definir_participante(usuario_id: int, body: ParticipanteIn, current_user=Depends(get_current_user)):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Apenas o administrador.")
    conn = get_conn()
    u = conn.execute("SELECT id, role FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    if not u or u["role"] == "gestor":
        conn.close()
        raise HTTPException(400, "Usuário inválido.")
    conn.execute("UPDATE usuarios SET comunicacao_ativa=? WHERE id=?", (1 if body.ativa else 0, usuario_id))
    conn.commit()
    conn.close()
    return {"id": usuario_id, "participa": bool(body.ativa)}


@router.get("/")
def listar_recados(
    canal: Optional[str] = None,
    usuario_id: Optional[int] = None,
    current_user=Depends(get_current_user),
):
    role = current_user.get("role")
    conn = get_conn()
    
    # 1. Se pediu por canal/grupo
    if canal:
        if role != "gestor" and canal != "geral":
            conn.close()
            raise HTTPException(403, "Você não tem permissão para acessar este canal.")
        
        rows = conn.execute(
            _SELECT + " WHERE conversa_setor=? AND conversa_usuario_id IS NULL ORDER BY id DESC",
            (canal,)
        ).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

    # 2. Se pediu conversa com um usuário específico (1:1)
    if usuario_id:
        u2 = conn.execute("SELECT id, role, ativo, comunicacao_ativa FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        if not u2 or not u2["ativo"]:
            conn.close()
            raise HTTPException(400, "Destinatário inválido.")
            
        # P2P entre dois não-gestores exige que a configuração chat_p2p_permitido esteja ligada
        if role != "gestor" and u2["role"] != "gestor":
            if usuario_id != current_user.get("id"):
                p2p_row = conn.execute("SELECT valor FROM configuracoes WHERE chave='chat_p2p_permitido'").fetchone()
                if not p2p_row or p2p_row["valor"] != "1":
                    conn.close()
                    raise HTTPException(403, "Conversas diretas entre colaboradores estão desativadas.")
        
        # Validar acesso de chat ativo para não gestores
        if role != "gestor":
            u1 = conn.execute("SELECT comunicacao_ativa FROM usuarios WHERE id=?", (current_user["id"],)).fetchone()
            if not u1 or not u1["comunicacao_ativa"]:
                conn.close()
                raise HTTPException(403, "Você não tem acesso à Comunicação.")
        if u2["role"] != "gestor" and not u2["comunicacao_ativa"]:
            conn.close()
            raise HTTPException(403, "O destinatário não tem acesso à Comunicação.")
            
        non_gestor_id = None
        if u2["role"] != "gestor":
            non_gestor_id = usuario_id
        elif role != "gestor":
            non_gestor_id = current_user["id"]
            
        if non_gestor_id is not None:
            # Pode ter histórico legado
            rows = conn.execute(
                _SELECT + """ WHERE (conversa_setor='p2p' AND ((autor_id=? AND conversa_usuario_id=?) OR (autor_id=? AND conversa_usuario_id=?)))
                              OR (conversa_setor IS NULL AND conversa_usuario_id=?) ORDER BY id DESC""",
                (current_user["id"], usuario_id, usuario_id, current_user["id"], non_gestor_id)
            ).fetchall()
        else:
            # Conversa P2P entre dois administradores
            rows = conn.execute(
                _SELECT + " WHERE conversa_setor='p2p' AND ((autor_id=? AND conversa_usuario_id=?) OR (autor_id=? AND conversa_usuario_id=?)) ORDER BY id DESC",
                (current_user["id"], usuario_id, usuario_id, current_user["id"])
            ).fetchall()
            
    else:
        if role == "gestor":
            # Admin sem usuário específico vê todos os recados
            rows = conn.execute(_SELECT + " ORDER BY id DESC").fetchall()
        else:
            # Caso geral: retornar todas as conversas/canais visíveis para este não-gestor
            query = _SELECT + " WHERE (conversa_usuario_id=? AND conversa_setor IS NULL) OR (conversa_setor='p2p' AND (autor_id=? OR conversa_usuario_id=?)) OR (conversa_usuario_id IS NULL AND conversa_setor='geral') ORDER BY id DESC"
            rows = conn.execute(query, (current_user["id"], current_user["id"], current_user["id"])).fetchall()
            
    conn.close()
    return [_row_to_dict(r) for r in rows]


@router.post("/")
async def criar_recado(
    texto: str = Form(""),
    canal: Optional[str] = Form(None),
    usuario_id: Optional[str] = Form(None),
    anexo: Optional[UploadFile] = File(None),
    current_user=Depends(get_current_user),
):
    role = current_user.get("role")
    conn = get_conn()
    
    conversa_uid = None
    conversa_setor = None
    
    # 1. Enviar para um canal/grupo
    if canal:
        if role != "gestor" and canal != "geral":
            conn.close()
            raise HTTPException(403, "Você não tem permissão para acessar este canal.")
        conversa_setor = canal
        
    # 2. Enviar mensagem 1:1
    elif usuario_id:
        try:
            alvo_id = int(usuario_id)
        except (TypeError, ValueError):
            conn.close()
            raise HTTPException(400, "Destinatário inválido.")
            
        u2 = conn.execute("SELECT id, role, ativo, comunicacao_ativa FROM usuarios WHERE id=?", (alvo_id,)).fetchone()
        if not u2 or not u2["ativo"]:
            conn.close()
            raise HTTPException(400, "Destinatário inválido.")
            
        # P2P entre dois não-gestores exige que a configuração chat_p2p_permitido esteja ligada
        if role != "gestor" and u2["role"] != "gestor":
            if alvo_id != current_user.get("id"):
                p2p_row = conn.execute("SELECT valor FROM configuracoes WHERE chave='chat_p2p_permitido'").fetchone()
                if not p2p_row or p2p_row["valor"] != "1":
                    conn.close()
                    raise HTTPException(403, "Conversas diretas entre colaboradores estão desativadas.")
                    
        # Verifique se o remetente tem chat ativo (menos gestores que sempre têm)
        if role != "gestor":
            u1 = conn.execute("SELECT comunicacao_ativa FROM usuarios WHERE id=?", (current_user["id"],)).fetchone()
            if not u1 or not u1["comunicacao_ativa"]:
                conn.close()
                raise HTTPException(403, "Acesso negado.")
                
        # Verifique se o destinatário tem chat ativo (menos gestores que sempre têm)
        if u2["role"] != "gestor" and not u2["comunicacao_ativa"]:
            conn.close()
            raise HTTPException(403, "Destinatário não tem acesso ao chat.")
            
        conversa_uid = alvo_id
        conversa_setor = 'p2p'
    else:
        if role != "gestor":
            conversa_uid = current_user.get("id")
        else:
            conn.close()
            raise HTTPException(400, "Especifique um canal ou usuário destinatário.")

    texto = (texto or "").strip()
    dados = None
    nome_orig = None
    tipo = None
    ext = ""
    if anexo is not None and anexo.filename:
        nome_orig = os.path.basename(anexo.filename)
        ext = os.path.splitext(nome_orig)[1].lower()
        if ext not in EXT_PERMITIDAS:
            conn.close()
            raise HTTPException(400, "Tipo de arquivo não permitido.")
        dados = await anexo.read()
        if len(dados) > MAX_BYTES:
            conn.close()
            raise HTTPException(400, "Arquivo muito grande (máximo 10 MB).")
        tipo = anexo.content_type or ""

    if not texto and dados is None:
        conn.close()
        raise HTTPException(400, "Envie um texto ou um arquivo.")

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO comunicacao_recados
            (texto, autor_id, autor_nome, autor_setor, conversa_setor, conversa_usuario_id)
        VALUES (?,?,?,?,?,?)
    """, (texto, current_user.get("id"), current_user.get("nome"), role, conversa_setor, conversa_uid))
    rid = cur.lastrowid

    if dados is not None:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        stored = f"{rid}{ext}"
        try:
            with open(os.path.join(UPLOAD_DIR, stored), "wb") as f:
                f.write(dados)
        except Exception:
            conn.rollback()
            conn.close()
            raise HTTPException(500, "Falha ao salvar o arquivo.")
        cur.execute("""UPDATE comunicacao_recados
            SET anexo_nome=?, anexo_tipo=?, anexo_arquivo=? WHERE id=?""",
                    (nome_orig, tipo, stored, rid))

    conn.commit()
    conn.close()
    return {"id": rid, "conversa_usuario_id": conversa_uid, "mensagem": "Mensagem enviada"}


@router.get("/anexo/{id}")
def baixar_anexo(id: int, current_user=Depends(get_current_user)):
    role = current_user.get("role")
    conn = get_conn()
    r = conn.execute(
        "SELECT anexo_nome, anexo_tipo, anexo_arquivo, conversa_usuario_id FROM comunicacao_recados WHERE id=?",
        (id,),
    ).fetchone()
    conn.close()
    if not r or not r["anexo_arquivo"]:
        raise HTTPException(404, "Anexo não encontrado")
    if role != "gestor" and r["conversa_usuario_id"] != current_user.get("id"):
        raise HTTPException(403, "Sem acesso a este anexo.")
    caminho = os.path.join(UPLOAD_DIR, r["anexo_arquivo"])
    if not os.path.exists(caminho):
        raise HTTPException(404, "Arquivo não encontrado no servidor")
    is_img = (r["anexo_tipo"] or "").startswith("image/")
    return FileResponse(
        caminho,
        media_type=r["anexo_tipo"] or "application/octet-stream",
        filename=r["anexo_nome"] or r["anexo_arquivo"],
        content_disposition_type="inline" if is_img else "attachment",
    )


@router.put("/{id}/resolver")
def resolver_recado(id: int, body: ResolverIn, current_user=Depends(get_current_user)):
    role = current_user.get("role")
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT conversa_usuario_id FROM comunicacao_recados WHERE id=?", (id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Mensagem não encontrada")
    if role != "gestor" and row["conversa_usuario_id"] != current_user.get("id"):
        conn.close()
        raise HTTPException(403, "Sem acesso a esta conversa.")
    if body.resolvido:
        cur.execute("""UPDATE comunicacao_recados
            SET resolvido=1, resolvido_por=?, resolvido_em=datetime('now') WHERE id=?""",
                    (current_user.get("nome"), id))
    else:
        cur.execute("""UPDATE comunicacao_recados
            SET resolvido=0, resolvido_por=NULL, resolvido_em=NULL WHERE id=?""", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Atualizado", "resolvido": body.resolvido}


# IMPORTANTE: rota específica antes da dinâmica /{id}
@router.delete("/conversa-usuario/{usuario_id}")
def limpar_conversa_usuario(usuario_id: int, current_user=Depends(get_current_user)):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Apenas o administrador pode limpar conversas.")
    conn = get_conn()
    arquivos = conn.execute(
        "SELECT anexo_arquivo FROM comunicacao_recados WHERE conversa_usuario_id=? AND anexo_arquivo IS NOT NULL",
        (usuario_id,),
    ).fetchall()
    conn.execute("DELETE FROM comunicacao_recados WHERE conversa_usuario_id=?", (usuario_id,))
    conn.commit()
    conn.close()
    for a in arquivos:
        _apagar_arquivo(a["anexo_arquivo"])
    return {"mensagem": "Conversa limpa"}


@router.delete("/{id}")
def excluir_recado(id: int, current_user=Depends(get_current_user)):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Apenas o administrador pode excluir mensagens.")
    conn = get_conn()
    r = conn.execute("SELECT anexo_arquivo FROM comunicacao_recados WHERE id=?", (id,)).fetchone()
    conn.execute("DELETE FROM comunicacao_recados WHERE id=?", (id,))
    conn.commit()
    conn.close()
    if r:
        _apagar_arquivo(r["anexo_arquivo"])
    return {"mensagem": "Mensagem excluída"}


@router.get("/config")
def obter_config(current_user=Depends(get_current_user)):
    conn = get_conn()
    p2p_row = conn.execute("SELECT valor FROM configuracoes WHERE chave='chat_p2p_permitido'").fetchone()
    conn.close()
    p2p_ok = p2p_row and p2p_row["valor"] == "1"
    return {"chat_p2p_permitido": p2p_ok}


@router.put("/config")
def atualizar_config(body: ChatP2PConfigIn, current_user=Depends(get_current_user)):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Apenas o administrador.")
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO configuracoes (chave, valor, descricao) VALUES ('chat_p2p_permitido', ?, 'Permitir chat 1:1 privado entre colaboradores')",
        ("1" if body.p2p_permitido else "0",)
    )
    conn.commit()
    conn.close()
    return {"chat_p2p_permitido": body.p2p_permitido}


@router.put("/usuarios/{usuario_id}/canais")
def atualizar_canais_usuario(usuario_id: int, body: CanaisPermitidosIn, current_user=Depends(get_current_user)):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Apenas o administrador.")
    conn = get_conn()
    u = conn.execute("SELECT id, role FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    if not u or u["role"] == "gestor":
        conn.close()
        raise HTTPException(400, "Usuário inválido ou administrador.")
    
    valid_channels = {"geral", "producao", "comercial", "estoque"}
    cleaned_channels = [c.strip().lower() for c in body.canais if c.strip().lower() in valid_channels]
    
    canais_str = ",".join(cleaned_channels)
    conn.execute("UPDATE usuarios SET canais_permitidos=? WHERE id=?", (canais_str, usuario_id))
    conn.commit()
    conn.close()
    return {"id": usuario_id, "canais": cleaned_channels}

