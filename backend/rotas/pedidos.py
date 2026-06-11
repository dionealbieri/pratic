from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from database import get_conn
import httpx
import os, re, tempfile, datetime

router = APIRouter()

class ClienteIn(BaseModel):
    cnpj: Optional[str] = None
    razao_social: str
    nome_fantasia: Optional[str] = None
    ie: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    observacoes: Optional[str] = None

class ItemPedidoIn(BaseModel):
    produto_id: Optional[int] = None
    descricao: str
    quantidade: float
    unidade: Optional[str] = "unidade"

class PedidoIn(BaseModel):
    numero_pedido: str
    cliente_id: int
    prazo_entrega: str
    vendedor: Optional[str] = None
    observacoes: Optional[str] = None
    itens: List[ItemPedidoIn] = []

class StatusItemIn(BaseModel):
    status: str
    qtd_produzida: Optional[float] = None
    split_if_partial: Optional[bool] = False


# ─── IMPORTAÇÃO DE PEDIDO POR ARQUIVO ────────────────────────────────────────

def _br_to_float(valor: str) -> float:
    """Converte números no padrão brasileiro: 3000,000 -> 3000.0; 1.234,56 -> 1234.56."""
    if valor is None:
        return 0.0
    v = str(valor).strip().replace("R$", "").replace(" ", "")
    if not v:
        return 0.0
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except Exception:
        return 0.0

def _date_br_to_iso(valor: str) -> Optional[str]:
    if not valor:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", valor)
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

def _clean_line(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "").strip())

def _extract_text_from_file(path: str, filename: str) -> str:
    ext = os.path.splitext(filename or path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception:
            raise HTTPException(500, "Para importar PDF, instale a dependência pypdf: pip install pypdf")
        try:
            reader = PdfReader(path)
            pages = [(page.extract_text() or "") for page in reader.pages]
            text = "\n".join(pages).strip()
            if text:
                return text
            raise HTTPException(400, "O PDF parece ser escaneado/imagem. Envie JPG/PNG ou instale OCR/Tesseract para leitura de imagem.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Não foi possível ler o PDF: {e}")
    if ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"]:
        try:
            from PIL import Image
            import pytesseract
        except Exception:
            raise HTTPException(500, "Para importar imagens, instale pillow e pytesseract. Também é necessário instalar o Tesseract OCR no Windows.")
        try:
            img = Image.open(path)
            try:
                return pytesseract.image_to_string(img, lang="por+eng")
            except Exception:
                return pytesseract.image_to_string(img)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Não foi possível ler a imagem: {e}")
    if ext in [".txt", ".csv"]:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise HTTPException(400, "Formato não suportado. Use PDF, JPG, PNG, WEBP, BMP, TIFF, TXT ou CSV.")

def _parse_pedido_text(texto: str) -> dict:
    text = texto or ""
    norm = re.sub(r"[ \t]+", " ", text)
    lines = [_clean_line(l) for l in text.splitlines() if _clean_line(l)]

    numero = None
    m = re.search(r"C[oó]digo\s+do\s+Pedido\s*[:\-]?\s*(\d+)", norm, re.I)
    if not m:
        m = re.search(r"\bPedido\s*[:#\-]?\s*(\d{3,})", norm, re.I)
    if m:
        numero = m.group(1)

    data_iso = None
    for pat in [r"Data\s+de\s+Vencimento\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", r"Data\s+de\s+Lan[çc]amento\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})"]:
        m = re.search(pat, norm, re.I)
        if m:
            data_iso = _date_br_to_iso(m.group(1))
            break
    if not data_iso:
        data_iso = datetime.date.today().isoformat()

    cliente_nome = None
    for line in lines:
        m = re.search(r"Cliente\s*:\s*(.+)", line, re.I)
        if m:
            cliente_nome = re.split(r"\s{2,}| Documento\s*:| Telefone\s*:| Celular\s*:", m.group(1), flags=re.I)[0].strip(" -")
            break

    documento = None
    m = re.search(r"Documento\s*:\s*([\d\.\-/]+)", norm, re.I)
    if m:
        documento = m.group(1).strip()

    telefone = None
    m = re.search(r"Celular\s*:\s*([+\d\s()\-.]+)", norm, re.I)
    if not m:
        m = re.search(r"Telefone\s*:\s*([+\d\s()\-.]+)", norm, re.I)
    if m:
        telefone = m.group(1).strip()

    vendedor = None
    pat_vendedor = r"\b(?:Vendedor(?:\s*Respons[aá]vel)?|Representante|Vend\b\.?|Contato\s+Venda|Emitido\s+por|Emissor|Consultor|Atendente)\s*[:\-]?\s*([^\n]+)"
    m = re.search(pat_vendedor, text, re.I)
    if m:
        bruto = m.group(1)
        limpo = re.split(r"\s{2,}|Pessoa\s+para\s+Contato\s*:|Documento\s*:|Telefone\s*:|Celular\s*:", bruto, flags=re.I)[0]
        vendedor = _clean_line(limpo)

    endereco = cidade = bairro = uf = None
    for line in lines:
        m_end = re.search(r"Endere[cç]o\s*:\s*(.*?)(?:\s+Bairro\s*:|$)", line, re.I)
        if m_end: endereco = m_end.group(1).strip()
        m_bairro = re.search(r"Bairro\s*:\s*(.*?)(?:\s+Cidade\s*:|\s+Estado\s*:|$)", line, re.I)
        if m_bairro: bairro = m_bairro.group(1).strip()
        m_cidade = re.search(r"Cidade\s*:\s*(.*?)(?:\s+Estado\s*:|$)", line, re.I)
        if m_cidade: cidade = m_cidade.group(1).strip()
        m_uf = re.search(r"Estado\s*:\s*([A-Z]{2}|[A-Za-zÀ-ÿ ]+)", line, re.I)
        if m_uf: uf = m_uf.group(1).strip()

    obs = None
    m = re.search(r"Observa[çc][aã]o\s*:\s*(.*?)(?:Sub\s*Total|Acr[eé]scimo|Frete|Valor\s+Total|Quantidade\s+Itens|$)", text, re.I|re.S)
    if m:
        obs = _clean_line(m.group(1))[:1000]

    itens = []
    unidade_pat = r"(?:und|unid|un|kg|g|litro|lt|l|metro|mt|m|caixa|cx|pacote|pct|pc|pç)"
    stop_words = re.compile(r"^(Parcela|Forma de Pagamento|SubTotal|Acr[eé]scimo|Frete|Desconto|Valor Total|Quantidade Itens|Peso dos Produtos|Observa[çc][aã]o)", re.I)
    for line in lines:
        if stop_words.search(line):
            continue
        # Padrão mais comum do pedido: código + descrição + unidade + quantidade + valores
        m = re.match(rf"^\s*\d+\s+(.+?)\s+({unidade_pat})\s+([\d\.]+,\d{{3}}|\d+,\d{{3}}|\d+[\.,]?\d*)\b", line, re.I)
        if m:
            desc = _clean_line(m.group(1))
            unidade = m.group(2).lower()
            qtd = _br_to_float(m.group(3))
            # Evita capturar linhas que não sejam produto
            if desc and qtd > 0 and len(desc) >= 3 and not re.search(r"Valor Unit[aá]rio|Produto Descri", desc, re.I):
                itens.append({"descricao": desc[:250], "quantidade": qtd, "unidade": unidade})

    # Remove duplicidades exatas causadas por OCR
    unicos = []
    vistos = set()
    for item in itens:
        key = (item["descricao"].upper(), item["quantidade"], item["unidade"])
        if key not in vistos:
            vistos.add(key)
            unicos.append(item)

    faltando = []
    if not numero: faltando.append("código do pedido")
    if not cliente_nome: faltando.append("cliente")
    if not unicos: faltando.append("itens/quantidades")
    return {
        "numero_pedido": numero,
        "prazo_entrega": data_iso,
        "cliente": {
            "razao_social": cliente_nome or "Cliente importado sem nome",
            "nome_fantasia": None,
            "cnpj": documento,
            "telefone": telefone,
            "logradouro": endereco,
            "bairro": bairro,
            "cidade": cidade,
            "uf": uf,
        },
        "vendedor": vendedor,
        "observacoes": obs,
        "itens": unicos,
        "faltando": faltando,
    }


import re as _re

def _auto_vincular_itens(conn):
    """Tenta vincular automaticamente itens de pedido ao estoque por similaridade de nome."""
    itens = conn.execute("""
        SELECT pi.id, pi.descricao FROM pedidos_itens pi WHERE pi.produto_id IS NULL
    """).fetchall()
    if not itens:
        return

    produtos = conn.execute("SELECT id, nome, marca FROM estoque_produtos WHERE ativo=1").fetchall()

    def extrair_numero(s):
        nums = _re.findall(r'\d+', s)
        return set(nums)

    def normalizar(s):
        return _re.sub(r'[^A-Z0-9]', ' ', s.upper()).split()

    for item in itens:
        desc_palavras = normalizar(item['descricao'])
        desc_nums = extrair_numero(item['descricao'])
        melhor_id = None
        melhor_score = 0

        for p in produtos:
            prod_str = (p['nome'] or '') + ' ' + (p['marca'] or '')
            prod_palavras = normalizar(prod_str)
            prod_nums = extrair_numero(prod_str)

            # Score de palavras comuns
            inter = set(desc_palavras) & set(prod_palavras)
            score = len(inter) / max(len(set(desc_palavras)), 1)

            # Bonus se os números coincidem (tamanhos)
            if desc_nums and prod_nums and desc_nums & prod_nums:
                score += 0.4
            elif desc_nums and prod_nums and not (desc_nums & prod_nums):
                score -= 0.3  # Penalizar se números diferentes (tamanhos diferentes)

            if score > melhor_score and score >= 0.6:
                melhor_score = score
                melhor_id = p['id']

        if melhor_id:
            conn.execute("UPDATE pedidos_itens SET produto_id = ? WHERE id = ?", (melhor_id, item['id']))

@router.post("/importar-arquivo")
async def importar_pedido_arquivo(file: UploadFile = File(...)):
    return await _processar_arquivo_pedido(file)

async def _processar_arquivo_pedido(file: UploadFile):
    """Lógica de importação reutilizável — analisa o arquivo e retorna os dados para revisão."""
    if not file.filename:
        raise HTTPException(400, "Selecione um arquivo")
    suffix = os.path.splitext(file.filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        try:
            texto = _extract_text_from_file(tmp_path, file.filename)
            parsed = _parse_pedido_text(texto)
        except Exception as e:
            print(f"[IMPORT_ERROR] Ocorreu um erro no processamento do arquivo: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(400, f"Não foi possível ler o arquivo: {str(e)}")

        doc = parsed["cliente"].get("cnpj")
        doc_limpo = ''.join(filter(str.isdigit, doc)) if doc else ''
        cliente = None
        
        conn = get_conn()
        cur = conn.cursor()
        
        if doc_limpo:
            cliente = cur.execute("SELECT id FROM pedidos_clientes WHERE cnpj=? AND ativo=1", (doc_limpo,)).fetchone()
        if not cliente and parsed["cliente"].get("razao_social"):
            cliente = cur.execute("SELECT id FROM pedidos_clientes WHERE UPPER(razao_social)=UPPER(?) AND ativo=1", (parsed["cliente"]["razao_social"],)).fetchone()

        if cliente:
            cliente_id = cliente["id"]
        else:
            c = parsed["cliente"]
            # Se for CNPJ (14 dígitos), busca automaticamente via ReceitaWS
            if doc_limpo and len(doc_limpo) == 14:
                cnpj_dados = await _buscar_cnpj_dados(doc_limpo)
                if cnpj_dados:
                    c = cnpj_dados
            
            cur.execute("""INSERT INTO pedidos_clientes
                (cnpj, razao_social, nome_fantasia, email, telefone, cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc_limpo or c.get("cnpj"), c.get("razao_social") or "Cliente importado sem nome", c.get("nome_fantasia"), c.get("email"), c.get("telefone"), c.get("cep"), c.get("logradouro"), c.get("numero"), c.get("complemento"), c.get("bairro"), c.get("cidade"), c.get("uf"), "Cadastrado automaticamente pela importação de pedido"))
            cliente_id = cur.lastrowid
            conn.commit()
            
        conn.close()
        
        return {
            "cliente_id": cliente_id,
            "dados_extraidos": parsed
        }
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

async def _buscar_cnpj_dados(cnpj: str) -> Optional[dict]:
    cnpj_limpo = ''.join(filter(str.isdigit, cnpj))
    if len(cnpj_limpo) != 14:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_limpo}")
            data = r.json()
            if data.get("status") == "ERROR":
                return None
            return {
                "cnpj": cnpj_limpo,
                "razao_social": data.get("nome", ""),
                "nome_fantasia": data.get("fantasia", ""),
                "email": data.get("email", ""),
                "telefone": data.get("telefone", ""),
                "cep": data.get("cep", "").replace(".", "").replace("-", "").replace(" ", ""),
                "logradouro": data.get("logradouro", ""),
                "numero": data.get("numero", ""),
                "complemento": data.get("complemento", ""),
                "bairro": data.get("bairro", ""),
                "cidade": data.get("municipio", ""),
                "uf": data.get("uf", ""),
            }
    except Exception:
        return None

@router.get("/busca-cnpj/{cnpj}")
async def buscar_cnpj(cnpj: str):
    dados = await _buscar_cnpj_dados(cnpj)
    if not dados:
        raise HTTPException(404, "CNPJ não encontrado ou inválido")
    return dados

@router.get("/busca-cep/{cep}")
async def buscar_cep(cep: str):
    cep_limpo = ''.join(filter(str.isdigit, cep))
    if len(cep_limpo) != 8:
        raise HTTPException(400, "CEP inválido")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://viacep.com.br/ws/{cep_limpo}/json/")
            data = r.json()
            if data.get("erro"):
                raise HTTPException(404, "CEP não encontrado")
            return {
                "cep": cep_limpo,
                "logradouro": data.get("logradouro", ""),
                "bairro": data.get("bairro", ""),
                "cidade": data.get("localidade", ""),
                "uf": data.get("uf", ""),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar CEP: {str(e)}")

# ─── CLIENTES ─────────────────────────────────────────────────────────────────

@router.get("/clientes")
def listar_clientes(busca: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT c.*,
               COUNT(p.id) as total_pedidos,
               MAX(p.created_at) as ultimo_pedido
        FROM pedidos_clientes c
        LEFT JOIN pedidos p ON p.cliente_id = c.id
        WHERE c.ativo = 1
    """
    params = []
    if busca:
        query += " AND (c.razao_social LIKE ? OR c.nome_fantasia LIKE ? OR c.cnpj LIKE ?)"
        params += [f"%{busca}%", f"%{busca}%", f"%{busca}%"]
    query += " GROUP BY c.id ORDER BY c.razao_social"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/clientes/{id}")
def buscar_cliente(id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM pedidos_clientes WHERE id=?", (id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Cliente não encontrado")
    return dict(row)

@router.post("/clientes")
def criar_cliente(c: ClienteIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO pedidos_clientes
        (cnpj, razao_social, nome_fantasia, ie, email, telefone,
         cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (c.cnpj, c.razao_social, c.nome_fantasia, c.ie, c.email, c.telefone,
         c.cep, c.logradouro, c.numero, c.complemento, c.bairro, c.cidade, c.uf, c.observacoes))
    conn.commit()
    id = cur.lastrowid
    conn.close()
    return {"id": id, "mensagem": "Cliente cadastrado"}

@router.put("/clientes/{id}")
def atualizar_cliente(id: int, c: ClienteIn):
    conn = get_conn()
    conn.execute("""UPDATE pedidos_clientes SET
        cnpj=?, razao_social=?, nome_fantasia=?, ie=?, email=?, telefone=?,
        cep=?, logradouro=?, numero=?, complemento=?, bairro=?, cidade=?, uf=?, observacoes=?
        WHERE id=?""",
        (c.cnpj, c.razao_social, c.nome_fantasia, c.ie, c.email, c.telefone,
         c.cep, c.logradouro, c.numero, c.complemento, c.bairro, c.cidade, c.uf, c.observacoes, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Cliente atualizado"}

@router.delete("/clientes/{id}")
def deletar_cliente(id: int):
    conn = get_conn()
    conn.execute("UPDATE pedidos_clientes SET ativo=0 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Cliente desativado"}

# ─── PEDIDOS ──────────────────────────────────────────────────────────────────

@router.get("/")
def listar_pedidos(status: Optional[str] = None, cliente_id: Optional[int] = None):
    conn = get_conn()
    query = """
        SELECT p.*,
               c.razao_social as cliente_nome,
               c.nome_fantasia,
               COUNT(i.id) as total_itens,
               COUNT(CASE WHEN i.status = 'entregue' THEN 1 END) as itens_entregues,
               julianday(p.prazo_entrega) - julianday('now') as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        LEFT JOIN pedidos_itens i ON i.pedido_id = p.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND p.status = ?"
        params.append(status)
    if cliente_id:
        query += " AND p.cliente_id = ?"
        params.append(cliente_id)
    query += " GROUP BY p.id ORDER BY p.prazo_entrega ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/alertas/resumo")
def alertas_pedidos():
    conn = get_conn()
    vencidos = conn.execute("""
        SELECT COUNT(*) FROM pedidos
        WHERE status NOT IN ('entregue')
        AND julianday(prazo_entrega) < julianday('now')
    """).fetchone()[0]
    urgentes = conn.execute("""
        SELECT COUNT(*) FROM pedidos
        WHERE status NOT IN ('entregue')
        AND julianday(prazo_entrega) - julianday('now') BETWEEN 0 AND 3
    """).fetchone()[0]
    em_aberto = conn.execute("""
        SELECT COUNT(*) FROM pedidos WHERE status = 'aberto'
    """).fetchone()[0]
    rows = conn.execute("""
        SELECT p.numero_pedido, c.razao_social as cliente,
               p.prazo_entrega, p.status,
               CAST(julianday(p.prazo_entrega) - julianday('now') AS INTEGER) as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.status NOT IN ('entregue')
        AND julianday(p.prazo_entrega) - julianday('now') <= 3
        ORDER BY p.prazo_entrega ASC
        LIMIT 5
    """).fetchall()
    conn.close()
    return {
        "vencidos": vencidos,
        "urgentes": urgentes,
        "em_aberto": em_aberto,
        "lista_urgentes": [dict(r) for r in rows]
    }

# ─── FILA PRODUÇÃO ───────────────────────────────────────────────────────────

@router.get("/fila/producao")
def fila_producao(status: Optional[str] = None):
    conn = get_conn()
    query = """
        SELECT i.*,
               p.numero_pedido, p.prazo_entrega, p.vendedor,
               c.razao_social as cliente_nome,
               CAST(julianday(p.prazo_entrega) - julianday('now') AS INTEGER) as dias_restantes,
               ep.nome as produto_nome_estoque
        FROM pedidos_itens i
        JOIN pedidos p ON i.pedido_id = p.id
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
        WHERE p.status NOT IN ('entregue')
    """
    params = []
    if status:
        query += " AND i.status = ?"
        params.append(status)
    query += " ORDER BY p.prazo_entrega ASC, i.id ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{id}")
def buscar_pedido(id: int):
    conn = get_conn()
    pedido = conn.execute("""
        SELECT p.*, c.razao_social as cliente_nome, c.nome_fantasia,
               julianday(p.prazo_entrega) - julianday('now') as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.id=?
    """, (id,)).fetchone()
    if not pedido:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    itens = conn.execute("""
        SELECT i.*, ep.nome as produto_nome
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
        WHERE i.pedido_id=?
        ORDER BY i.id
    """, (id,)).fetchall()
    conn.close()
    result = dict(pedido)
    result["itens"] = [dict(i) for i in itens]
    return result

@router.post("/")
def criar_pedido(p: PedidoIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO pedidos
        (numero_pedido, cliente_id, prazo_entrega, vendedor, observacoes, status)
        VALUES (?,?,?,?,?,'aberto')""",
        (p.numero_pedido, p.cliente_id, p.prazo_entrega, p.vendedor, p.observacoes))
    pedido_id = cur.lastrowid
    for item in p.itens:
        cur.execute("""INSERT INTO pedidos_itens
            (pedido_id, produto_id, descricao, quantidade, unidade, qtd_produzida, status)
            VALUES (?,?,?,?,?,0,'aberto')""",
            (pedido_id, item.produto_id, item.descricao, item.quantidade, item.unidade))
    conn.commit()
    conn.close()
    return {"id": pedido_id, "mensagem": "Pedido criado"}

@router.put("/{id}")
def atualizar_pedido(id: int, p: PedidoIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""UPDATE pedidos SET
        numero_pedido=?, cliente_id=?, prazo_entrega=?, vendedor=?, observacoes=?
        WHERE id=?""",
        (p.numero_pedido, p.cliente_id, p.prazo_entrega, p.vendedor, p.observacoes, id))
    
    # Mapear status e quantidade produzida dos itens atuais pela descrição (para preservar o progresso)
    progresso_itens = {}
    for row in cur.execute("SELECT descricao, status, qtd_produzida FROM pedidos_itens WHERE pedido_id=?", (id,)).fetchall():
        progresso_itens[row["descricao"].upper()] = (row["status"], row["qtd_produzida"])
        
    cur.execute("DELETE FROM pedidos_itens WHERE pedido_id=?", (id,))
    for item in p.itens:
        status = "aberto"
        qtd_produzida = 0.0
        key = item.descricao.upper()
        if key in progresso_itens:
            status, qtd_produzida = progresso_itens[key]
        cur.execute("""INSERT INTO pedidos_itens
            (pedido_id, produto_id, descricao, quantidade, unidade, qtd_produzida, status)
            VALUES (?,?,?,?,?,?,?)""",
            (id, item.produto_id, item.descricao, item.quantidade, item.unidade, qtd_produzida, status))
            
    conn.commit()
    conn.close()
    return {"mensagem": "Pedido atualizado"}

@router.put("/{id}/status")
def atualizar_status_pedido(id: int, body: StatusItemIn):
    validos = ["aberto", "em_producao", "produzido", "entregue"]
    if body.status not in validos:
        raise HTTPException(400, f"Status inválido. Use: {validos}")
    conn = get_conn()
    conn.execute("UPDATE pedidos SET status=? WHERE id=?", (body.status, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Status atualizado"}

@router.delete("/{id}")
def deletar_pedido(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM pedidos_itens WHERE pedido_id=?", (id,))
    conn.execute("DELETE FROM pedidos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Pedido removido"}

# ─── ITENS ────────────────────────────────────────────────────────────────────

@router.put("/itens/{id}/status")
def atualizar_status_item(id: int, body: StatusItemIn):
    validos = ["aberto", "em_producao", "produzido", "entregue"]
    if body.status not in validos:
        raise HTTPException(400, f"Status inválido. Use: {validos}")
    conn = get_conn()
    cur = conn.cursor()
    
    item = cur.execute("SELECT * FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item do pedido não encontrado")
        
    pid = item["pedido_id"]
    
    if body.split_if_partial and body.qtd_produzida is not None:
        nova_qtd = body.qtd_produzida
        limite = item["quantidade"]
        if 0 < nova_qtd < limite:
            # Caso de split parcial!
            cur.execute("""
                UPDATE pedidos_itens 
                SET quantidade=?, qtd_produzida=?, status=? 
                WHERE id=?
            """, (nova_qtd, nova_qtd, 'produzido', id))
            
            resto = limite - nova_qtd
            cur.execute("""
                INSERT INTO pedidos_itens (pedido_id, produto_id, descricao, quantidade, unidade, qtd_produzida, status)
                VALUES (?, ?, ?, ?, ?, 0, 'aberto')
            """, (pid, item["produto_id"], item["descricao"], resto, item["unidade"]))
        else:
            cur.execute("UPDATE pedidos_itens SET status=?, qtd_produzida=? WHERE id=?",
                        (body.status, body.qtd_produzida, id))
    else:
        if body.qtd_produzida is not None:
            cur.execute("UPDATE pedidos_itens SET status=?, qtd_produzida=? WHERE id=?",
                        (body.status, body.qtd_produzida, id))
        else:
            cur.execute("UPDATE pedidos_itens SET status=? WHERE id=?", (body.status, id))

    # Recalcular status do pedido pai
    item = cur.execute("SELECT pedido_id FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if item:
        pid = item["pedido_id"]
        counts = cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status='entregue' THEN 1 END) as entregues,
                COUNT(CASE WHEN status='produzido' THEN 1 END) as produzidos,
                COUNT(CASE WHEN status='em_producao' THEN 1 END) as em_prod
            FROM pedidos_itens WHERE pedido_id=?
        """, (pid,)).fetchone()
        if counts["total"] == counts["entregues"]:
            novo_status = "entregue"
        elif counts["produzidos"] + counts["entregues"] == counts["total"]:
            novo_status = "produzido"
        elif counts["em_prod"] > 0:
            novo_status = "em_producao"
        else:
            novo_status = "aberto"
        cur.execute("UPDATE pedidos SET status=? WHERE id=?", (novo_status, pid))

    conn.commit()
    conn.close()
    return {"mensagem": "Item atualizado"}

@router.put("/itens/{id}/produto")
def vincular_produto_item(id: int, body: dict):
    conn = get_conn()
    produto_id = body.get('produto_id')
    conn.execute("UPDATE pedidos_itens SET produto_id = ? WHERE id = ?", (produto_id, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Produto vinculado", "produto_id": produto_id}

@router.delete("/itens/{id}")
def deletar_item(id: int):
    conn = get_conn()
    conn.execute("DELETE FROM pedidos_itens WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"mensagem": "Item removido"}

# ─── ALERTAS ─────────────────────────────────────────────────────────────────


