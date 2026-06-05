from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from database import get_conn
import os, base64, datetime

router = APIRouter()

class EPIIn(BaseModel):
    nome: str
    categoria: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[int] = 1

class FuncaoEPIIn(BaseModel):
    funcao: str
    epi_ids: List[int]

class EntregaIn(BaseModel):
    colaborador_id: int
    epi_id: int
    data_entrega: str
    data_validade: str
    motivo: Optional[str] = "Entrega inicial"
    responsavel: Optional[str] = None
    observacao: Optional[str] = None

class StatusEntregaIn(BaseModel):
    status: str
    motivo: Optional[str] = None

# ─── EPIs ─────────────────────────────────────────────────────────────────────

@router.get("/epis")
def listar_epis(ativo: Optional[int] = 1):
    conn = get_conn()
    query = "SELECT * FROM epis WHERE 1=1"
    params = []
    if ativo is not None:
        query += " AND ativo = ?"
        params.append(ativo)
    query += " ORDER BY categoria, nome"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/epis")
def criar_epi(e: EPIIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO epis (nome, categoria, descricao, ativo) VALUES (?,?,?,?)",
                (e.nome, e.categoria, e.descricao, e.ativo))
    conn.commit()
    id = cur.lastrowid
    conn.close()
    return {"id": id, "mensagem": "EPI cadastrado"}

@router.put("/epis/{id}")
def atualizar_epi(id: int, e: EPIIn):
    conn = get_conn()
    conn.execute("UPDATE epis SET nome=?, categoria=?, descricao=?, ativo=? WHERE id=?",
                 (e.nome, e.categoria, e.descricao, e.ativo, id))
    conn.commit()
    conn.close()
    return {"mensagem": "EPI atualizado"}

@router.delete("/epis/{id}")
def deletar_epi(id: int):
    conn = get_conn()
    conn.execute("UPDATE epis SET ativo=0 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "EPI desativado"}

# ─── FUNÇÕES × EPIs ───────────────────────────────────────────────────────────

@router.get("/funcoes-epis")
def listar_funcoes_epis():
    conn = get_conn()
    rows = conn.execute("""
        SELECT fe.funcao, fe.epi_id, e.nome as epi_nome, e.categoria
        FROM funcao_epis fe
        JOIN epis e ON fe.epi_id = e.id
        ORDER BY fe.funcao, e.nome
    """).fetchall()
    conn.close()
    result = {}
    for r in rows:
        f = r["funcao"]
        if f not in result:
            result[f] = []
        result[f].append({"epi_id": r["epi_id"], "epi_nome": r["epi_nome"], "categoria": r["categoria"]})
    return result

@router.post("/funcoes-epis")
def salvar_funcao_epis(body: FuncaoEPIIn):
    conn = get_conn()
    conn.execute("DELETE FROM funcao_epis WHERE funcao=?", (body.funcao,))
    for epi_id in body.epi_ids:
        conn.execute("INSERT INTO funcao_epis (funcao, epi_id) VALUES (?,?)", (body.funcao, epi_id))
    conn.commit()
    conn.close()
    return {"mensagem": "EPIs da função atualizados"}

@router.get("/epis-por-funcao/{funcao}")
def epis_por_funcao(funcao: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT e.* FROM funcao_epis fe
        JOIN epis e ON fe.epi_id = e.id
        WHERE fe.funcao = ? AND e.ativo = 1
    """, (funcao,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── ENTREGAS ─────────────────────────────────────────────────────────────────

@router.get("/entregas")
def listar_entregas(colaborador_id: Optional[int] = None, status: Optional[str] = None):
    conn = get_conn()
    hoje = datetime.date.today().isoformat()
    query = """
        SELECT ee.*, c.nome as colaborador_nome, c.tipo as colaborador_tipo,
               e.nome as epi_nome, e.categoria as epi_categoria,
               CASE
                 WHEN ee.status = 'devolvido' THEN 'devolvido'
                 WHEN ee.status = 'extraviado' THEN 'extraviado'
                 WHEN ee.data_validade < ? THEN 'vencido'
                 WHEN julianday(ee.data_validade) - julianday(?) <= 30 THEN 'vencendo'
                 ELSE 'ativo'
               END as status_calculado,
               CAST(julianday(ee.data_validade) - julianday(?) AS INTEGER) as dias_restantes
        FROM epi_entregas ee
        JOIN colaboradores c ON ee.colaborador_id = c.id
        JOIN epis e ON ee.epi_id = e.id
        WHERE 1=1
    """
    params = [hoje, hoje, hoje]
    if colaborador_id:
        query += " AND ee.colaborador_id = ?"
        params.append(colaborador_id)
    if status:
        query += " AND ee.status = ?"
        params.append(status)
    query += " ORDER BY ee.data_validade ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/entregas")
def registrar_entrega(e: EntregaIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO epi_entregas
        (colaborador_id, epi_id, data_entrega, data_validade, motivo, responsavel, observacao, status)
        VALUES (?,?,?,?,?,?,?,'ativo')""",
        (e.colaborador_id, e.epi_id, e.data_entrega, e.data_validade,
         e.motivo, e.responsavel, e.observacao))
    conn.commit()
    id = cur.lastrowid
    conn.close()
    return {"id": id, "mensagem": "Entrega registrada"}

@router.put("/entregas/{id}/status")
def atualizar_status(id: int, body: StatusEntregaIn):
    conn = get_conn()
    conn.execute("UPDATE epi_entregas SET status=?, observacao=? WHERE id=?",
                 (body.status, body.motivo, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Status atualizado"}

@router.delete("/entregas/{id}")
def deletar_entrega(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM epi_entregas WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Entrega removida"}

# ─── ALERTAS ─────────────────────────────────────────────────────────────────

@router.get("/alertas")
def alertas_epi():
    conn = get_conn()
    hoje = datetime.date.today().isoformat()
    vencidos = conn.execute("""
        SELECT COUNT(*) FROM epi_entregas
        WHERE data_validade < ? AND status = 'ativo'
    """, (hoje,)).fetchone()[0]
    vencendo = conn.execute("""
        SELECT COUNT(*) FROM epi_entregas
        WHERE julianday(data_validade) - julianday(?) BETWEEN 0 AND 30
        AND status = 'ativo'
    """, (hoje,)).fetchone()[0]
    rows = conn.execute("""
        SELECT c.nome as colaborador, e.nome as epi, ee.data_validade,
               CAST(julianday(ee.data_validade) - julianday(?) AS INTEGER) as dias_restantes
        FROM epi_entregas ee
        JOIN colaboradores c ON ee.colaborador_id = c.id
        JOIN epis e ON ee.epi_id = e.id
        WHERE julianday(ee.data_validade) - julianday(?) <= 30
        AND ee.status = 'ativo'
        ORDER BY ee.data_validade ASC LIMIT 10
    """, (hoje, hoje)).fetchall()
    conn.close()
    return {
        "vencidos": vencidos,
        "vencendo": vencendo,
        "lista": [dict(r) for r in rows]
    }

# ─── COMPROVANTE ─────────────────────────────────────────────────────────────

@router.get("/comprovante/{colaborador_id}")
def gerar_comprovante(colaborador_id: int):
    conn = get_conn()
    hoje = datetime.date.today().isoformat()
    col = conn.execute("SELECT * FROM colaboradores WHERE id=?", (colaborador_id,)).fetchone()
    if not col:
        conn.close()
        raise HTTPException(404, "Colaborador não encontrado")
    epis = conn.execute("""
        SELECT ee.*, e.nome as epi_nome, e.categoria,
               CAST(julianday(ee.data_validade) - julianday(?) AS INTEGER) as dias_restantes
        FROM epi_entregas ee
        JOIN epis e ON ee.epi_id = e.id
        WHERE ee.colaborador_id = ? AND ee.status = 'ativo'
        ORDER BY e.categoria, e.nome
    """, (hoje, colaborador_id)).fetchall()
    empresa = conn.execute("SELECT chave, valor FROM configuracoes WHERE chave LIKE 'empresa_%'").fetchall()
    conn.close()
    empresa_cfg = {r["chave"].replace("empresa_", ""): r["valor"] for r in empresa}
    # Compatibilidade com versões antigas do banco, que usavam apenas empresa_endereco.
    if not empresa_cfg.get("logradouro") and empresa_cfg.get("endereco"):
        empresa_cfg["logradouro"] = empresa_cfg.get("endereco", "")
    return {
        "colaborador": dict(col),
        "epis": [dict(r) for r in epis],
        "empresa": empresa_cfg,
        "data_geracao": hoje
    }
