from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_conn

router = APIRouter()

class ColaboradorIn(BaseModel):
    nome: str
    tipo: str
    maquina_id: Optional[int] = None
    ativo: Optional[int] = 1

class TipoColaboradorIn(BaseModel):
    nome: str
    ativo: Optional[int] = 1


def _normalizar_tipo(nome: str) -> str:
    nome = (nome or "").strip().lower()
    if not nome:
        raise HTTPException(400, "Informe o tipo do colaborador")
    return nome

def _garantir_tabela_tipos(conn):
    """Garante que a tabela de tipos exista antes de qualquer ação de salvar/listar."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS colaborador_tipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        )
    """)
    for tipo_padrao in ("operador", "auxiliar"):
        conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (tipo_padrao,))
    for row in conn.execute("SELECT DISTINCT tipo FROM colaboradores WHERE COALESCE(tipo,'')<>''").fetchall():
        tipo = _normalizar_tipo(row[0])
        conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (tipo,))
    conn.commit()

@router.get("/tipos")
def listar_tipos():
    conn = get_conn()
    _garantir_tabela_tipos(conn)
    rows = conn.execute("SELECT * FROM colaborador_tipos WHERE ativo=1 ORDER BY CASE nome WHEN 'operador' THEN 0 WHEN 'auxiliar' THEN 1 ELSE 2 END, nome").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/tipos")
def criar_tipo(tipo: TipoColaboradorIn):
    nome = _normalizar_tipo(tipo.nome)
    conn = get_conn()
    _garantir_tabela_tipos(conn)
    existente = conn.execute("SELECT id, ativo FROM colaborador_tipos WHERE LOWER(nome)=LOWER(?)", (nome,)).fetchone()
    if existente:
        conn.execute("UPDATE colaborador_tipos SET ativo=1, nome=? WHERE id=?", (nome, existente["id"]))
        conn.commit()
        conn.close()
        return {"id": existente["id"], "nome": nome, "mensagem": "Tipo já existia e foi ativado"}
    c = conn.cursor()
    c.execute("INSERT INTO colaborador_tipos (nome, ativo) VALUES (?, ?)", (nome, tipo.ativo or 1))
    conn.commit()
    id = c.lastrowid
    conn.close()
    return {"id": id, "nome": nome, "mensagem": "Tipo cadastrado com sucesso"}

@router.delete("/tipos/{id}")
def deletar_tipo(id: int):
    conn = get_conn()
    _garantir_tabela_tipos(conn)
    row = conn.execute("SELECT nome FROM colaborador_tipos WHERE id=?", (id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Tipo não encontrado")
    em_uso = conn.execute("SELECT id FROM colaboradores WHERE LOWER(tipo)=LOWER(?) AND ativo=1 LIMIT 1", (row["nome"],)).fetchone()
    if em_uso:
        conn.close()
        raise HTTPException(400, "Este tipo está em uso por colaborador ativo")
    conn.execute("UPDATE colaborador_tipos SET ativo=0 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Tipo desativado"}

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
    tipo = _normalizar_tipo(col.tipo)
    conn = get_conn()
    _garantir_tabela_tipos(conn)
    conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (tipo,))
    c = conn.cursor()
    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id, ativo) VALUES (?, ?, ?, ?)",
              (col.nome.strip(), tipo, col.maquina_id, col.ativo))
    conn.commit()
    id = c.lastrowid
    conn.close()
    return {"id": id, "mensagem": "Colaborador cadastrado com sucesso"}

@router.put("/{id}")
def atualizar(id: int, col: ColaboradorIn):
    tipo = _normalizar_tipo(col.tipo)
    conn = get_conn()
    _garantir_tabela_tipos(conn)
    conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (tipo,))
    conn.execute("UPDATE colaboradores SET nome=?, tipo=?, maquina_id=?, ativo=? WHERE id=?",
                 (col.nome.strip(), tipo, col.maquina_id, col.ativo, id))
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
