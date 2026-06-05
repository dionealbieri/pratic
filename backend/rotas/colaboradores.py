from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_conn

router = APIRouter()

class ColaboradorIn(BaseModel):
    nome: str
    tipo: str  # 'operador' ou 'auxiliar'
    maquina_id: Optional[int] = None
    ativo: Optional[int] = 1

@router.get("/")
def listar(tipo: Optional[str] = None):
    conn = get_conn()
    if tipo:
        rows = conn.execute("""
            SELECT c.*, m.nome as maquina_nome 
            FROM colaboradores c
            LEFT JOIN maquinas m ON c.maquina_id = m.id
            WHERE c.tipo = ? AND c.ativo = 1
            ORDER BY c.nome
        """, (tipo,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT c.*, m.nome as maquina_nome 
            FROM colaboradores c
            LEFT JOIN maquinas m ON c.maquina_id = m.id
            WHERE c.ativo = 1
            ORDER BY c.nome
        """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{id}")
def buscar(id: int):
    conn = get_conn()
    row = conn.execute("""
        SELECT c.*, m.nome as maquina_nome 
        FROM colaboradores c
        LEFT JOIN maquinas m ON c.maquina_id = m.id
        WHERE c.id = ?
    """, (id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Colaborador não encontrado")
    return dict(row)

@router.post("/")
def criar(col: ColaboradorIn):
    if col.tipo not in ("operador", "auxiliar"):
        raise HTTPException(400, "Tipo deve ser 'operador' ou 'auxiliar'")
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id, ativo) VALUES (?, ?, ?, ?)",
              (col.nome, col.tipo, col.maquina_id, col.ativo))
    conn.commit()
    id = c.lastrowid
    conn.close()
    return {"id": id, "mensagem": "Colaborador cadastrado com sucesso"}

@router.put("/{id}")
def atualizar(id: int, col: ColaboradorIn):
    conn = get_conn()
    conn.execute("UPDATE colaboradores SET nome=?, tipo=?, maquina_id=?, ativo=? WHERE id=?",
                 (col.nome, col.tipo, col.maquina_id, col.ativo, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Colaborador atualizado"}

@router.delete("/{id}")
def deletar(id: int):
    conn = get_conn()
    conn.execute("UPDATE colaboradores SET ativo = 0 WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Colaborador desativado"}
