from fastapi import FastAPI, UploadFile, File, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import os, shutil, tempfile, datetime, base64, sqlite3

from database import init_db, seed_data
from auth_utils import get_current_user, validar_sessao_db
from rotas import auth, colaboradores, maquinas, producao, premiacao, configuracoes, relatorios, estoque, pedidos, epi

app = FastAPI(title="PRATIC - Sistema de Produção")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Rota estável para importação — fora de /api/pedidos para não conflitar com /{id}
@app.post("/api/importar-pedido-arquivo", dependencies=[Depends(get_current_user)])
async def importar_pedido_arquivo_estavel(file: UploadFile = File(...)):
    from rotas.pedidos import _processar_arquivo_pedido
    return await _processar_arquivo_pedido(file)

# Rota de autenticação aberta (internamente possui endpoints abertos e fechados)
app.include_router(auth.router,           prefix="/api/auth",           tags=["Autenticação"])

# Rotas de API protegidas por padrão
app.include_router(colaboradores.router,  prefix="/api/colaboradores",  tags=["Colaboradores"], dependencies=[Depends(get_current_user)])
app.include_router(maquinas.router,       prefix="/api/maquinas",       tags=["Máquinas"],      dependencies=[Depends(get_current_user)])
app.include_router(producao.router,       prefix="/api/producao",       tags=["Produção"],      dependencies=[Depends(get_current_user)])
app.include_router(premiacao.router,      prefix="/api/premiacao",      tags=["Premiação"],     dependencies=[Depends(get_current_user)])
app.include_router(configuracoes.router,  prefix="/api/configuracoes",  tags=["Configurações"], dependencies=[Depends(get_current_user)])
app.include_router(relatorios.router,     prefix="/api/relatorios",     tags=["Relatórios"],    dependencies=[Depends(get_current_user)])
app.include_router(estoque.router,        prefix="/api/estoque",        tags=["Estoque"],       dependencies=[Depends(get_current_user)])
app.include_router(pedidos.router,        prefix="/api/pedidos",        tags=["Pedidos"],       dependencies=[Depends(get_current_user)])
app.include_router(epi.router,            prefix="/api/epi",            tags=["EPI"],           dependencies=[Depends(get_current_user)])

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
js_path = os.path.join(frontend_path, "js")
css_path = os.path.join(frontend_path, "css")

app.mount("/js", StaticFiles(directory=js_path), name="js")
app.mount("/css", StaticFiles(directory=css_path), name="css")

# Rota de login (aberta)
@app.get("/login")
def login_page(request: Request):
    session_id = request.cookies.get("session_id")
    if validar_sessao_db(session_id):
        return RedirectResponse(url="/")
    return FileResponse(os.path.join(frontend_path, "login.html"))

@app.get("/")
def root(request: Request):
    session_id = request.cookies.get("session_id")
    if not validar_sessao_db(session_id):
        return RedirectResponse(url="/login")
    return FileResponse(os.path.join(frontend_path, "index.html"))



@app.get("/favicon.ico")
def favicon():
    # Não requer login para evitar loops e carregar o ícone
    return FileResponse(os.path.join(frontend_path, "index.html"), media_type="text/html")

@app.get("/mobile")
def mobile():
    # Servido sem redirecionamento backend. O JS interno valida a sessão via API
    # e exibe a barreira de login amigável se necessário.
    return FileResponse(os.path.join(frontend_path, "mobile.html"))

@app.get("/comercial")
def comercial(request: Request):
    session_id = request.cookies.get("session_id")
    if not validar_sessao_db(session_id):
        return RedirectResponse(url="/login")
    return FileResponse(os.path.join(frontend_path, "comercial.html"))

@app.get("/producao-setor")
def producao_setor(request: Request):
    session_id = request.cookies.get("session_id")
    if not validar_sessao_db(session_id):
        return RedirectResponse(url="/login")
    return FileResponse(os.path.join(frontend_path, "producao.html"))

@app.get("/estoque-mobile")
def estoque_mobile():
    # Servido sem redirecionamento backend. O JS interno trata a autenticação.
    return FileResponse(os.path.join(frontend_path, "estoque-mobile.html"))

@app.get("/manual")
@app.get("/manual.html")
def manual(request: Request):
    session_id = request.cookies.get("session_id")
    if not validar_sessao_db(session_id):
        return RedirectResponse(url="/login")
    return FileResponse(os.path.join(frontend_path, "manual.html"))

@app.get("/api/backup", dependencies=[Depends(get_current_user)])
def fazer_backup():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "banco", "pratic.db"))
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"pratic_backup_{now}.db"
    backup_path = os.path.join(tempfile.gettempdir(), backup_name)
    shutil.copy2(db_path, backup_path)
    return FileResponse(path=backup_path, filename=backup_name, media_type="application/octet-stream")

@app.post("/api/restore", dependencies=[Depends(get_current_user)])
async def restaurar_backup(file: UploadFile = File(...)):
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "banco", "pratic.db"))
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(db_path, db_path + f".bak_{now}")
    contents = await file.read()
    with open(db_path, "wb") as f:
        f.write(contents)
    return {"mensagem": "Banco de dados restaurado com sucesso! Reinicie o servidor."}

@app.post("/api/empresa/logo", dependencies=[Depends(get_current_user)])
async def upload_logo(file: UploadFile = File(...)):
    contents = await file.read()
    ext = file.filename.split(".")[-1].lower()
    b64 = base64.b64encode(contents).decode()
    data_url = f"data:image/{ext};base64,{b64}"
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "banco", "pratic.db"))
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT OR REPLACE INTO configuracoes (chave, valor, descricao) VALUES ('empresa_logo', ?, 'Logo da empresa em base64')", (data_url,))
    conn.commit()
    conn.close()
    return {"mensagem": "Logo salvo", "url": data_url[:50] + "..."}

@app.on_event("startup")
def startup():
    init_db()
    seed_data()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
