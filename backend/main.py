from fastapi import FastAPI, UploadFile, File, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import os, shutil, tempfile, datetime, base64, sqlite3, zipfile

from database import init_db, seed_data, get_conn, DB_PATH
from auth_utils import get_current_user, validar_sessao_db
from rotas import auth, colaboradores, maquinas, producao, premiacao, configuracoes, relatorios, estoque, pedidos, epi, comunicacao, gerencial, pintura, remessas, programacao

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
app.include_router(remessas.router,        prefix="/api/remessas",        tags=["Remessas"],       dependencies=[Depends(get_current_user)])
app.include_router(epi.router,            prefix="/api/epi",            tags=["EPI"],           dependencies=[Depends(get_current_user)])
app.include_router(comunicacao.router,    prefix="/api/comunicacao",    tags=["Comunicação"],   dependencies=[Depends(get_current_user)])
app.include_router(gerencial.router,      prefix="/api/gerencial",      tags=["Gerencial"],     dependencies=[Depends(get_current_user)])
app.include_router(programacao.router,    prefix="/api/programacao",    tags=["Programação"],   dependencies=[Depends(get_current_user)])
app.include_router(pintura.router,        prefix="/api/pintura",        tags=["Pintura"],       dependencies=[Depends(get_current_user)])

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

def _so_gestor_ou_pagina(pagina=None):
    """Gestor sempre; outros perfis só com a página liberada no Controle de Acesso."""
    def dep(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") == "gestor":
            return current_user
        if pagina:
            conn = get_conn()
            try:
                r = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (f"perm_{current_user.get('role')}",)).fetchone()
                paginas = [p.strip() for p in ((r["valor"] if r else "") or "").split(",")]
            finally:
                conn.close()
            if pagina in paginas:
                return current_user
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Acesso restrito ao Gestor.")
    return dep


@app.get("/api/backup", dependencies=[Depends(_so_gestor_ou_pagina("backup"))])
def fazer_backup():
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"pratic_backup_{now}.db"
    backup_path = os.path.join(tempfile.gettempdir(), backup_name)
    
    # Executa o backup atômico via API oficial do sqlite3
    src = get_conn()
    dst = sqlite3.connect(backup_path)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()
    
    return FileResponse(path=backup_path, filename=backup_name, media_type="application/octet-stream")

# ─── BACKUP COMPLETO: banco + arquivos (PDFs das notas fiscais e anexos do chat) ───
# Os PDFs ficam em pastas ao lado do banco (banco/notas_fiscais, banco/uploads/...),
# por isso o backup só do .db não levava as notas. O completo é um .zip com tudo.
PASTAS_ARQUIVOS = ("notas_fiscais", "uploads", "pedidos_originais", "pedidos_artes")


def _pasta_banco() -> str:
    return os.path.dirname(os.path.abspath(DB_PATH))


def _arquivos_do_backup():
    base = _pasta_banco()
    for pasta in PASTAS_ARQUIVOS:
        raiz = os.path.join(base, pasta)
        if not os.path.isdir(raiz):
            continue
        for dirpath, _dirs, nomes in os.walk(raiz):
            for nome in nomes:
                caminho = os.path.join(dirpath, nome)
                yield caminho, os.path.relpath(caminho, base).replace(os.sep, "/")


@app.get("/api/backup/info", dependencies=[Depends(_so_gestor_ou_pagina("backup"))])
def info_backup():
    qtd_nf, qtd_outros, qtd_orig, tamanho = 0, 0, 0, 0
    for caminho, rel in _arquivos_do_backup():
        try:
            tamanho += os.path.getsize(caminho)
        except OSError:
            continue
        if rel.startswith("notas_fiscais/"):
            qtd_nf += 1
        elif rel.startswith("pedidos_originais/"):
            qtd_orig += 1
        else:
            qtd_outros += 1
    try:
        tam_db = os.path.getsize(DB_PATH)
    except OSError:
        tam_db = 0
    return {"notas_fiscais": qtd_nf, "pedidos_originais": qtd_orig, "outros_arquivos": qtd_outros,
            "tamanho_arquivos": tamanho, "tamanho_banco": tam_db}


@app.get("/api/backup/completo", dependencies=[Depends(_so_gestor_ou_pagina("backup"))])
def fazer_backup_completo():
    from starlette.background import BackgroundTask
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp_db = os.path.join(tempfile.gettempdir(), f"pratic_bk_{now}.db")
    zip_name = f"pratic_backup_completo_{now}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_name)
    src = get_conn()
    dst = sqlite3.connect(tmp_db)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_db, "pratic.db")
            for caminho, rel in _arquivos_do_backup():
                try:
                    # PDF já é comprimido: guarda sem recomprimir (mais rápido)
                    z.write(caminho, rel, compress_type=zipfile.ZIP_STORED if rel.lower().endswith(".pdf") else zipfile.ZIP_DEFLATED)
                except OSError:
                    pass
            z.writestr("LEIA-ME.txt", "Backup completo do PRATIC\n"
                       "- pratic.db: banco de dados\n- notas_fiscais/: PDFs das notas fiscais\n- pedidos_originais/: PDFs dos pedidos importados\n- uploads/: anexos\n"
                       "Para restaurar: Backup > Restaurar Backup, escolhendo este arquivo .zip.\n")
    finally:
        if os.path.exists(tmp_db):
            os.remove(tmp_db)
    return FileResponse(path=zip_path, filename=zip_name, media_type="application/zip",
                        background=BackgroundTask(lambda: os.path.exists(zip_path) and os.remove(zip_path)))


@app.post("/api/restore", dependencies=[Depends(_so_gestor_ou_pagina())])
async def restaurar_backup(file: UploadFile = File(...)):
    db_path = DB_PATH
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Salva o arquivo enviado em disco (sem carregar tudo na memória: o .zip com PDFs pode ser grande)
    nome_env = (file.filename or "").lower()
    temp_up = os.path.join(tempfile.gettempdir(), f"restore_up_{now}")
    with open(temp_up, "wb") as f:
        shutil.copyfileobj(file.file, f, 1024 * 1024)
    temp_db_path = os.path.join(tempfile.gettempdir(), f"restore_{now}.db")
    restaurados = 0
    try:
        if nome_env.endswith(".zip") or zipfile.is_zipfile(temp_up):
            from fastapi import HTTPException
            base = _pasta_banco()
            with zipfile.ZipFile(temp_up) as z:
                nomes = z.namelist()
                db_nome = "pratic.db" if "pratic.db" in nomes else next((n for n in nomes if n.lower().endswith(".db") and "/" not in n), None)
                if not db_nome:
                    raise HTTPException(400, "Este .zip não tem o banco (pratic.db).")
                with z.open(db_nome) as zsrc, open(temp_db_path, "wb") as out:
                    shutil.copyfileobj(zsrc, out, 1024 * 1024)
                # Valida o banco antes de mexer em qualquer coisa
                try:
                    t = sqlite3.connect(temp_db_path); t.execute("SELECT name FROM sqlite_master LIMIT 1"); t.close()
                except sqlite3.DatabaseError:
                    raise HTTPException(400, "O banco dentro do .zip não é válido.")
                # Arquivos (PDFs das notas, anexos): só dentro das pastas conhecidas, sem sair da pasta do banco
                for info in z.infolist():
                    rel = info.filename.replace("\\", "/")
                    if info.is_dir() or not any(rel.startswith(p + "/") for p in PASTAS_ARQUIVOS):
                        continue
                    destino = os.path.normpath(os.path.join(base, rel))
                    if not destino.startswith(os.path.join(base, "")):
                        continue
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    with z.open(info) as zsrc, open(destino, "wb") as out:
                        shutil.copyfileobj(zsrc, out, 1024 * 1024)
                    restaurados += 1
        else:
            shutil.move(temp_up, temp_db_path)
            try:
                t = sqlite3.connect(temp_db_path); t.execute("SELECT name FROM sqlite_master LIMIT 1"); t.close()
            except sqlite3.DatabaseError:
                from fastapi import HTTPException
                raise HTTPException(400, "O arquivo enviado não é um banco .db válido.")
    except Exception:
        for tmp in (temp_up, temp_db_path):
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    finally:
        if os.path.exists(temp_up):
            os.remove(temp_up)

    # Salva uma cópia física de segurança (backup anterior)
    shutil.copy2(db_path, db_path + f".bak_{now}")
        
    # Restaura o banco de dados via API oficial do sqlite3 (mantém os handles do servidor seguros)
    try:
        src = sqlite3.connect(temp_db_path)
        dst = get_conn()
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
            src.close()
    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
            
    # Reaplica as migrações do banco (colunas/tabelas novas) sobre o arquivo
    # recém-restaurado — sem isso, um backup mais antigo que o código atual
    # ficaria sem colunas adicionadas depois, até o próximo restart manual.
    init_db()

    msg = "Banco de dados restaurado com sucesso!"
    if restaurados:
        msg += f" {restaurados} arquivo(s) (PDFs das notas e anexos) restaurados."
    return {"mensagem": msg, "arquivos": restaurados}

@app.post("/api/empresa/logo", dependencies=[Depends(_so_gestor_ou_pagina("empresa"))])
async def upload_logo(file: UploadFile = File(...)):
    contents = await file.read()
    ext = file.filename.split(".")[-1].lower()
    b64 = base64.b64encode(contents).decode()
    data_url = f"data:image/{ext};base64,{b64}"
    conn = get_conn()
    try:
        conn.execute("INSERT OR REPLACE INTO configuracoes (chave, valor, descricao) VALUES ('empresa_logo', ?, 'Logo da empresa em base64')", (data_url,))
        conn.commit()
    finally:
        conn.close()
    return {"mensagem": "Logo salvo", "url": data_url[:50] + "..."}

@app.on_event("startup")
def startup():
    init_db()
    seed_data()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
