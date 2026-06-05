from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_conn

router = APIRouter()

class MaquinaIn(BaseModel):
    nome: str
    setor: Optional[str] = None
    meta_padrao: Optional[float] = 8000
    ativa: Optional[int] = 1

@router.get("/")
def listar():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM maquinas ORDER BY nome").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{id}")
def buscar(id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM maquinas WHERE id = ?", (id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Máquina não encontrada")
    return dict(row)

@router.post("/")
def criar(m: MaquinaIn):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO maquinas (nome, setor, meta_padrao, ativa) VALUES (?, ?, ?, ?)",
              (m.nome, m.setor, m.meta_padrao, m.ativa))
    conn.commit()
    id = c.lastrowid
    conn.close()
    return {"id": id, "mensagem": "Máquina cadastrada com sucesso"}

@router.put("/{id}")
def atualizar(id: int, m: MaquinaIn):
    conn = get_conn()
    conn.execute("UPDATE maquinas SET nome=?, setor=?, meta_padrao=?, ativa=? WHERE id=?",
                 (m.nome, m.setor, m.meta_padrao, m.ativa, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Máquina atualizada"}

@router.delete("/{id}")
def deletar(id: int):
    conn = get_conn()
    conn.execute("UPDATE maquinas SET ativa = 0 WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Máquina desativada"}
