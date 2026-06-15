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
                try:
                    return pytesseract.image_to_string(img, lang="por+eng")
                except Exception:
                    return pytesseract.image_to_string(img)
            except Exception as ocr_err:
                err_msg = str(ocr_err)
                if "tesseract is not installed" in err_msg.lower() or "not found" in err_msg.lower() or "no such file" in err_msg.lower():
                    raise HTTPException(400, "O Tesseract OCR não está instalado no servidor de produção (online). Para corrigir, execute no terminal do servidor: 'sudo apt-get update && sudo apt-get install -y tesseract-ocr' (Linux/Ubuntu) ou instale o Tesseract OCR e configure o PATH (Windows).")
                raise HTTPException(400, f"Erro no processamento OCR da imagem: {ocr_err}")
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


# ─── IMPORTAÇÃO ESPECÍFICA: PEDIDO DO SAC COMMERCE / SOFTLINE ─────────────────
# Esse PDF coloca cada rótulo e cada valor em linhas separadas; por isso usa um
# leitor próprio. A detecção é automática (mesmo botão de importar do sistema).

_UNIDADES_SAC = {"und", "unid", "un", "kg", "g", "litro", "lt", "l", "metro", "mt",
                 "m", "caixa", "cx", "pacote", "pct", "pc", "pç", "pçs", "milheiro",
                 "mil", "cento", "ct", "rolo", "fardo", "fd"}

def _is_pedido_sac(texto: str) -> bool:
    t = (texto or "")
    if "softlinesistemas" in t.lower():
        return True
    tem_cod = bool(re.search(r"C[oó]digo do\s*\n?\s*Pedido", t, re.I))
    tem_lanc = bool(re.search(r"Data de Lan[çc]amento", t, re.I))
    return tem_cod and tem_lanc

def _sac_is_int(s): return bool(re.fullmatch(r"\d+", s.strip()))
def _sac_is_unidade(s): return s.strip().lower() in _UNIDADES_SAC
def _sac_is_numero(s): return bool(re.fullmatch(r"[\d.]*\d+(?:,\d+)?", s.strip()))
def _sac_is_money(s):
    s = s.strip()
    return s.startswith("R$") or bool(re.fullmatch(r"R?\$?\s*[\d.]*\d+,\d{2}", s))

def _sac_valor_apos(linhas, label, ate=None):
    """Retorna o primeiro valor não vazio APÓS uma linha-rótulo (rótulo e valor em linhas separadas)."""
    pat = re.compile(label, re.I)
    limite = len(linhas) if ate is None else ate
    for i in range(limite):
        if pat.search(linhas[i]):
            resto = re.sub(rf".*?{label}\s*:?\s*", "", linhas[i], flags=re.I).strip()
            if resto and not resto.endswith(":"):
                return resto
            for j in range(i + 1, min(i + 4, limite)):
                cand = linhas[j].strip()
                if cand and not cand.endswith(":") and not re.fullmatch(r"[A-Za-zÀ-ÿ ]+:", cand):
                    return cand
    return None

# Prazo de entrega padrão para pedidos importados do SAC: data do pedido + N dias
PRAZO_ENTREGA_PADRAO_DIAS = 15

def _parse_pedido_sac(texto: str) -> dict:
    linhas = [l.strip() for l in (texto or "").splitlines()]
    linhas = [l for l in linhas if l != ""]
    full = "\n".join(linhas)

    idx_obs = next((i for i, l in enumerate(linhas) if re.match(r"Observa[çc][ãa]o\s*:", l, re.I)), len(linhas))

    numero = None
    m = re.search(r"C[oó]digo do\s+Pedido\s*:?\s*(\d+)", full, re.I)
    if not m:
        m = re.search(r"Pedido\s*\n?\s*:?\s*\n?\s*(\d{3,})", full, re.I)
    if m:
        numero = m.group(1)

    _lanc_iso = _date_br_to_iso(_sac_valor_apos(linhas, r"Data de Lan[çc]amento") or "")
    _base = datetime.date.fromisoformat(_lanc_iso) if _lanc_iso else datetime.date.today()
    data_iso = (_base + datetime.timedelta(days=PRAZO_ENTREGA_PADRAO_DIAS)).isoformat()

    cliente = _sac_valor_apos(linhas, r"Cliente", ate=idx_obs)

    documento = None
    d = _sac_valor_apos(linhas, r"Documento", ate=idx_obs)
    if d:
        md = re.search(r"[\d.\-/]{11,}", d)
        if md:
            documento = md.group(0)

    telefone = _sac_valor_apos(linhas, r"Celular", ate=idx_obs) or _sac_valor_apos(linhas, r"Telefone", ate=idx_obs)
    if telefone and telefone.lower().startswith("celular"):
        telefone = None

    endereco = _sac_valor_apos(linhas, r"Endere[çc]o", ate=idx_obs)
    bairro = _sac_valor_apos(linhas, r"Bairro", ate=idx_obs)
    cidade = _sac_valor_apos(linhas, r"Cidade", ate=idx_obs)
    uf = _sac_valor_apos(linhas, r"Estado", ate=idx_obs)
    if uf:
        mu = re.search(r"\b([A-Z]{2})\b", uf)
        uf = mu.group(1) if mu else uf

    email = None
    me = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", full)
    if me:
        email = me.group(0)
    cep = None
    mc = re.search(r"\b(\d{5})-?(\d{3})\b", full)
    if mc:
        cep = mc.group(1) + mc.group(2)

    vendedor = _sac_valor_apos(linhas, r"Vendedor")
    if vendedor and vendedor.lower().startswith("pessoa"):
        vendedor = None

    obs = None
    if idx_obs < len(linhas):
        partes = []
        primeira = re.sub(r".*?Observa[çc][ãa]o\s*:?\s*", "", linhas[idx_obs], flags=re.I).strip()
        if primeira:
            partes.append(primeira)
        for j in range(idx_obs + 1, min(idx_obs + 4, len(linhas))):
            if re.match(r"(Pessoa para Contato|Vendedor|SubTotal|Produto|Quantidade Itens)", linhas[j], re.I):
                break
            partes.append(linhas[j])
        obs = " ".join(partes).strip()[:1000] or None

    # ── ITENS (tabela com cada célula em uma linha) ──
    itens = []
    inicio = None
    for i, l in enumerate(linhas):
        if l.strip().lower() == "produto":
            janela = " ".join(linhas[i:i + 8]).lower()
            if "descri" in janela and "quantidade" in janela:
                for k in range(i + 1, min(i + 9, len(linhas))):
                    if linhas[k].strip().lower() == "valor total":
                        inicio = k + 1
                        break
                if inicio is None:
                    inicio = i + 7
                break
    fim = next((i for i, l in enumerate(linhas) if l.strip().lower() == "parcelas"), len(linhas))
    if inicio is not None:
        regiao = linhas[inicio:fim]
        i = 0
        while i < len(regiao):
            if _sac_is_int(regiao[i]):
                desc_parts = []
                j = i + 1
                while j < len(regiao) and not _sac_is_unidade(regiao[j]):
                    if _sac_is_int(regiao[j]) or _sac_is_money(regiao[j]):
                        break
                    desc_parts.append(regiao[j])
                    j += 1
                if j < len(regiao) and _sac_is_unidade(regiao[j]):
                    unidade = regiao[j].lower()
                    qtd_raw = regiao[j + 1] if j + 1 < len(regiao) else ""
                    if _sac_is_numero(qtd_raw):
                        desc = " ".join(desc_parts).strip()
                        if desc:
                            itens.append({"descricao": desc[:250], "quantidade": _br_to_float(qtd_raw), "unidade": unidade})
                        i = j + 2
                        while i < len(regiao) and _sac_is_money(regiao[i]):
                            i += 1
                        continue
            i += 1

    faltando = []
    if not numero:
        faltando.append("código do pedido")
    if not cliente:
        faltando.append("cliente")
    if not itens:
        faltando.append("itens/quantidades")
    return {
        "numero_pedido": numero,
        "prazo_entrega": data_iso,
        "cliente": {
            "razao_social": cliente or "Cliente importado sem nome",
            "nome_fantasia": None,
            "cnpj": documento,
            "email": email,
            "telefone": telefone,
            "cep": cep,
            "logradouro": endereco,
            "numero": None,
            "complemento": None,
            "bairro": bairro,
            "cidade": cidade,
            "uf": uf,
        },
        "vendedor": vendedor,
        "observacoes": obs,
        "itens": itens,
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

_SUFIXOS_JURIDICOS = {"LTDA", "LTDA.", "EIRELI", "EPP", "ME", "MEI", "SA", "S/A",
                      "S.A", "S.A.", "CIA", "CIA.", "EI", "INC", "EIRL"}

def _abreviar_razao(razao: str) -> str:
    """Gera um nome curto a partir da razão social (sem sufixos jurídicos)."""
    if not razao:
        return ""
    tokens = re.split(r"\s+", razao.strip())
    out = []
    for t in tokens:
        tu = t.upper().strip(".,-/")
        if tu in _SUFIXOS_JURIDICOS:
            continue
        if t.strip() in ("-", "&", "/") and not out:
            continue
        out.append(t)
    s = " ".join(out).strip(" -,/&")
    if not s:
        s = razao.strip()
    return s[:60].rstrip()

async def _preparar_cliente_para_cadastro(c: dict) -> dict:
    """Para um cliente NOVO: busca os dados oficiais na Receita pelo CNPJ
    (como o botão 'buscar') e preenche o nome fantasia com a razão social
    abreviada quando a Receita/arquivo não trouxer fantasia."""
    final = dict(c or {})
    doc_limpo = ''.join(filter(str.isdigit, final.get("cnpj") or ""))
    if len(doc_limpo) == 14:
        receita = await _buscar_cnpj_dados(doc_limpo)
        if receita:
            # E-mail e telefone NÃO são sobrescritos: na Receita costumam ser do
            # escritório de contabilidade. Mantém-se sempre o que veio do pedido.
            for campo in ("razao_social", "nome_fantasia", "cep",
                          "logradouro", "numero", "complemento", "bairro", "cidade", "uf"):
                if receita.get(campo):
                    final[campo] = receita.get(campo)
    if not (final.get("razao_social") or "").strip():
        final["razao_social"] = "Cliente importado sem nome"
    if not (final.get("nome_fantasia") or "").strip():
        final["nome_fantasia"] = _abreviar_razao(final.get("razao_social") or "")
    final["cnpj"] = doc_limpo or final.get("cnpj")
    return final


async def _resolver_cliente_id(parsed: dict, cur) -> int:
    """Encontra (por CNPJ/razão social) ou cria o cliente do pedido. Reutilizado na importação em lote."""
    doc = parsed["cliente"].get("cnpj")
    doc_limpo = ''.join(filter(str.isdigit, doc)) if doc else ''
    cliente = None
    if doc_limpo:
        cliente = cur.execute("SELECT id FROM pedidos_clientes WHERE cnpj=? AND ativo=1", (doc_limpo,)).fetchone()
    if not cliente and parsed["cliente"].get("razao_social"):
        cliente = cur.execute(
            "SELECT id FROM pedidos_clientes WHERE UPPER(razao_social)=UPPER(?) AND ativo=1",
            (parsed["cliente"]["razao_social"],)).fetchone()
    if cliente:
        return cliente["id"]
    c = await _preparar_cliente_para_cadastro(parsed["cliente"])
    cur.execute("""INSERT INTO pedidos_clientes
        (cnpj, razao_social, nome_fantasia, email, telefone, cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (c.get("cnpj"), c.get("razao_social"), c.get("nome_fantasia"),
         c.get("email"), c.get("telefone"), c.get("cep"), c.get("logradouro"), c.get("numero"), c.get("complemento"),
         c.get("bairro"), c.get("cidade"), c.get("uf"), "Cadastrado automaticamente pela importação de pedido"))
    return cur.lastrowid


@router.post("/importar-arquivos-lote")
async def importar_pedidos_lote(files: List[UploadFile] = File(...)):
    """Importa vários PDFs de pedido de uma vez: cria cliente+pedido+itens, pula duplicados (por número) e devolve um resumo."""
    if not files:
        raise HTTPException(400, "Selecione ao menos um arquivo")
    resultados = []
    criados = duplicados = erros = 0
    conn = get_conn()
    try:
        cur = conn.cursor()
        for file in files:
            nome = file.filename or "arquivo"
            tmp_path = None
            try:
                suffix = os.path.splitext(nome)[1].lower()
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(await file.read())
                    tmp_path = tmp.name
                texto = _extract_text_from_file(tmp_path, nome)
                parsed = _parse_pedido_sac(texto) if _is_pedido_sac(texto) else _parse_pedido_text(texto)

                numero = parsed.get("numero_pedido")
                if not numero:
                    erros += 1
                    resultados.append({"arquivo": nome, "status": "erro",
                                       "motivo": "Número do pedido não encontrado",
                                       "faltando": parsed.get("faltando", [])})
                    continue

                existe = cur.execute("SELECT id FROM pedidos WHERE numero_pedido=?", (str(numero),)).fetchone()
                if existe:
                    duplicados += 1
                    resultados.append({"arquivo": nome, "numero_pedido": numero,
                                       "status": "duplicado", "pedido_id": existe["id"]})
                    continue

                cliente_id = await _resolver_cliente_id(parsed, cur)
                cur.execute("""INSERT INTO pedidos
                    (numero_pedido, cliente_id, prazo_entrega, vendedor, observacoes, status)
                    VALUES (?,?,?,?,?,'aberto')""",
                    (str(numero), cliente_id, parsed.get("prazo_entrega") or datetime.date.today().isoformat(),
                     parsed.get("vendedor"), parsed.get("observacoes")))
                pedido_id = cur.lastrowid
                for it in parsed.get("itens", []):
                    cur.execute("""INSERT INTO pedidos_itens
                        (pedido_id, produto_id, descricao, quantidade, unidade, qtd_produzida, status)
                        VALUES (?,?,?,?,?,0,'aberto')""",
                        (pedido_id, None, it["descricao"], it["quantidade"], it.get("unidade") or "unidade"))
                conn.commit()
                criados += 1
                resultados.append({"arquivo": nome, "numero_pedido": numero, "status": "criado",
                                   "pedido_id": pedido_id, "cliente": parsed["cliente"].get("razao_social"),
                                   "qtd_itens": len(parsed.get("itens", [])),
                                   "faltando": parsed.get("faltando", [])})
            except Exception as e:
                conn.rollback()
                erros += 1
                resultados.append({"arquivo": nome, "status": "erro", "motivo": str(e)})
            finally:
                if tmp_path:
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        try:
            _auto_vincular_itens(conn)
            conn.commit()
        except Exception:
            conn.rollback()
    finally:
        conn.close()
    return {
        "resumo": {"total": len(files), "criados": criados, "duplicados": duplicados, "erros": erros},
        "resultados": resultados,
    }


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
            if _is_pedido_sac(texto):
                parsed = _parse_pedido_sac(texto)
            else:
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
        try:
            cur = conn.cursor()
            
            if doc_limpo:
                cliente = cur.execute("SELECT id FROM pedidos_clientes WHERE cnpj=? AND ativo=1", (doc_limpo,)).fetchone()
            if not cliente and parsed["cliente"].get("razao_social"):
                cliente = cur.execute("SELECT id FROM pedidos_clientes WHERE UPPER(razao_social)=UPPER(?) AND ativo=1", (parsed["cliente"]["razao_social"],)).fetchone()

            if cliente:
                cliente_id = cliente["id"]
            else:
                c = await _preparar_cliente_para_cadastro(parsed["cliente"])
                cur.execute("""INSERT INTO pedidos_clientes
                    (cnpj, razao_social, nome_fantasia, email, telefone, cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c.get("cnpj"), c.get("razao_social"), c.get("nome_fantasia"), c.get("email"), c.get("telefone"), c.get("cep"), c.get("logradouro"), c.get("numero"), c.get("complemento"), c.get("bairro"), c.get("cidade"), c.get("uf"), "Cadastrado automaticamente pela importação de pedido"))
                cliente_id = cur.lastrowid
                conn.commit()
        finally:
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

def _recalc_status_pedido(cur, pedido_id):
    """Recalcula o status do pedido a partir do progresso real dos itens (qtd_produzida)."""
    counts = cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN status='entregue' THEN 1 END) as entregues,
               COUNT(CASE WHEN status IN ('produzido','entregue')
                           OR (qtd_produzida >= quantidade AND quantidade > 0) THEN 1 END) as produzidos,
               COUNT(CASE WHEN qtd_produzida > 0
                           OR status IN ('em_producao','produzido','entregue') THEN 1 END) as iniciados
        FROM pedidos_itens WHERE pedido_id=?
    """, (pedido_id,)).fetchone()
    total = counts["total"] or 0
    if total == 0:
        novo = 'aberto'
    elif counts["entregues"] == total:
        novo = 'entregue'
    elif counts["produzidos"] == total:
        novo = 'produzido'
    elif counts["iniciados"] > 0:
        novo = 'em_producao'
    else:
        novo = 'aberto'
    cur.execute("UPDATE pedidos SET status=? WHERE id=?", (novo, pedido_id))
    return novo


@router.get("/")
def listar_pedidos(status: Optional[str] = None, cliente_id: Optional[int] = None):
    conn = get_conn()
    query = """
        SELECT p.*,
               c.razao_social as cliente_nome,
               c.nome_fantasia,
               COUNT(i.id) as total_itens,
               COUNT(CASE WHEN i.status = 'entregue' THEN 1 END) as itens_entregues,
               COUNT(CASE WHEN i.status IN ('produzido','entregue')
                           OR (i.qtd_produzida >= i.quantidade AND i.quantidade > 0) THEN 1 END) as itens_produzidos,
               COUNT(CASE WHEN i.qtd_produzida > 0
                           OR i.status IN ('em_producao','produzido','entregue') THEN 1 END) as itens_iniciados,
               GROUP_CONCAT(DISTINCT pr.marca) as marcas,
               julianday(p.prazo_entrega) - julianday('now') as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        LEFT JOIN pedidos_itens i ON i.pedido_id = p.id
        LEFT JOIN estoque_produtos pr ON pr.id = i.produto_id
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
    result = []
    for r in rows:
        d = dict(r)
        tot = d.get("total_itens") or 0
        prod = d.get("itens_produzidos") or 0
        entr = d.get("itens_entregues") or 0
        ini = d.get("itens_iniciados") or 0
        if tot > 0 and entr == tot:
            d["status_efetivo"] = "entregue"
        elif tot > 0 and prod == tot:
            d["status_efetivo"] = "produzido"
        elif ini > 0:
            d["status_efetivo"] = "em_producao"
        else:
            d["status_efetivo"] = d.get("status") or "aberto"
        result.append(d)
    return result

@router.post("/resync-status")
def resync_status_pedidos():
    """Reconcilia o status de itens e pedidos a partir do progresso real (qtd_produzida).
    Corrige pedidos antigos que ficaram 'aberto' apesar de já produzidos."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""UPDATE pedidos_itens SET status='produzido'
                   WHERE qtd_produzida >= quantidade AND quantidade > 0 AND status NOT IN ('entregue')""")
    cur.execute("""UPDATE pedidos_itens SET status='em_producao'
                   WHERE qtd_produzida > 0 AND qtd_produzida < quantidade AND status='aberto'""")
    ped_ids = [r["id"] for r in cur.execute("SELECT id FROM pedidos").fetchall()]
    for pid in ped_ids:
        _recalc_status_pedido(cur, pid)
    conn.commit()
    conn.close()
    return {"mensagem": "Status sincronizado", "pedidos": len(ped_ids)}


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
    _auto_vincular_itens(conn)
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
            
    _auto_vincular_itens(conn)
    _recalc_status_pedido(cur, id)
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


