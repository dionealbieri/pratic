"""Treinamento do Comercial — só funciona com PRATIC_AMBIENTE=treinamento.

- Registra o que cada usuário FAZ no treino (gravações na API: importar pedido,
  cadastrar cliente, definir envio...) e alguns cliques marcados pela tela
  (tour, busca, ver detalhes).
- Confere sozinho as "missões" de cada vendedor a partir desse registro.
- Mostra ao Gestor treinador o progresso da turma (painel 📋 Turma).

Na produção/teste as rotas respondem 404 e nada é gravado.
"""
import os
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from database import get_conn
from auth_utils import get_current_user, validar_sessao_db

router = APIRouter()


def em_treinamento() -> bool:
    return (os.environ.get("PRATIC_AMBIENTE") or "").strip().lower() == "treinamento"


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _tabelas(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS treino_eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,              -- 'api' (gravação no sistema) ou 'tela' (clique marcado)
        metodo TEXT, caminho TEXT,
        em TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_treino_eventos_usr ON treino_eventos(usuario_id, em)")
    conn.execute("""CREATE TABLE IF NOT EXISTS treino_missoes (
        usuario_id INTEGER PRIMARY KEY,
        inicio TEXT NOT NULL)""")


# ─── missões ─────────────────────────────────────────────────────────────────
# (id, ícone, título, dica, como confere, precisa da Programação liberada)
#   como confere: ("tela", tipo)  ou  ("api", regex "METODO caminho")
MISSOES = [
    ("tour", "🧭", "Fazer o tour da tela",
     "Clique em “▶ Começar tour” aqui neste painel e siga os balões.",
     ("tela", "tour"), False),
    ("busca", "🔎", "Encontrar um pedido pela busca",
     "Em 🧾 Meus Pedidos, digite na busca o número de um pedido ou o nome de um cliente.",
     ("tela", "busca"), False),
    ("detalhe", "👁️", "Abrir os detalhes de um pedido",
     "Clique no ⋯ de um pedido e escolha “👁 Ver detalhes”.",
     ("tela", "detalhe"), False),
    ("importar", "📥", "Importar um pedido",
     "Aba 📥 Importar → envie o PDF (ou foto) de um pedido e salve. Use um pedido que ainda não esteja no sistema.",
     ("api", r"^POST /api/(pedidos/importar-arquivos-lote|pedidos/?|pedidos/\d+/arquivo-original)$"), False),
    ("cliente", "🏢", "Cadastrar um cliente novo",
     "Na importação, quando o cliente não existir, cadastre-o (buscando pelo CNPJ).",
     ("api", r"^POST /api/pedidos/clientes/?$"), False),
    ("info", "📝", "Passar informações para a produção",
     "No pedido, preencha cor da impressão, marca, arte e observação para a produção.",
     ("api", r"^PUT /api/programacao/pedido/\d+/info$"), True),
    ("pagamento", "💳", "Registrar a forma de pagamento",
     "Na mesma tela do pedido, escolha a condição de pagamento.",
     ("api", r"^PUT /api/programacao/pedido/\d+/pagamento$"), True),
    ("prioridade", "⚡", "Pedir prioridade para um pedido",
     "Marque “pedir prioridade” e explique o motivo — o gestor aprova ou recusa.",
     ("api", r"^POST /api/programacao/pedido/\d+/prioridade$"), True),
    ("envio", "🚚", "Definir o envio de um pedido",
     "Num pedido pronto, use o ⋯ para enviar a cotação de frete ou marcar 🙋 Cliente retira.",
     ("api", r"^POST /api/(pedidos/\d+/(definir-envio|enviar-cotacao|autorizar-cotacao)|remessas/pedido/\d+(/cotacao)?)$"), False),
]

# Rótulos para o painel do treinador (o que a pessoa fez, em português)
ROTULOS_API = [
    (r"^POST /api/pedidos/importar-arquivos-lote$", "📥 Importou pedido(s) em lote"),
    (r"^POST /api/pedidos/?$", "📥 Salvou um pedido"),
    (r"^POST /api/pedidos/\d+/arquivo-original$", "📎 Anexou o PDF original do pedido"),
    (r"^POST /api/importar-pedido-arquivo$", "📄 Leu um arquivo de pedido"),
    (r"^POST /api/pedidos/clientes/?$", "🏢 Cadastrou cliente"),
    (r"^PUT /api/pedidos/\d+$", "✏️ Editou um pedido"),
    (r"^DELETE /api/pedidos/\d+$", "🗑 Excluiu um pedido"),
    (r"^PUT /api/programacao/pedido/\d+/info$", "📝 Informações para a produção"),
    (r"^PUT /api/programacao/pedido/\d+/pagamento$", "💳 Forma de pagamento"),
    (r"^POST /api/programacao/pedido/\d+/prioridade$", "⚡ Pediu prioridade"),
    (r"^DELETE /api/programacao/pedido/\d+/prioridade$", "↩ Cancelou pedido de prioridade"),
    (r"^POST /api/programacao/pedido/\d+/arte$", "🎨 Anexou arte"),
    (r"^POST /api/pedidos/\d+/enviar-cotacao$", "📨 Enviou cotação de frete"),
    (r"^POST /api/pedidos/\d+/definir-envio$", "🚚 Definiu o envio"),
    (r"^POST /api/pedidos/\d+/autorizar-cotacao$", "✅ Autorizou cotação"),
    (r"^POST /api/pedidos/\d+/cancelar-cotacao$", "↩ Cancelou cotação"),
    (r"^POST /api/remessas/pedido/\d+(/cotacao)?$", "📦 Criou envio parcial"),
    (r"^POST /api/remessas/\d+/autorizar$", "✅ Autorizou remessa"),
    (r"^POST /api/remessas/\d+/cancelar$", "✕ Cancelou remessa"),
    (r"^POST /api/pedidos/meus/visto$", None),          # ruído: marcar novidades como vistas
]
ROTULOS_TELA = {"tour": "🧭 Concluiu o tour", "busca": "🔎 Usou a busca", "detalhe": "👁️ Abriu detalhes de um pedido"}


def _rotulo(ev) -> str:
    if ev["tipo"] == "tela":
        return ROTULOS_TELA.get(ev["caminho"], ev["caminho"])
    chave = f'{ev["metodo"]} {ev["caminho"]}'
    for rx, rot in ROTULOS_API:
        if re.match(rx, chave):
            return rot
    return chave.replace("/api/", "")


# ─── registro (chamado pelo middleware do main.py) ──────────────────────────
IGNORAR = ("/api/auth", "/api/treino", "/api/ambiente", "/api/pedidos/meus/visto", "/api/comunicacao")


def registrar_api(session_id: str, metodo: str, caminho: str):
    if not em_treinamento() or not session_id or caminho.startswith(IGNORAR):
        return
    u = validar_sessao_db(session_id)
    if not u:
        return
    conn = get_conn()
    try:
        _tabelas(conn)
        conn.execute("INSERT INTO treino_eventos (usuario_id, tipo, metodo, caminho, em) VALUES (?, 'api', ?, ?, ?)",
                     (u["id"], metodo, caminho.rstrip("/") or caminho, _agora()))
        conn.commit()
    finally:
        conn.close()


def _exigir_treino():
    if not em_treinamento():
        raise HTTPException(status_code=404, detail="Disponível só no ambiente de treinamento.")


def _inicio(conn, uid: int) -> str:
    r = conn.execute("SELECT inicio FROM treino_missoes WHERE usuario_id = ?", (uid,)).fetchone()
    if r:
        return r["inicio"]
    ini = _agora()
    conn.execute("INSERT INTO treino_missoes (usuario_id, inicio) VALUES (?, ?)", (uid, ini))
    conn.commit()
    return ini


def _prog_liberada(conn) -> bool:
    try:
        from rotas.programacao import _liberada
        return bool(_liberada(conn))
    except Exception:
        return False


def _progresso(conn, uid: int, inicio: str, liberada: bool):
    evs = conn.execute("SELECT tipo, metodo, caminho FROM treino_eventos WHERE usuario_id = ? AND em >= ?",
                       (uid, inicio)).fetchall()
    tela = {e["caminho"] for e in evs if e["tipo"] == "tela"}
    api = [f'{e["metodo"]} {e["caminho"]}' for e in evs if e["tipo"] == "api"]
    out = []
    for mid, ico, tit, dica, (modo, alvo), precisa_prog in MISSOES:
        feita = (alvo in tela) if modo == "tela" else any(re.match(alvo, a) for a in api)
        out.append({"id": mid, "icone": ico, "titulo": tit, "dica": dica, "feita": feita,
                    "disponivel": liberada or not precisa_prog})
    return out


@router.get("/missoes")
def minhas_missoes(current_user: dict = Depends(get_current_user)):
    _exigir_treino()
    if current_user.get("role") != "comercial" and not current_user.get("tambem_vendedor"):
        return {"aplicavel": False}
    conn = get_conn()
    try:
        _tabelas(conn)
        ini = _inicio(conn, current_user["id"])
        lib = _prog_liberada(conn)
        ms = _progresso(conn, current_user["id"], ini, lib)
    finally:
        conn.close()
    validas = [m for m in ms if m["disponivel"]]
    return {"aplicavel": True, "inicio": ini, "programacao_liberada": lib, "missoes": ms,
            "feitas": sum(1 for m in validas if m["feita"]), "total": len(validas)}


@router.post("/missoes/reiniciar")
def reiniciar_missoes(current_user: dict = Depends(get_current_user)):
    _exigir_treino()
    conn = get_conn()
    try:
        _tabelas(conn)
        conn.execute("INSERT OR REPLACE INTO treino_missoes (usuario_id, inicio) VALUES (?, ?)",
                     (current_user["id"], _agora()))
        conn.commit()
    finally:
        conn.close()
    return {"mensagem": "Missões recomeçadas"}


class EventoTelaIn(BaseModel):
    tipo: str


@router.post("/evento")
def evento_tela(body: EventoTelaIn, current_user: dict = Depends(get_current_user)):
    _exigir_treino()
    if body.tipo not in ROTULOS_TELA:
        raise HTTPException(status_code=400, detail="Evento desconhecido")
    conn = get_conn()
    try:
        _tabelas(conn)
        conn.execute("INSERT INTO treino_eventos (usuario_id, tipo, metodo, caminho, em) VALUES (?, 'tela', NULL, ?, ?)",
                     (current_user["id"], body.tipo, _agora()))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.get("/turma")
def turma(request: Request):
    """Painel do treinador: progresso de cada vendedor e o que fez por último."""
    _exigir_treino()
    from rotas.auth import _exigir_treinador
    _exigir_treinador(request)
    conn = get_conn()
    try:
        _tabelas(conn)
        lib = _prog_liberada(conn)
        usuarios = conn.execute("""SELECT id, nome, username FROM usuarios
                                   WHERE (role = 'comercial' OR COALESCE(tambem_vendedor,0) = 1) AND ativo = 1
                                   ORDER BY nome COLLATE NOCASE""").fetchall()
        lista = []
        for u in usuarios:
            r = conn.execute("SELECT inicio FROM treino_missoes WHERE usuario_id = ?", (u["id"],)).fetchone()
            ult = conn.execute("""SELECT tipo, metodo, caminho, em FROM treino_eventos
                                  WHERE usuario_id = ? ORDER BY id DESC LIMIT 40""", (u["id"],)).fetchall()
            if not r and not ult:
                continue                      # ainda não entrou no treino
            ini = r["inicio"] if r else "0000"
            ms = _progresso(conn, u["id"], ini, lib)
            validas = [m for m in ms if m["disponivel"]]
            acoes = []
            for e in ult:
                rot = _rotulo(e)
                if rot:
                    acoes.append({"em": e["em"], "acao": rot})
                if len(acoes) >= 10:
                    break
            lista.append({
                "id": u["id"], "nome": u["nome"], "username": u["username"], "inicio": r["inicio"] if r else None,
                "feitas": sum(1 for m in validas if m["feita"]), "total": len(validas),
                "missoes": [{"icone": m["icone"], "titulo": m["titulo"], "feita": m["feita"], "disponivel": m["disponivel"]} for m in ms],
                "ultima_atividade": ult[0]["em"] if ult else None,
                "acoes": acoes,
            })
    finally:
        conn.close()
    lista.sort(key=lambda x: x["ultima_atividade"] or "", reverse=True)
    return {"programacao_liberada": lib, "vendedores": lista, "agora": _agora()}
