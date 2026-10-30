from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel
from typing import Optional, List
from database import get_conn
from auth_utils import get_current_user
from rotas.producao import _reverter_estoque_producao
from vendedores import vincular_pedido, vincular_pedidos_sem_vendedor, separar_nomes, juntar_nomes
import httpx
import os, re, tempfile, datetime
from html.parser import HTMLParser

router = APIRouter()

def verificar_permissao(modulo: str, acao: str, current_user: dict) -> bool:
    if current_user.get("role") == "gestor":
        return True
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT permitido FROM usuario_permissoes WHERE usuario_id = ? AND modulo = ? AND acao = ?",
            (current_user["id"], modulo, acao)
        ).fetchone()
        return bool(row and row["permitido"])
    finally:
        conn.close()


def exigir_permissao(modulo: str, acao: str, current_user: dict):
    if not verificar_permissao(modulo, acao, current_user):
        raise HTTPException(403, "Você não tem permissão para esta ação. Fale com o Gestor (Controle de Acesso).")


def exigir_gestor(current_user: dict):
    if current_user.get("role") != "gestor":
        raise HTTPException(403, "Acesso restrito ao perfil de Gestor.")


# ─── FLUXO PÓS-PRODUÇÃO ──────────────────────────────────────────────────────
# produzido ──(vendedor)──> aguardando_nf ──(expedição: NF)──> enviado ──> entregue (futuro)
#           └─(vendedor)──> aguardando_retirada ──(expedição: NF)──> retirado
STATUS_LIBERADOS = ("aguardando_nf", "aguardando_retirada")
STATUS_CONCLUIDOS = ("enviado", "retirado", "entregue")
STATUS_POS_PRODUCAO = ("produzido",) + STATUS_LIBERADOS + STATUS_CONCLUIDOS
STATUS_VALIDOS_PEDIDO = ["aberto", "em_producao"] + list(STATUS_POS_PRODUCAO) + ["em_estoque"]
# em_estoque: pedido produzido para ficar no estoque do cliente (não vai para vendedor/Expedição)


def _nome_usuario(current_user: dict) -> str:
    return current_user.get("nome") or current_user.get("username") or "sistema"


def _marcar_usuario_hist(conn, pedido_id: int, current_user: dict):
    """Grava quem fez a última mudança de status (o gatilho do banco cria a linha)."""
    conn.execute("""UPDATE pedidos_status_hist SET usuario = ?
                    WHERE id = (SELECT MAX(id) FROM pedidos_status_hist WHERE pedido_id = ?)
                      AND usuario IS NULL""", (_nome_usuario(current_user), pedido_id))


def _revenda_pendente(conn, pedido_id: int) -> int:
    return conn.execute("""
        SELECT COUNT(*) FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
        LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
        WHERE i.pedido_id = ? AND ec.tipo = 'revenda'
          AND (i.status IS NULL OR i.status != 'entregue')
    """, (pedido_id,)).fetchone()[0]


# Item com embalagem definida: tem caixas lançadas à mão OU o produto tem no cadastro
# medidas + peso da caixa e unidades por caixa (ou o item já está em caixas).
SQL_ITEM_COM_EMBALAGEM = """(
    EXISTS (SELECT 1 FROM pedidos_volumes v WHERE v.pedido_item_id = i.id)
    OR EXISTS (SELECT 1 FROM estoque_produtos ep2 WHERE ep2.id = i.produto_id
               AND COALESCE(ep2.embalagem_comprimento,0) > 0 AND COALESCE(ep2.embalagem_largura,0) > 0
               AND COALESCE(ep2.embalagem_altura,0) > 0 AND COALESCE(ep2.embalagem_peso,0) > 0
               AND (COALESCE(ep2.embalagem_qtd,0) > 0 OR LOWER(COALESCE(i.unidade,'')) LIKE 'cx%'
                    OR LOWER(COALESCE(i.unidade,'')) LIKE 'caixa%')))"""


def _sql_embalagem_pendente(alias_pedido: str = "p") -> str:
    return f"""(SELECT COUNT(*) FROM pedidos_itens i WHERE i.pedido_id = {alias_pedido}.id
                AND NOT {SQL_ITEM_COM_EMBALAGEM})"""


def _sql_revenda_pendente(alias_pedido: str = "p") -> str:
    return f"""(SELECT COUNT(*) FROM pedidos_itens i
                LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
                LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
                WHERE i.pedido_id = {alias_pedido}.id AND ec.tipo = 'revenda'
                  AND (i.status IS NULL OR i.status != 'entregue'))"""


def _embalagem_pendente(conn, pedido_id: int) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM pedidos_itens i WHERE i.pedido_id = ? AND NOT {SQL_ITEM_COM_EMBALAGEM}",
                        (pedido_id,)).fetchone()[0]


def _vendedor_desde(conn) -> str:
    """Data de corte (AAAA-MM-DD) configurada pelo Gestor: pedidos lançados antes
    dela não aparecem no portal do vendedor nem no aviso 'sem vendedor'."""
    row = conn.execute("SELECT valor FROM configuracoes WHERE chave='vendedor_mostrar_desde'").fetchone()
    v = (row["valor"] if row else "") or ""
    v = v.strip()[:10]
    return v if len(v) == 10 else ""


SQL_VALOR_PEDIDO = """(
    COALESCE((SELECT SUM(COALESCE(it.quantidade,0) * COALESCE(it.valor_unitario,0) - COALESCE(it.desconto,0))
              FROM pedidos_itens it WHERE it.pedido_id = p.id), 0)
    + COALESCE(p.acrescimo,0) + COALESCE(p.frete,0) - COALESCE(p.desconto_global,0))"""


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
    # 1 = cliente com estoque programado (deixamos estoque). None = não mexer.
    estoque_programado: Optional[int] = None

class ItemPedidoIn(BaseModel):
    id: Optional[int] = None  # id do item já existente (edição): permite atualizar em vez de recriar
    produto_id: Optional[int] = None
    descricao: str
    quantidade: float
    unidade: Optional[str] = "unidade"
    valor_unitario: Optional[float] = 0.0
    desconto: Optional[float] = 0.0
    insumo_vinculado_id: Optional[int] = None  # ex.: palmilha escolhida para este item, quando a categoria do produto exige

class ParcelaPedidoIn(BaseModel):
    forma_pagamento: Optional[str] = ""
    vencimento: Optional[str] = ""
    valor: float

class PedidoIn(BaseModel):
    numero_pedido: Optional[str] = None
    cliente_id: int
    prazo_entrega: Optional[str] = ""
    vendedor: Optional[str] = None
    observacoes: Optional[str] = None
    itens: List[ItemPedidoIn] = []
    # None = "não enviado": na edição (PUT) o valor atual é preservado em vez de zerado
    acrescimo: Optional[float] = None
    frete: Optional[float] = None
    desconto_global: Optional[float] = None
    parcelas: Optional[List[ParcelaPedidoIn]] = None
    precisa_pintura: Optional[bool] = False

class StatusItemIn(BaseModel):
    status: str
    qtd_produzida: Optional[float] = None
    split_if_partial: Optional[bool] = False

class SepararRevendaIn(BaseModel):
    marcar: bool = True

class ProgramarSeparacaoIn(BaseModel):
    itens_ids: List[int]
    data_programada: str

class MarcarSeparadoIn(BaseModel):
    marcar: bool = True


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
    unidade_pat = r"(?:und|unid|un|kg|g|litro|lt|l|metro|mt|m|caixa|cx|pacote|pct|pc|pç|par|pares)"
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
                 "mil", "cento", "ct", "rolo", "fardo", "fd", "par", "pares"}

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

def _sac_valores_item(qtd, valores):
    """Interpreta as colunas de valor da linha de item do PDF SAC:
    [Valor Unitário, Desconto, Valor Total]. Só devolve o que for coerente
    (qtd x unitário - desconto = total, com tolerância de centavos); se a conta
    não fechar, não inventa preço — o item segue o comportamento anterior."""
    if len(valores) < 3:
        return {}
    unit, desc, total = valores[0], valores[1], valores[2]
    if abs(qtd * unit - desc - total) <= 0.02:
        return {"valor_unitario": unit, "desconto": desc}
    if abs(qtd * unit - total) <= 0.02:
        return {"valor_unitario": unit, "desconto": 0.0}
    return {}


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
    if inicio is not None:
        # O bloco "Parcelas" pode vir ANTES ou DEPOIS da tabela de itens, conforme o
        # layout do PDF. O fim da região é o primeiro "Parcelas" (ou o rodapé do
        # Softline) que aparece DEPOIS do início da tabela — antes pegava o primeiro
        # "Parcelas" do documento e, quando ele vinha antes dos itens, a região ficava vazia.
        fim = next((i for i in range(inicio, len(linhas))
                    if linhas[i].strip().lower() == "parcelas"
                    or linhas[i].strip().lower().startswith("desenvolvido por")), len(linhas))
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
                        i = j + 2
                        valores = []
                        while i < len(regiao) and _sac_is_money(regiao[i]):
                            valores.append(_br_to_float(regiao[i].replace("R$", "")))
                            i += 1
                        if desc:
                            item = {"descricao": desc[:250], "quantidade": _br_to_float(qtd_raw), "unidade": unidade}
                            item.update(_sac_valores_item(item["quantidade"], valores))
                            itens.append(item)
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
            p_info = conn.execute("SELECT preco FROM estoque_produtos WHERE id = ?", (melhor_id,)).fetchone()
            p_price = p_info["preco"] if p_info else 0.0
            conn.execute("""
                UPDATE pedidos_itens 
                SET produto_id = ?, 
                    valor_unitario = CASE WHEN valor_unitario = 0.0 THEN ? ELSE valor_unitario END 
                WHERE id = ?
            """, (melhor_id, p_price, item['id']))

def _alertas_estoque_para_pedidos(cur, pedido_ids):
    """Para os produtos dos pedidos informados, compara o saldo com a demanda
    total de todos os pedidos abertos. Retorna a lista dos que vão faltar."""
    ids = [pid for pid in (pedido_ids or []) if pid]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    prod_ids = [r["produto_id"] for r in cur.execute(
        f"""SELECT DISTINCT produto_id FROM pedidos_itens
            WHERE pedido_id IN ({placeholders}) AND produto_id IS NOT NULL""", ids).fetchall()]
    alertas = []
    for prod_id in prod_ids:
        prod = cur.execute("""
            SELECT ep.nome, ep.unidade, ec.tipo as categoria_tipo,
                   COALESCE(es.quantidade, 0) as saldo
            FROM estoque_produtos ep
            LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
            LEFT JOIN estoque_saldo es ON es.produto_id = ep.id
            WHERE ep.id = ?""", (prod_id,)).fetchone()
        if not prod:
            continue
        dem = cur.execute("""
            SELECT COALESCE(SUM(pi.quantidade - pi.qtd_produzida), 0) as total
            FROM pedidos_itens pi JOIN pedidos ped ON pi.pedido_id = ped.id
            WHERE pi.produto_id = ? AND ped.status != 'entregue'
              AND pi.quantidade > pi.qtd_produzida""", (prod_id,)).fetchone()
        total_demanda = dem["total"] or 0
        saldo = prod["saldo"] or 0
        if total_demanda > 0 and saldo < total_demanda:
            alertas.append({
                "produto": prod["nome"],
                "unidade": prod["unidade"] or "",
                "categoria_tipo": prod["categoria_tipo"] or "producao",
                "saldo": saldo,
                "demanda": total_demanda,
                "falta": total_demanda - saldo,
            })
    return alertas

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


class _TabelaClientesHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.linhas = []
        self._linha = None
        self._cel = None
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._linha = []
        elif tag == "td" and self._linha is not None:
            self._cel = []
    def handle_endtag(self, tag):
        if tag == "td" and self._cel is not None:
            self._linha.append("".join(self._cel).strip())
            self._cel = None
        elif tag == "tr" and self._linha is not None:
            self.linhas.append(self._linha)
            self._linha = None
    def handle_data(self, data):
        if self._cel is not None:
            self._cel.append(data)


def _cli_val(linha, idx, col):
    i = idx.get(col)
    if i is None or i >= len(linha):
        return None
    v = (linha[i] or "").strip()
    return v or None


def _col_idx(ref):
    letras = "".join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1 if n > 0 else 0


def _ler_xlsx(raw):
    import zipfile, io as _io
    from xml.etree import ElementTree as ET
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(_io.BytesIO(raw))
    nomes = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in nomes:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root:
            shared.append("".join((t.text or "") for t in si.iter(NS + "t")))
    sheets = sorted(n for n in nomes if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
    if not sheets:
        return []
    root = ET.fromstring(z.read(sheets[0]))
    linhas = []
    for row in root.iter(NS + "row"):
        celulas = {}
        maxi = -1
        pos = 0
        for c in row.findall(NS + "c"):
            ref = c.get("r") or ""
            ci = _col_idx(ref) if ref else pos
            pos = ci + 1
            t = c.get("t")
            v = c.find(NS + "v")
            val = ""
            if t == "s" and v is not None and v.text is not None:
                try:
                    val = shared[int(v.text)]
                except Exception:
                    val = ""
            elif t == "inlineStr":
                is_ = c.find(NS + "is")
                if is_ is not None:
                    val = "".join((tt.text or "") for tt in is_.iter(NS + "t"))
            elif v is not None:
                val = v.text or ""
            celulas[ci] = (val or "").strip()
            if ci > maxi:
                maxi = ci
        linha = [celulas.get(i, "") for i in range(maxi + 1)]
        if any(linha):
            linhas.append(linha)
    return linhas


def _ler_csv(texto):
    import csv, io as _io
    amostra = texto[:3000]
    delim = ";" if amostra.count(";") > amostra.count(",") else ","
    linhas = []
    for row in csv.reader(_io.StringIO(texto), delimiter=delim):
        if any((x or "").strip() for x in row):
            linhas.append([(x or "").strip() for x in row])
    return linhas


def _extrair_linhas(raw):
    if raw[:2] == bytes([0x50, 0x4B]):
        return _ler_xlsx(raw)
    if raw[:4] == bytes([0xD0, 0xCF, 0x11, 0xE0]):
        raise HTTPException(400, "Este arquivo e um Excel binario (.xls). Salve como .xlsx ou .csv (ou use o arquivo original exportado do sistema) e tente novamente.")
    try:
        texto = raw.decode("ISO-8859-1")
    except Exception:
        texto = raw.decode("utf-8", errors="replace")
    if "<td" in texto.lower():
        parser = _TabelaClientesHTML()
        parser.feed(texto)
        return [l for l in parser.linhas if l]
    if ("," in texto) or (";" in texto):
        return _ler_csv(texto)
    raise HTTPException(400, "Formato nao reconhecido. Envie o .xls exportado do sistema, ou um arquivo .xlsx/.csv.")


@router.post("/importar-clientes")
async def importar_clientes(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Arquivo vazio")
    linhas = _extrair_linhas(raw)
    if len(linhas) < 2:
        raise HTTPException(400, "Nenhum cliente encontrado no arquivo (so cabecalho ou vazio).")
    cabecalho = linhas[0]
    idx = {nome: i for i, nome in enumerate(cabecalho)}
    if "Nome" not in idx:
        raise HTTPException(400, "Coluna 'Nome' nao encontrada. Verifique o arquivo exportado.")

    clientes = []
    for linha in linhas[1:]:
        nome = _cli_val(linha, idx, "Nome")
        if not nome:
            continue
        doc_raw = _cli_val(linha, idx, "Documento")
        doc = re.sub("[^0-9]", "", doc_raw) if doc_raw else None
        doc = doc or None
        tel = _cli_val(linha, idx, "Celular") or _cli_val(linha, idx, "Telefone")
        codigo = _cli_val(linha, idx, "Codigo")
        contato = _cli_val(linha, idx, "Contato")
        obs = ["Importado da planilha" + ((" (cod. origem %s)" % codigo) if codigo else "")]
        if contato:
            obs.append("Contato: %s" % contato)
        clientes.append({
            "cnpj": doc,
            "razao_social": nome,
            "nome_fantasia": _cli_val(linha, idx, "Fantasia"),
            "ie": _cli_val(linha, idx, "InscricaoEstadual"),
            "email": _cli_val(linha, idx, "Email"),
            "telefone": tel,
            "cep": _cli_val(linha, idx, "Cep"),
            "logradouro": _cli_val(linha, idx, "Endereco"),
            "numero": _cli_val(linha, idx, "Numero"),
            "complemento": _cli_val(linha, idx, "Complemento"),
            "bairro": _cli_val(linha, idx, "Bairro"),
            "cidade": _cli_val(linha, idx, "NomeCidade"),
            "uf": _cli_val(linha, idx, "Estado"),
            "observacoes": " - ".join(obs),
        })

    conn = get_conn()
    cur = conn.cursor()
    docs = set(r[0] for r in cur.execute("SELECT cnpj FROM pedidos_clientes WHERE cnpj IS NOT NULL AND cnpj <> ''").fetchall())
    nomes = set((r[0] or "").strip().upper() for r in cur.execute("SELECT razao_social FROM pedidos_clientes").fetchall())
    novos = []
    ja_existentes = 0
    dup_arquivo = 0
    vd = set()
    vn = set()
    for c in clientes:
        doc = c["cnpj"]
        nk = c["razao_social"].strip().upper()
        if doc and doc in docs:
            ja_existentes += 1
            continue
        if (not doc) and nk in nomes:
            ja_existentes += 1
            continue
        if doc and doc in vd:
            dup_arquivo += 1
            continue
        if (not doc) and nk in vn:
            dup_arquivo += 1
            continue
        if doc:
            vd.add(doc)
        else:
            vn.add(nk)
        novos.append(c)

    if novos:
        cur.executemany(
            "INSERT INTO pedidos_clientes (cnpj, razao_social, nome_fantasia, ie, email, telefone, cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes, ativo) "
            "VALUES (:cnpj, :razao_social, :nome_fantasia, :ie, :email, :telefone, :cep, :logradouro, :numero, :complemento, :bairro, :cidade, :uf, :observacoes, 1)",
            novos
        )
        conn.commit()
    amostra = [{"razao_social": c["razao_social"], "cnpj": c["cnpj"], "cidade": c["cidade"], "uf": c["uf"]} for c in novos[:5]]
    conn.close()
    return {"lidos": len(clientes), "inseridos": len(novos), "ja_existentes": ja_existentes, "duplicados_arquivo": dup_arquivo, "amostra": amostra}


@router.post("/importar-arquivos-lote")
async def importar_pedidos_lote(files: List[UploadFile] = File(...), current_user: dict = Depends(get_current_user)):
    """Importa vários PDFs de pedido de uma vez: cria cliente+pedido+itens, pula duplicados (por número) e devolve um resumo."""
    if not files:
        raise HTTPException(400, "Selecione ao menos um arquivo")
    resultados = []
    criados = duplicados = erros = 0
    criados_ids = []
    alertas = []
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
                uid_vend = vincular_pedido(conn, pedido_id)
                vendedor_outro = None
                if current_user.get("role") == "comercial":
                    if not uid_vend:
                        # Vendedor importando: pedido sem vendedor reconhecido fica com quem importou
                        cur.execute("UPDATE pedidos SET vendedor_usuario_id=? WHERE id=?", (current_user["id"], pedido_id))
                    elif uid_vend != current_user["id"]:
                        vendedor_outro = parsed.get("vendedor")
                for it in parsed.get("itens", []):
                    cur.execute("""INSERT INTO pedidos_itens
                        (pedido_id, produto_id, descricao, quantidade, unidade, valor_unitario, desconto, qtd_produzida, status)
                        VALUES (?,?,?,?,?,?,?,0,'aberto')""",
                        (pedido_id, None, it["descricao"], it["quantidade"], it.get("unidade") or "unidade",
                         it.get("valor_unitario") or 0, it.get("desconto") or 0))
                conn.commit()
                criados += 1
                criados_ids.append(pedido_id)
                resultados.append({"arquivo": nome, "numero_pedido": numero, "status": "criado",
                                   "pedido_id": pedido_id, "cliente": parsed["cliente"].get("razao_social"),
                                   "vendedor_outro": vendedor_outro,
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
        try:
            alertas = _alertas_estoque_para_pedidos(cur, criados_ids)
        except Exception:
            alertas = []
    finally:
        conn.close()
    return {
        "resumo": {"total": len(files), "criados": criados, "duplicados": duplicados, "erros": erros},
        "resultados": resultados,
        "alertas_estoque": alertas,
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
         cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes, estoque_programado)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (c.cnpj, c.razao_social, c.nome_fantasia, c.ie, c.email, c.telefone,
         c.cep, c.logradouro, c.numero, c.complemento, c.bairro, c.cidade, c.uf, c.observacoes,
         1 if c.estoque_programado else 0))
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
    if c.estoque_programado is not None:
        conn.execute("UPDATE pedidos_clientes SET estoque_programado=? WHERE id=?", (1 if c.estoque_programado else 0, id))
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
    # Obter status atual para preservar 'enviado' se for o caso
    pedido = cur.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
    current_status = pedido["status"] if pedido else "aberto"
    para_estoque = bool(pedido and "para_estoque_cliente" in pedido.keys() and pedido["para_estoque_cliente"])

    counts = cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN status='entregue' THEN 1 END) as entregues,
               COUNT(CASE WHEN (ec.tipo IS NULL OR ec.tipo != 'revenda') THEN 1 END) as total_prod,
               COUNT(CASE WHEN (ec.tipo IS NULL OR ec.tipo != 'revenda') AND (status IN ('produzido','entregue') OR (qtd_produzida >= quantidade AND quantidade > 0)) THEN 1 END) as produzidos,
               COUNT(CASE WHEN (ec.tipo IS NULL OR ec.tipo != 'revenda') AND (qtd_produzida > 0 OR status IN ('em_producao','produzido','entregue')) THEN 1 END) as iniciados
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
        LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
        WHERE i.pedido_id=?
    """, (pedido_id,)).fetchone()
    total = counts["total"] or 0
    entregues = counts["entregues"] or 0
    total_prod = counts["total_prod"] or 0
    produzidos = counts["produzidos"] or 0
    iniciados = counts["iniciados"] or 0

    if total == 0:
        novo = 'aberto'
    elif entregues == total:
        novo = 'entregue'
    elif current_status == 'entregue':
        novo = 'entregue'
    elif current_status == 'enviado':
        novo = 'enviado'
    elif current_status in ('aguardando_nf', 'aguardando_retirada', 'retirado'):
        novo = current_status
    elif total_prod == 0:
        novo = 'produzido'
    elif produzidos == total_prod:
        novo = 'produzido'
    elif iniciados > 0:
        novo = 'em_producao'
    else:
        novo = 'aberto'
    # Pedido para o estoque do cliente: terminou a produção → entra no estoque do cliente
    if para_estoque and novo in ('produzido', 'entregue') and current_status not in STATUS_LIBERADOS + STATUS_CONCLUIDOS:
        novo = 'em_estoque'
    cur.execute("UPDATE pedidos SET status=? WHERE id=?", (novo, pedido_id))
    if novo == 'em_estoque' and current_status != 'em_estoque':
        _entrada_estoque_cliente(cur, pedido_id)
    elif current_status == 'em_estoque' and novo != 'em_estoque':
        cur.execute("DELETE FROM estoque_cliente_mov WHERE pedido_id=? AND tipo='entrada'", (pedido_id,))
    _checar_bloqueio_revenda(cur, pedido_id, novo)
    return novo


def _entrada_estoque_cliente(cur, pedido_id):
    """Lança no estoque do cliente o que foi produzido no pedido (itens de produção; revenda fica de fora)."""
    ped = cur.execute("SELECT cliente_id, numero_pedido FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
    if not ped:
        return
    cur.execute("DELETE FROM estoque_cliente_mov WHERE pedido_id=? AND tipo='entrada'", (pedido_id,))
    itens = cur.execute("""
        SELECT i.id, i.produto_id, i.descricao, i.quantidade, i.qtd_produzida, i.valor_unitario
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON ep.id = i.produto_id
        LEFT JOIN estoque_categorias ec ON ec.id = ep.categoria_id
        WHERE i.pedido_id = ? AND (ec.tipo IS NULL OR ec.tipo != 'revenda')
    """, (pedido_id,)).fetchall()
    for it in itens:
        qtd = float(it["qtd_produzida"] or 0) or float(it["quantidade"] or 0)
        if qtd <= 0:
            continue
        cur.execute("""INSERT INTO estoque_cliente_mov
                       (cliente_id, produto_id, descricao, tipo, quantidade, valor_unitario, pedido_id, pedido_item_id, usuario, observacao)
                       VALUES (?, ?, ?, 'entrada', ?, ?, ?, ?, 'Produção', ?)""",
                    (ped["cliente_id"], it["produto_id"], _desc_estoque(it["descricao"]), qtd,
                     it["valor_unitario"] or 0, pedido_id, it["id"], f"Produzido no pedido {ped['numero_pedido']}"))


def _desc_estoque(d) -> str:
    return re.sub(r"\s+", " ", str(d or "").strip()).upper() or "(SEM DESCRIÇÃO)"


def _checar_bloqueio_revenda(cur, pedido_id, status):
    """Pedido produzido com revenda ainda por separar ou com item sem embalagem
    informada fica 'Aguardando separação/embalagem' (o vendedor vê, mas não consegue
    informar o frete). Quando tudo estiver ok, o pedido é liberado: registra no
    histórico (vira novidade para o vendedor) e a contagem de dias recomeça."""
    try:
        ped = cur.execute("SELECT COALESCE(revenda_bloqueado,0) AS bloq FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
    except Exception:
        return  # banco ainda sem a coluna (migração não rodou)
    if not ped:
        return
    pend = (_revenda_pendente(cur, pedido_id) + _embalagem_pendente(cur, pedido_id)) if status == 'produzido' else 0
    if status == 'produzido' and pend > 0:
        if not ped["bloq"]:
            cur.execute("UPDATE pedidos SET revenda_bloqueado=1 WHERE id=?", (pedido_id,))
    elif ped["bloq"]:
        cur.execute("UPDATE pedidos SET revenda_bloqueado=0 WHERE id=?", (pedido_id,))
        if status == 'produzido':
            cur.execute("""INSERT INTO pedidos_status_hist (pedido_id, status_anterior, status, usuario)
                           VALUES (?, 'aguardando_separacao', 'produzido', 'Separação/embalagem')""", (pedido_id,))
            cur.execute("UPDATE pedidos SET status_desde=datetime('now','localtime') WHERE id=?", (pedido_id,))


@router.get("/")
def listar_pedidos(status: Optional[str] = None, cliente_id: Optional[int] = None,
                   current_user: dict = Depends(get_current_user)):
    # Vendedor (perfil Comercial) só enxerga os pedidos vinculados a ele
    so_do_vendedor = current_user.get("role") == "comercial"
    conn = get_conn()
    query = """
        SELECT p.*,
               c.razao_social as cliente_nome,
               c.nome_fantasia,
               COUNT(i.id) as total_itens,
               COUNT(CASE WHEN i.status = 'entregue' THEN 1 END) as itens_entregues,
               COUNT(CASE WHEN (ec.tipo IS NULL OR ec.tipo != 'revenda') AND (i.status IN ('produzido','entregue')
                           OR (i.qtd_produzida >= i.quantidade AND i.quantidade > 0)) THEN 1 END) as itens_produzidos,
               COUNT(CASE WHEN (ec.tipo IS NULL OR ec.tipo != 'revenda') AND (i.qtd_produzida > 0
                           OR i.status IN ('em_producao','produzido','entregue')) THEN 1 END) as itens_iniciados,
               COUNT(CASE WHEN (ec.tipo IS NULL OR ec.tipo != 'revenda') THEN 1 END) as total_itens_prod,
               COUNT(CASE WHEN ec.tipo = 'revenda' THEN 1 END) as itens_revenda,
               COUNT(CASE WHEN ec.tipo = 'revenda' AND (i.status IS NULL OR i.status != 'entregue') THEN 1 END) as revenda_pendentes,
               GROUP_CONCAT(DISTINCT pr.marca) as marcas,
               julianday(p.prazo_entrega) - julianday('now') as dias_restantes,
               uv.nome as vendedor_usuario_nome
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        LEFT JOIN usuarios uv ON uv.id = p.vendedor_usuario_id
        LEFT JOIN pedidos_itens i ON i.pedido_id = p.id
        LEFT JOIN estoque_produtos pr ON pr.id = i.produto_id
        LEFT JOIN estoque_categorias ec ON pr.categoria_id = ec.id
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
    if so_do_vendedor:
        desde = _vendedor_desde(conn)
        filtro_v = " AND p.vendedor_usuario_id = ? "
        params.append(current_user["id"])
        if desde:
            filtro_v += " AND date(p.created_at) >= ? "
            params.append(desde)
        query = query.replace(" GROUP BY p.id ", filtro_v + "GROUP BY p.id ", 1)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        tot = d.get("total_itens") or 0
        tot_prod = d.get("total_itens_prod") or 0
        prod_prod = d.get("itens_produzidos") or 0
        entr = d.get("itens_entregues") or 0
        ini_prod = d.get("itens_iniciados") or 0
        stored = d.get("status") or "aberto"
        if stored in STATUS_LIBERADOS + STATUS_CONCLUIDOS + ("em_estoque",):
            d["status_efetivo"] = stored
        elif tot > 0 and entr == tot:
            d["status_efetivo"] = "entregue"
        elif tot_prod == 0:
            d["status_efetivo"] = "produzido"
        elif prod_prod == tot_prod:
            d["status_efetivo"] = "produzido"
        elif ini_prod > 0:
            d["status_efetivo"] = "em_producao"
        else:
            d["status_efetivo"] = stored
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


# ─── VENDEDOR DO PEDIDO ──────────────────────────────────────────────────────

class AtribuirVendedorIn(BaseModel):
    usuario_id: int
    lembrar_nome: Optional[bool] = True


@router.get("/sem-vendedor")
def pedidos_sem_vendedor(current_user: dict = Depends(get_current_user)):
    """Pedidos em andamento cujo nome de vendedor não bateu com nenhum usuário."""
    exigir_gestor(current_user)
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT p.id, p.numero_pedido, p.vendedor, p.status, p.prazo_entrega, p.created_at,
                   c.razao_social AS cliente_nome
            FROM pedidos p
            JOIN pedidos_clientes c ON c.id = p.cliente_id
            WHERE p.vendedor_usuario_id IS NULL
              AND COALESCE(p.status, 'aberto') NOT IN ('enviado', 'retirado', 'entregue')
              AND (? = '' OR date(p.created_at) >= ?)
            ORDER BY p.created_at DESC, p.id DESC
        """, (_vendedor_desde(conn), _vendedor_desde(conn))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.put("/{id}/vendedor")
def atribuir_vendedor(id: int, body: AtribuirVendedorIn, current_user: dict = Depends(get_current_user)):
    """Gestor atribui o vendedor do pedido. Com lembrar_nome, o nome que veio no
    pedido passa a ser reconhecido para esse usuário nas próximas importações
    (e os outros pedidos pendentes com o mesmo nome são vinculados na hora)."""
    exigir_gestor(current_user)
    conn = get_conn()
    try:
        ped = conn.execute("SELECT id, numero_pedido, vendedor, vendedor_usuario_id FROM pedidos WHERE id=?", (id,)).fetchone()
        if not ped:
            raise HTTPException(404, "Pedido não encontrado")
        usr = conn.execute("SELECT id, nome, COALESCE(vendedor_nomes,'') AS vendedor_nomes FROM usuarios WHERE id=? AND ativo=1",
                           (body.usuario_id,)).fetchone()
        if not usr:
            raise HTTPException(400, "Usuário não encontrado ou inativo")
        conn.execute("UPDATE pedidos SET vendedor_usuario_id=? WHERE id=?", (usr["id"], id))
        outros = 0
        nome_pdf = (ped["vendedor"] or "").strip()
        if body.lembrar_nome and nome_pdf:
            nomes = separar_nomes(usr["vendedor_nomes"]) + [nome_pdf]
            conn.execute("UPDATE usuarios SET vendedor_nomes=? WHERE id=?", (juntar_nomes(nomes), usr["id"]))
            outros = vincular_pedidos_sem_vendedor(conn)
        usuario = current_user.get("nome") or current_user.get("username") or "sistema"
        conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                       VALUES (?, 'atribuir_vendedor', 'pedidos', ?, ?, ?, ?)""",
                     (usuario, id, f"Vendedor do pedido '{ped['numero_pedido']}' atribuído a {usr['nome']}",
                      str(ped["vendedor_usuario_id"] or ""), str(usr["id"])))
        conn.commit()
        return {"mensagem": f"Pedido vinculado a {usr['nome']}", "outros_vinculados": outros}
    finally:
        conn.close()


# ─── VENDEDOR: MEUS PEDIDOS / DEFINIR ENVIO ─────────────────────────────────

class DefinirEnvioIn(BaseModel):
    modo: str  # 'transportadora' | 'retirada' | 'voltar'
    transportadora: Optional[str] = ""
    frete: Optional[float] = 0
    previsao_entrega: Optional[str] = ""
    retirada_prevista: Optional[str] = ""
    obs_vendedor: Optional[str] = ""


class RetiradaIn(BaseModel):
    nota_fiscal: str
    data_retirada: Optional[str] = ""
    volumes: Optional[int] = 0
    obs: Optional[str] = ""


# ─── CADASTRO DE TRANSPORTADORAS ─────────────────────────────────────────────

class TransportadoraIn(BaseModel):
    nome: str
    cnpj: Optional[str] = ""
    telefone: Optional[str] = ""
    contato: Optional[str] = ""
    email: Optional[str] = ""
    site_rastreio: Optional[str] = ""
    observacoes: Optional[str] = ""
    ativo: Optional[int] = 1


class UnificarTranspIn(BaseModel):
    para_id: int


def _pode_editar_transportadoras(current_user: dict):
    if current_user.get("role") not in ("gestor", "expedicao"):
        raise HTTPException(403, "Só o Gestor ou a Expedição podem alterar o cadastro de transportadoras.")


@router.get("/transportadoras")
def listar_transportadoras(ativos: Optional[int] = 0, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        rows = conn.execute(f"""
            SELECT t.*,
                   (SELECT COUNT(*) FROM pedidos p WHERE p.transportadora = t.nome COLLATE NOCASE
                       AND p.status IN ('enviado','entregue')) AS envios,
                   (SELECT MAX(p.data_despacho) FROM pedidos p WHERE p.transportadora = t.nome COLLATE NOCASE
                       AND p.status IN ('enviado','entregue')) AS ultimo_envio,
                   (SELECT COALESCE(SUM(COALESCE(NULLIF(p.frete_pago,0), p.frete, 0)),0) FROM pedidos p
                     WHERE p.transportadora = t.nome COLLATE NOCASE AND p.status IN ('enviado','entregue')) AS total_frete
            FROM transportadoras t
            {"WHERE t.ativo = 1" if ativos else ""}
            ORDER BY t.ativo DESC, t.nome COLLATE NOCASE
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/transportadoras")
def criar_transportadora(body: TransportadoraIn, current_user: dict = Depends(get_current_user)):
    _pode_editar_transportadoras(current_user)
    nome = " ".join((body.nome or "").split())
    if not nome:
        raise HTTPException(400, "Informe o nome da transportadora.")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM transportadoras WHERE nome = ? COLLATE NOCASE", (nome,)).fetchone():
            raise HTTPException(400, "Já existe uma transportadora com esse nome.")
        cur = conn.execute("""INSERT INTO transportadoras (nome, cnpj, telefone, contato, email, site_rastreio, observacoes, ativo)
                              VALUES (?,?,?,?,?,?,?,?)""",
                           (nome, (body.cnpj or "").strip(), (body.telefone or "").strip(), (body.contato or "").strip(),
                            (body.email or "").strip(), (body.site_rastreio or "").strip(), (body.observacoes or "").strip(),
                            1 if body.ativo is None else int(body.ativo)))
        conn.commit()
        return {"id": cur.lastrowid, "mensagem": "Transportadora cadastrada"}
    finally:
        conn.close()


@router.put("/transportadoras/{tid}")
def atualizar_transportadora(tid: int, body: TransportadoraIn, current_user: dict = Depends(get_current_user)):
    """Edita o cadastro. Se o nome mudar, os pedidos com o nome antigo são atualizados junto."""
    _pode_editar_transportadoras(current_user)
    nome = " ".join((body.nome or "").split())
    if not nome:
        raise HTTPException(400, "Informe o nome da transportadora.")
    conn = get_conn()
    try:
        atual = conn.execute("SELECT * FROM transportadoras WHERE id=?", (tid,)).fetchone()
        if not atual:
            raise HTTPException(404, "Transportadora não encontrada")
        if conn.execute("SELECT 1 FROM transportadoras WHERE nome = ? COLLATE NOCASE AND id != ?", (nome, tid)).fetchone():
            raise HTTPException(400, "Já existe outra transportadora com esse nome. Use 'Unificar' para juntar as duas.")
        conn.execute("""UPDATE transportadoras SET nome=?, cnpj=?, telefone=?, contato=?, email=?, site_rastreio=?,
                        observacoes=?, ativo=? WHERE id=?""",
                     (nome, (body.cnpj or "").strip(), (body.telefone or "").strip(), (body.contato or "").strip(),
                      (body.email or "").strip(), (body.site_rastreio or "").strip(), (body.observacoes or "").strip(),
                      1 if body.ativo is None else int(body.ativo), tid))
        if atual["nome"] != nome:
            conn.execute("UPDATE pedidos SET transportadora=? WHERE transportadora = ? COLLATE NOCASE", (nome, atual["nome"]))
        conn.commit()
        return {"mensagem": "Transportadora atualizada"}
    finally:
        conn.close()


@router.post("/transportadoras/{tid}/unificar")
def unificar_transportadora(tid: int, body: UnificarTranspIn, current_user: dict = Depends(get_current_user)):
    """Junta duas transportadoras repetidas: os pedidos da 'tid' passam para a 'para_id'
    e o cadastro 'tid' é removido."""
    _pode_editar_transportadoras(current_user)
    if tid == body.para_id:
        raise HTTPException(400, "Escolha uma transportadora diferente.")
    conn = get_conn()
    try:
        de = conn.execute("SELECT * FROM transportadoras WHERE id=?", (tid,)).fetchone()
        para = conn.execute("SELECT * FROM transportadoras WHERE id=?", (body.para_id,)).fetchone()
        if not de or not para:
            raise HTTPException(404, "Transportadora não encontrada")
        n = conn.execute("UPDATE pedidos SET transportadora=? WHERE transportadora = ? COLLATE NOCASE",
                         (para["nome"], de["nome"])).rowcount
        conn.execute("DELETE FROM transportadoras WHERE id=?", (tid,))
        conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                       VALUES (?, 'unificar_transportadora', 'transportadoras', ?, ?, ?, ?)""",
                     (_nome_usuario(current_user), body.para_id, f"{n} pedido(s) passaram de '{de['nome']}' para '{para['nome']}'",
                      de["nome"], para["nome"]))
        conn.commit()
        return {"mensagem": f"Unificado: {n} pedido(s) passaram para {para['nome']}"}
    finally:
        conn.close()


# ─── PRAZOS DAS CORES / ACOMPANHAMENTO / ESTOQUE DOS CLIENTES ────────────────

def _prazos_parados(conn) -> dict:
    """Dias para o selo ficar amarelo / vermelho (configurável pelo Gestor)."""
    def ler(chave, padrao):
        r = conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
        try:
            v = int(float((r["valor"] if r else "") or padrao))
            return v if v >= 0 else padrao
        except (TypeError, ValueError):
            return padrao
    amarelo = ler("prazo_amarelo_dias", 2)
    vermelho = ler("prazo_vermelho_dias", 4)
    if vermelho < amarelo:
        vermelho = amarelo
    return {"amarelo": amarelo, "vermelho": vermelho}


@router.get("/prazos-parados")
def prazos_parados(current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        return _prazos_parados(conn)
    finally:
        conn.close()


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.datetime.strptime(str(s)[:10], "%Y-%m-%d")
        except ValueError:
            return None


@router.get("/acompanhamento")
def acompanhamento(current_user: dict = Depends(get_current_user)):
    """Painel do Gestor: onde e com quem os pedidos pós-produção estão parados,
    valor pronto e não faturado e tempo médio de reação de cada vendedor."""
    exigir_gestor(current_user)
    conn = get_conn()
    try:
        desde = _vendedor_desde(conn)
        prazos = _prazos_parados(conn)
        rows = conn.execute(f"""
            SELECT p.id, p.numero_pedido, p.status, p.status_desde, p.transportadora, p.retirada_prevista,
                   p.vendedor, p.vendedor_usuario_id, uv.nome AS vendedor_nome,
                   c.razao_social AS cliente_nome,
                   ({_sql_revenda_pendente('p')} + {_sql_embalagem_pendente('p')}) AS bloqueios,
                   CAST(julianday('now','localtime') - julianday(p.status_desde) AS INTEGER) AS dias_na_etapa,
                   {SQL_VALOR_PEDIDO} AS valor_total
            FROM pedidos p
            JOIN pedidos_clientes c ON c.id = p.cliente_id
            LEFT JOIN usuarios uv ON uv.id = p.vendedor_usuario_id
            WHERE p.status IN ('produzido','aguardando_nf','aguardando_retirada')
              AND (? = '' OR date(p.created_at) >= ?)
            ORDER BY p.status_desde ASC
        """, (desde, desde)).fetchall()
        pedidos = [dict(r) for r in rows]
        # Produzido com revenda por separar: etapa à parte, com o Estoque
        for p in pedidos:
            if p["status"] == "produzido" and p["bloqueios"]:
                p["status"] = "aguardando_separacao"
        responsavel = {"aguardando_separacao": "Estoque (separação/embalagem)", "produzido": "Vendedor",
                       "aguardando_nf": "Expedição", "aguardando_retirada": "Cliente (retirada)"}
        etapas = {}
        for st in ("aguardando_separacao", "produzido", "aguardando_nf", "aguardando_retirada"):
            lst = [p for p in pedidos if p["status"] == st]
            etapas[st] = {
                "qtd": len(lst),
                "valor": round(sum(p["valor_total"] or 0 for p in lst), 2),
                "mais_antigo_dias": max([p["dias_na_etapa"] or 0 for p in lst], default=0),
                "atrasados": sum(1 for p in lst if (p["dias_na_etapa"] or 0) >= prazos["vermelho"]),
                "responsavel": responsavel[st],
            }
        for p in pedidos:
            p["responsavel"] = responsavel[p["status"]]

        # Tempo médio (últimos 30 dias): Produzido → vendedor definir o envio, por vendedor;
        # e Aguardando NF/retirada → Expedição concluir.
        hist = conn.execute("""
            SELECT h.pedido_id, h.status_anterior, h.status, h.em, p.vendedor_usuario_id, uv.nome AS vendedor_nome
            FROM pedidos_status_hist h
            JOIN pedidos p ON p.id = h.pedido_id
            LEFT JOIN usuarios uv ON uv.id = p.vendedor_usuario_id
            WHERE h.em >= datetime('now','localtime','-60 days')
            ORDER BY h.pedido_id, h.id
        """).fetchall()
        entrou = {}
        por_vendedor = {}
        expedicao = []
        limite = datetime.datetime.now() - datetime.timedelta(days=30)
        for h in hist:
            em = _parse_dt(h["em"])
            if em is None:
                continue
            chave = (h["pedido_id"], h["status"])
            entrou[chave] = em
            inicio = entrou.get((h["pedido_id"], h["status_anterior"]))
            if not inicio or em < limite:
                continue
            dias = (em - inicio).total_seconds() / 86400
            if h["status_anterior"] == "produzido" and h["status"] in STATUS_LIBERADOS and h["vendedor_usuario_id"]:
                v = por_vendedor.setdefault(h["vendedor_usuario_id"], {"vendedor_nome": h["vendedor_nome"], "tempos": []})
                v["tempos"].append(dias)
            if h["status_anterior"] in STATUS_LIBERADOS and h["status"] in ("enviado", "retirado"):
                expedicao.append(dias)
        aguardando_por_vend = {}
        for p in pedidos:
            if p["status"] == "produzido" and p["vendedor_usuario_id"]:
                a = aguardando_por_vend.setdefault(p["vendedor_usuario_id"], {"vendedor_nome": p["vendedor_nome"], "qtd": 0})
                a["qtd"] += 1
        vendedores = []
        for uid in set(por_vendedor) | set(aguardando_por_vend):
            t = por_vendedor.get(uid, {}).get("tempos", [])
            vendedores.append({
                "vendedor_id": uid,
                "vendedor_nome": (por_vendedor.get(uid) or aguardando_por_vend.get(uid))["vendedor_nome"],
                "tempo_medio_dias": round(sum(t) / len(t), 1) if t else None,
                "liberados_30d": len(t),
                "aguardando_agora": aguardando_por_vend.get(uid, {}).get("qtd", 0),
            })
        vendedores.sort(key=lambda v: (v["tempo_medio_dias"] is None, -(v["tempo_medio_dias"] or 0)))
        sem_vendedor = conn.execute("""
            SELECT COUNT(*) FROM pedidos p
            WHERE p.vendedor_usuario_id IS NULL AND COALESCE(p.status,'aberto') NOT IN ('enviado','retirado','entregue')
              AND (? = '' OR date(p.created_at) >= ?)
        """, (desde, desde)).fetchone()[0]
        return {
            "prazos": prazos,
            "mostrar_desde": desde,
            "etapas": etapas,
            "valor_nao_faturado": round(sum(e["valor"] for e in etapas.values()), 2),
            "parados": pedidos[:40],
            "vendedores": vendedores,
            "expedicao_tempo_medio_dias": round(sum(expedicao) / len(expedicao), 1) if expedicao else None,
            "expedicao_concluidos_30d": len(expedicao),
            "sem_vendedor": sem_vendedor,
        }
    finally:
        conn.close()


# ─── ESTOQUE DO CLIENTE (copo personalizado guardado para o cliente) ─────────

class EntregaEstoqueItemIn(BaseModel):
    produto_id: Optional[int] = None
    descricao: str
    quantidade: float


class EntregaEstoqueIn(BaseModel):
    cliente_id: int
    itens: List[EntregaEstoqueItemIn]
    observacao: Optional[str] = ""


class AjusteEstoqueClienteIn(BaseModel):
    cliente_id: int
    produto_id: Optional[int] = None
    descricao: str
    quantidade: float          # + entra / - baixa
    observacao: Optional[str] = ""


class ParaEstoqueIn(BaseModel):
    ativo: bool


def _pode_mexer_estoque_cliente(current_user: dict) -> bool:
    if current_user.get("role") == "gestor":
        return True
    if current_user.get("role") == "comercial":
        return False
    return verificar_permissao("estoque", "movimentar", current_user)


def _clientes_do_vendedor(conn, uid: int) -> set:
    return {r[0] for r in conn.execute(
        "SELECT DISTINCT cliente_id FROM pedidos WHERE vendedor_usuario_id = ?", (uid,)).fetchall()}


def _saldos_estoque_cliente(conn, cliente_ids=None) -> list:
    """Saldo por cliente + produto + descrição, com consumo dos últimos 6 meses e cobertura."""
    filtro, params = "", []
    if cliente_ids is not None:
        if not cliente_ids:
            return []
        filtro = f"WHERE m.cliente_id IN ({','.join('?' * len(cliente_ids))})"
        params = list(cliente_ids)
    rows = conn.execute(f"""
        SELECT m.cliente_id, c.razao_social AS cliente_nome, c.nome_fantasia, m.produto_id, m.descricao,
               ep.nome AS produto_nome, ep.unidade,
               SUM(m.quantidade) AS saldo,
               SUM(CASE WHEN m.quantidade > 0 THEN m.quantidade ELSE 0 END) AS total_entradas,
               SUM(CASE WHEN m.tipo = 'entrega' AND m.created_at >= datetime('now','localtime','-6 months')
                        THEN -m.quantidade ELSE 0 END) AS saidas_6m,
               MIN(CASE WHEN m.tipo = 'entrega' AND m.created_at >= datetime('now','localtime','-6 months')
                        THEN m.created_at END) AS primeira_saida_6m,
               MAX(CASE WHEN m.tipo = 'entrega' THEN m.created_at END) AS ultima_entrega,
               MAX(CASE WHEN m.tipo = 'entrada' THEN m.created_at END) AS ultima_entrada,
               MAX(m.created_at) AS ultimo_mov
        FROM estoque_cliente_mov m
        JOIN pedidos_clientes c ON c.id = m.cliente_id
        LEFT JOIN estoque_produtos ep ON ep.id = m.produto_id
        {filtro}
        GROUP BY m.cliente_id, COALESCE(m.produto_id, 0), m.descricao
        ORDER BY c.razao_social, m.descricao
    """, params).fetchall()
    hoje = datetime.datetime.now()
    out = []
    for r in rows:
        d = dict(r)
        d["saldo"] = round(d["saldo"] or 0, 2)
        dias_hist = 180
        if d["primeira_saida_6m"]:
            ini = _parse_dt(d["primeira_saida_6m"])
            if ini:
                dias_hist = max(30, min(180, (hoje - ini).days or 1))
        media_dia = (d["saidas_6m"] or 0) / dias_hist if (d["saidas_6m"] or 0) > 0 else 0
        d["consumo_mensal"] = round(media_dia * 30, 1)
        d["cobertura_dias"] = int(d["saldo"] / media_dia) if media_dia > 0 and d["saldo"] > 0 else None
        ref = _parse_dt(d["ultima_entrega"] or d["ultima_entrada"])
        d["dias_parado"] = (hoje - ref).days if ref else None
        if d["saldo"] <= 0:
            d["situacao"] = "zerado"
        elif d["cobertura_dias"] is not None and d["cobertura_dias"] <= 30:
            d["situacao"] = "acabando"
        elif d["dias_parado"] is not None and d["dias_parado"] >= 60:
            d["situacao"] = "parado"
        else:
            d["situacao"] = "ok"
        out.append(d)
    return out


@router.get("/estoque-cliente")
def listar_estoque_cliente(cliente_id: Optional[int] = None, com_zerados: bool = False,
                           current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        ids = None
        if current_user.get("role") == "comercial":
            ids = _clientes_do_vendedor(conn, current_user["id"])
        if cliente_id:
            ids = {cliente_id} if ids is None or cliente_id in ids else set()
        linhas = _saldos_estoque_cliente(conn, ids)
        if not com_zerados:
            linhas = [l for l in linhas if l["saldo"] > 0]
        # Pedidos em produção para o estoque (o que ainda vai entrar)
        filtro, params = "", []
        if ids is not None:
            if not ids:
                return {"linhas": [], "a_caminho": [], "pode_mexer": False}
            filtro = f"AND p.cliente_id IN ({','.join('?' * len(ids))})"
            params = list(ids)
        a_caminho = [dict(r) for r in conn.execute(f"""
            SELECT p.id, p.numero_pedido, p.status, p.cliente_id, c.razao_social AS cliente_nome
            FROM pedidos p JOIN pedidos_clientes c ON c.id = p.cliente_id
            WHERE COALESCE(p.para_estoque_cliente,0) = 1 AND p.status IN ('aberto','em_producao') {filtro}
            ORDER BY p.id
        """, params).fetchall()]
        return {"linhas": linhas, "a_caminho": a_caminho, "pode_mexer": _pode_mexer_estoque_cliente(current_user)}
    finally:
        conn.close()


@router.get("/estoque-cliente/historico")
def historico_estoque_cliente(cliente_id: int, descricao: str, produto_id: Optional[int] = None,
                              current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        if current_user.get("role") == "comercial" and cliente_id not in _clientes_do_vendedor(conn, current_user["id"]):
            raise HTTPException(403, "Cliente não é seu.")
        rows = conn.execute("""
            SELECT m.*, p.numero_pedido, p.status AS pedido_status
            FROM estoque_cliente_mov m LEFT JOIN pedidos p ON p.id = m.pedido_id
            WHERE m.cliente_id = ? AND m.descricao = ? AND COALESCE(m.produto_id,0) = COALESCE(?,0)
            ORDER BY m.id DESC LIMIT 200
        """, (cliente_id, descricao, produto_id)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _saldo_linha(conn, cliente_id, produto_id, descricao) -> float:
    return conn.execute("""SELECT COALESCE(SUM(quantidade),0) FROM estoque_cliente_mov
                           WHERE cliente_id=? AND descricao=? AND COALESCE(produto_id,0)=COALESCE(?,0)""",
                        (cliente_id, descricao, produto_id)).fetchone()[0]


@router.post("/estoque-cliente/entrega")
def criar_entrega_estoque_cliente(body: EntregaEstoqueIn, current_user: dict = Depends(get_current_user)):
    """Tira do estoque do cliente e cria um pedido de entrega já pronto (status Produzido):
    segue o fluxo normal — embalagem → vendedor define frete/retirada → Expedição emite NF."""
    conn = get_conn()
    try:
        role = current_user.get("role")
        if role == "comercial":
            if body.cliente_id not in _clientes_do_vendedor(conn, current_user["id"]):
                raise HTTPException(403, "Cliente não é seu.")
        elif not _pode_mexer_estoque_cliente(current_user):
            raise HTTPException(403, "Você não tem permissão para movimentar o estoque do cliente.")
        itens = [i for i in body.itens if (i.quantidade or 0) > 0]
        if not itens:
            raise HTTPException(400, "Informe a quantidade de pelo menos um item.")
        cli = conn.execute("SELECT id, razao_social FROM pedidos_clientes WHERE id=?", (body.cliente_id,)).fetchone()
        if not cli:
            raise HTTPException(404, "Cliente não encontrado")
        for it in itens:
            saldo = _saldo_linha(conn, body.cliente_id, it.produto_id, it.descricao)
            if it.quantidade > saldo + 1e-9:
                raise HTTPException(400, f"Saldo insuficiente de {it.descricao}: tem {saldo:g}, pediu {it.quantidade:g}.")
        # Vendedor responsável: quem pediu (se vendedor) ou o do último pedido de estoque do cliente
        if role == "comercial":
            vend_id, vend_nome = current_user["id"], _nome_usuario(current_user)
        else:
            ult = conn.execute("""SELECT p.vendedor_usuario_id, p.vendedor FROM pedidos p
                                  WHERE p.cliente_id=? AND p.vendedor_usuario_id IS NOT NULL
                                  ORDER BY COALESCE(p.para_estoque_cliente,0) DESC, p.id DESC LIMIT 1""",
                               (body.cliente_id,)).fetchone()
            vend_id = ult["vendedor_usuario_id"] if ult else None
            vend_nome = (ult["vendedor"] if ult else "") or ""
        seq = conn.execute("SELECT COUNT(*) FROM pedidos WHERE COALESCE(origem_estoque_cliente,0)=1").fetchone()[0] + 1
        numero = f"EST-{seq:04d}"
        while conn.execute("SELECT 1 FROM pedidos WHERE numero_pedido=?", (numero,)).fetchone():
            seq += 1
            numero = f"EST-{seq:04d}"
        usuario = _nome_usuario(current_user)
        cur = conn.cursor()
        cur.execute("""INSERT INTO pedidos (numero_pedido, cliente_id, prazo_entrega, vendedor, vendedor_usuario_id,
                       observacoes, status, origem_estoque_cliente)
                       VALUES (?, ?, date('now','localtime'), ?, ?, ?, 'produzido', 1)""",
                    (numero, body.cliente_id, vend_nome, vend_id,
                     ("Entrega do estoque do cliente. " + (body.observacao or "")).strip()))
        pid = cur.lastrowid
        for it in itens:
            vu = conn.execute("""SELECT valor_unitario FROM estoque_cliente_mov
                                 WHERE cliente_id=? AND descricao=? AND COALESCE(produto_id,0)=COALESCE(?,0)
                                   AND tipo='entrada' ORDER BY id DESC LIMIT 1""",
                              (body.cliente_id, it.descricao, it.produto_id)).fetchone()
            cur.execute("""INSERT INTO pedidos_itens (pedido_id, produto_id, descricao, quantidade, unidade, status,
                           qtd_produzida, valor_unitario) VALUES (?, ?, ?, ?, 'un', 'produzido', ?, ?)""",
                        (pid, it.produto_id, it.descricao, it.quantidade, it.quantidade, (vu[0] if vu else 0) or 0))
            item_id = cur.lastrowid
            cur.execute("""INSERT INTO estoque_cliente_mov (cliente_id, produto_id, descricao, tipo, quantidade,
                           pedido_id, pedido_item_id, usuario, observacao)
                           VALUES (?, ?, ?, 'entrega', ?, ?, ?, ?, ?)""",
                        (body.cliente_id, it.produto_id, it.descricao, -it.quantidade, pid, item_id, usuario,
                         f"Entrega {numero}"))
        _marcar_usuario_hist(conn, pid, current_user)
        _checar_bloqueio_revenda(cur, pid, "produzido")
        conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                        VALUES (?, 'entrega_estoque_cliente', 'pedidos', ?, ?, '', '')""",
                     (usuario, pid, f"Entrega {numero} do estoque de {cli['razao_social']}"))
        conn.commit()
        return {"mensagem": f"Entrega {numero} criada. Ela segue para embalagem e frete.", "pedido_id": pid,
                "numero_pedido": numero}
    finally:
        conn.close()


@router.post("/estoque-cliente/ajuste")
def ajustar_estoque_cliente(body: AjusteEstoqueClienteIn, current_user: dict = Depends(get_current_user)):
    """Baixa ou entrada manual (saldo inicial, perda, entrega feita por fora...)."""
    if not _pode_mexer_estoque_cliente(current_user):
        raise HTTPException(403, "Só o Gestor ou o Estoque podem ajustar o estoque do cliente.")
    if not body.quantidade:
        raise HTTPException(400, "Informe a quantidade.")
    if not (body.observacao or "").strip():
        raise HTTPException(400, "Informe o motivo do ajuste.")
    conn = get_conn()
    try:
        if not conn.execute("SELECT 1 FROM pedidos_clientes WHERE id=?", (body.cliente_id,)).fetchone():
            raise HTTPException(404, "Cliente não encontrado")
        desc = _desc_estoque(body.descricao)
        if body.quantidade < 0:
            saldo = _saldo_linha(conn, body.cliente_id, body.produto_id, desc)
            if -body.quantidade > saldo + 1e-9:
                raise HTTPException(400, f"Saldo insuficiente: tem {saldo:g}.")
        conn.execute("""INSERT INTO estoque_cliente_mov (cliente_id, produto_id, descricao, tipo, quantidade, usuario, observacao)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (body.cliente_id, body.produto_id, desc, "baixa" if body.quantidade < 0 else "ajuste",
                      body.quantidade, _nome_usuario(current_user), body.observacao.strip()))
        conn.commit()
        return {"mensagem": "Estoque do cliente atualizado"}
    finally:
        conn.close()


@router.put("/{id}/para-estoque")
def marcar_para_estoque(id: int, body: ParaEstoqueIn, current_user: dict = Depends(get_current_user)):
    """Marca/desmarca o pedido como produção para o estoque do cliente."""
    if current_user.get("role") == "comercial" or not (
            current_user.get("role") == "gestor"
            or verificar_permissao("producao", "criar", current_user)
            or verificar_permissao("pedidos", "editar", current_user)):
        raise HTTPException(403, "Sem permissão para alterar o destino do pedido.")
    conn = get_conn()
    try:
        ped = conn.execute("SELECT id, status, COALESCE(para_estoque_cliente,0) AS pe, COALESCE(origem_estoque_cliente,0) AS oe FROM pedidos WHERE id=?", (id,)).fetchone()
        if not ped:
            raise HTTPException(404, "Pedido não encontrado")
        if ped["oe"]:
            raise HTTPException(400, "Este pedido já é uma entrega do estoque do cliente.")
        if bool(ped["pe"]) == bool(body.ativo):
            return {"mensagem": "Sem alteração", "status": ped["status"]}
        if ped["status"] in STATUS_LIBERADOS + STATUS_CONCLUIDOS:
            raise HTTPException(400, "O pedido já foi liberado para a Expedição — não dá mais para mudar o destino.")
        if not body.ativo and ped["status"] == "em_estoque":
            neg = conn.execute("""
                SELECT m.descricao FROM estoque_cliente_mov m
                WHERE m.cliente_id = (SELECT cliente_id FROM pedidos WHERE id=?)
                GROUP BY m.cliente_id, COALESCE(m.produto_id,0), m.descricao
                HAVING SUM(CASE WHEN m.pedido_id = ? AND m.tipo = 'entrada' THEN 0 ELSE m.quantidade END) < 0
            """, (id, id)).fetchone()
            if neg:
                raise HTTPException(400, f"Parte deste estoque ({neg['descricao']}) já foi entregue — não dá para desmarcar.")
        cur = conn.cursor()
        cur.execute("UPDATE pedidos SET para_estoque_cliente=? WHERE id=?", (1 if body.ativo else 0, id))
        novo = _recalc_status_pedido(cur, id)
        _marcar_usuario_hist(conn, id, current_user)
        conn.commit()
        return {"mensagem": "Pedido marcado para o estoque do cliente" if body.ativo else "Pedido volta para entrega normal",
                "status": novo}
    finally:
        conn.close()


def _sem_repetir_novidades(rows):
    """Um aviso por pedido/etapa (ex.: produzido e depois liberado da separação de revenda)."""
    vistos, out = set(), []
    for r in rows:
        k = (r["pedido_id"], r["status"])
        if k in vistos:
            continue
        vistos.add(k)
        out.append(dict(r))
    return out


@router.get("/meus")
def meus_pedidos(current_user: dict = Depends(get_current_user)):
    """Pedidos do vendedor logado: em andamento + concluídos nos últimos 15 dias,
    e as novidades (produzido / enviado / retirado) desde o último 'marcar como visto'."""
    conn = get_conn()
    try:
        uid = current_user["id"]
        desde = _vendedor_desde(conn)
        rows = conn.execute(f"""
            SELECT p.id, p.numero_pedido, p.status, p.status_desde, p.prazo_entrega,
                   p.transportadora, p.frete, p.previsao_entrega, p.retirada_prevista,
                   p.obs_vendedor, p.nota_fiscal, p.data_despacho, p.data_entrega, p.envio_definido_em,
                   COALESCE(p.origem_estoque_cliente,0) AS origem_estoque_cliente,
                   c.razao_social AS cliente_nome, c.nome_fantasia,
                   CAST(julianday('now','localtime') - julianday(p.status_desde) AS INTEGER) AS dias_na_etapa,
                   julianday(p.prazo_entrega) - julianday('now') AS dias_restantes,
                   {SQL_VALOR_PEDIDO} AS valor_total,
                   (SELECT COUNT(*) FROM pedidos_itens i
                      LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
                      LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
                     WHERE i.pedido_id = p.id AND ec.tipo = 'revenda'
                       AND (i.status IS NULL OR i.status != 'entregue')) AS revenda_pendentes,
                   {_sql_embalagem_pendente('p')} AS embalagem_pendentes
            FROM pedidos p
            JOIN pedidos_clientes c ON c.id = p.cliente_id
            WHERE p.vendedor_usuario_id = ?
              AND (? = '' OR date(p.created_at) >= ?)
              AND (COALESCE(p.status,'aberto') NOT IN ('enviado','retirado','entregue')
                   -- Concluídos: só os com data real de despacho/entrega nos últimos 15 dias
                   -- (pedidos antigos sem data ficam só na lista geral)
                   OR COALESCE(NULLIF(p.data_entrega,''), NULLIF(p.data_despacho,'')) >= date('now','localtime','-15 days'))
            ORDER BY p.status_desde ASC, p.id ASC
        """, (uid, desde, desde)).fetchall()
        visto = conn.execute("SELECT meus_pedidos_visto_em FROM usuarios WHERE id=?", (uid,)).fetchone()
        visto_em = visto["meus_pedidos_visto_em"] if visto else None
        novidades = conn.execute(f"""
            SELECT h.id, h.status, h.em, h.usuario, p.id AS pedido_id, p.numero_pedido, p.nota_fiscal,
                   c.razao_social AS cliente_nome
            FROM pedidos_status_hist h
            JOIN pedidos p ON p.id = h.pedido_id
            JOIN pedidos_clientes c ON c.id = p.cliente_id
            WHERE p.vendedor_usuario_id = ?
              AND (? = '' OR date(p.created_at) >= ?)
              AND h.status IN ('produzido','enviado','retirado','em_estoque')
              AND NOT (h.status = 'produzido' AND p.status = 'produzido'
                       AND ({_sql_revenda_pendente('p')} + {_sql_embalagem_pendente('p')}) > 0)
              AND h.em > COALESCE(?, datetime('now','localtime','-3 days'))
            ORDER BY h.id DESC
            LIMIT 30
        """, (uid, desde, desde, visto_em)).fetchall()
        return {
            "pedidos": [dict(r) for r in rows],
            "novidades": _sem_repetir_novidades(novidades),
            "visto_em": visto_em,
            "mostrar_desde": desde,
            "prazos": _prazos_parados(conn),
        }
    finally:
        conn.close()


@router.post("/meus/visto")
def meus_pedidos_visto(current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        conn.execute("UPDATE usuarios SET meus_pedidos_visto_em = datetime('now','localtime') WHERE id=?",
                     (current_user["id"],))
        conn.commit()
        return {"mensagem": "ok"}
    finally:
        conn.close()


# ─── DADOS PARA COTAÇÃO DE FRETE (CAIXAS, PESO, CUBAGEM) ────────────────────

class VolumeIn(BaseModel):
    pedido_item_id: Optional[int] = None
    descricao: Optional[str] = ""
    qtd_caixas: float = 1
    comprimento: float = 0
    largura: float = 0
    altura: float = 0
    peso_caixa: float = 0


def _acesso_pedido_cotacao(conn, pedido_id: int, current_user: dict, editar: bool = False):
    ped = conn.execute("SELECT id, numero_pedido, vendedor_usuario_id, status FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
    if not ped:
        raise HTTPException(404, "Pedido não encontrado")
    role = current_user.get("role")
    dono = ped["vendedor_usuario_id"] == current_user.get("id")
    if role == "comercial" and not dono:
        raise HTTPException(403, "Este pedido não é seu.")
    if editar and not _pode_lancar_caixas(current_user):
        raise HTTPException(403, "As caixas do pedido são informadas pelo Estoque ou pela Expedição.")
    return ped


def _pode_lancar_caixas(current_user: dict) -> bool:
    """Embalagem é informada por quem separa/embala: Gestor, Estoque (movimentar) e Expedição (despachar).
    O vendedor só consulta."""
    role = current_user.get("role")
    if role == "gestor":
        return True
    if role == "comercial":
        return False
    return (verificar_permissao("estoque", "movimentar", current_user)
            or verificar_permissao("expedicao", "despachar", current_user))


def _eh_caixa(unidade: str) -> bool:
    u = (unidade or "").strip().lower()
    return u.startswith("cx") or u.startswith("caixa")


def _cubagem_m3(qtd, c, l, a) -> float:
    return (qtd or 0) * (c or 0) * (l or 0) * (a or 0) / 1_000_000.0


@router.get("/{id}/cotacao")
def dados_cotacao(id: int, current_user: dict = Depends(get_current_user)):
    """Caixas, peso e cubagem do pedido para o vendedor cotar o frete.
    Cada item é calculado pelo cadastro do produto (unidades por caixa + medidas e peso
    da caixa fechada). Caixas lançadas à mão e ligadas a um item substituem o cálculo
    daquele item; lançamentos sem item são somados à parte."""
    import math
    conn = get_conn()
    try:
        ped = _acesso_pedido_cotacao(conn, id, current_user)
        itens = conn.execute("""
            SELECT i.id, i.descricao, i.quantidade, i.unidade, i.produto_id,
                   ep.nome AS produto_nome, ep.codigo AS produto_codigo,
                   COALESCE(ep.embalagem_qtd,0) AS emb_qtd, COALESCE(ep.embalagem_comprimento,0) AS emb_c,
                   COALESCE(ep.embalagem_largura,0) AS emb_l, COALESCE(ep.embalagem_altura,0) AS emb_a,
                   COALESCE(ep.embalagem_peso,0) AS emb_peso, ec.tipo AS categoria_tipo
            FROM pedidos_itens i
            LEFT JOIN estoque_produtos ep ON ep.id = i.produto_id
            LEFT JOIN estoque_categorias ec ON ec.id = ep.categoria_id
            WHERE i.pedido_id = ? ORDER BY i.id
        """, (id,)).fetchall()
        manuais = [dict(r) for r in conn.execute(
            "SELECT * FROM pedidos_volumes WHERE pedido_id=? ORDER BY id", (id,)).fetchall()]
        itens_com_manual = {m["pedido_item_id"] for m in manuais if m["pedido_item_id"]}

        linhas, avisos = [], []
        tot_cx = tot_peso = tot_m3 = 0.0
        for it in itens:
            nome = it["descricao"] or it["produto_nome"] or "Item"
            base = {"item_id": it["id"], "descricao": nome, "quantidade": it["quantidade"] or 0,
                    "unidade": it["unidade"] or "", "revenda": it["categoria_tipo"] == "revenda"}
            if it["id"] in itens_com_manual:
                linhas.append({**base, "origem": "manual"})
                continue
            qtd = float(it["quantidade"] or 0)
            tem_medida = it["emb_c"] > 0 and it["emb_l"] > 0 and it["emb_a"] > 0
            if _eh_caixa(it["unidade"]):
                caixas_exatas = qtd
            elif it["emb_qtd"] > 0:
                caixas_exatas = qtd / it["emb_qtd"]
            else:
                caixas_exatas = None
            if caixas_exatas is None or not tem_medida or not it["emb_peso"]:
                falta = []
                if not it["produto_id"]:
                    falta.append("item sem produto vinculado")
                else:
                    if caixas_exatas is None:
                        falta.append("unidades por caixa")
                    if not tem_medida:
                        falta.append("medidas da caixa")
                    if not it["emb_peso"]:
                        falta.append("peso")
                linhas.append({**base, "origem": "sem_dados", "falta": falta})
                avisos.append(f"{nome}: falta {', '.join(falta)} — cadastre no produto ou lance as caixas.")
                continue
            caixas = math.ceil(round(caixas_exatas, 6))
            # Peso proporcional: a última caixa pode ir incompleta
            peso = round(caixas_exatas * it["emb_peso"], 2)
            m3 = _cubagem_m3(caixas, it["emb_c"], it["emb_l"], it["emb_a"])
            tot_cx += caixas; tot_peso += peso; tot_m3 += m3
            linhas.append({**base, "origem": "cadastro", "unid_por_caixa": it["emb_qtd"],
                           "caixas": caixas, "comprimento": it["emb_c"], "largura": it["emb_l"],
                           "altura": it["emb_a"], "peso_caixa": it["emb_peso"],
                           "peso_total": peso, "cubagem_m3": round(m3, 4)})
        for m in manuais:
            q = m["qtd_caixas"] or 0
            peso = round(q * (m["peso_caixa"] or 0), 2)
            m3 = _cubagem_m3(q, m["comprimento"], m["largura"], m["altura"])
            m["peso_total"] = peso
            m["cubagem_m3"] = round(m3, 4)
            tot_cx += q; tot_peso += peso; tot_m3 += m3
        return {
            "pedido_id": id, "numero_pedido": ped["numero_pedido"],
            "itens": linhas, "manuais": manuais, "avisos": avisos,
            "pode_editar": _pode_lancar_caixas(current_user),
            "completo": not any(l["origem"] == "sem_dados" for l in linhas),
            "totais": {"caixas": round(tot_cx, 2), "peso_kg": round(tot_peso, 2), "cubagem_m3": round(tot_m3, 4)},
        }
    finally:
        conn.close()


@router.post("/{id}/volumes")
def lancar_volume(id: int, v: VolumeIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        _acesso_pedido_cotacao(conn, id, current_user, editar=True)
        if (v.qtd_caixas or 0) <= 0:
            raise HTTPException(400, "Informe a quantidade de caixas.")
        if (v.comprimento or 0) <= 0 or (v.largura or 0) <= 0 or (v.altura or 0) <= 0:
            raise HTTPException(400, "Informe comprimento, largura e altura da caixa.")
        if (v.peso_caixa or 0) <= 0:
            raise HTTPException(400, "Informe o peso de cada caixa.")
        if v.pedido_item_id:
            ok = conn.execute("SELECT 1 FROM pedidos_itens WHERE id=? AND pedido_id=?", (v.pedido_item_id, id)).fetchone()
            if not ok:
                raise HTTPException(400, "Item não pertence a este pedido.")
        conn.execute("""INSERT INTO pedidos_volumes (pedido_id, pedido_item_id, descricao, qtd_caixas,
                        comprimento, largura, altura, peso_caixa, usuario) VALUES (?,?,?,?,?,?,?,?,?)""",
                     (id, v.pedido_item_id or None, (v.descricao or "").strip(), v.qtd_caixas,
                      v.comprimento, v.largura, v.altura, v.peso_caixa, _nome_usuario(current_user)))
        st = conn.execute("SELECT status FROM pedidos WHERE id=?", (id,)).fetchone()["status"]
        _checar_bloqueio_revenda(conn, id, st)
        conn.commit()
        return {"mensagem": "Caixas lançadas"}
    finally:
        conn.close()


@router.delete("/{id}/volumes/{vid}")
def excluir_volume(id: int, vid: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        _acesso_pedido_cotacao(conn, id, current_user, editar=True)
        cur = conn.execute("DELETE FROM pedidos_volumes WHERE id=? AND pedido_id=?", (vid, id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Lançamento não encontrado")
        st = conn.execute("SELECT status FROM pedidos WHERE id=?", (id,)).fetchone()["status"]
        _checar_bloqueio_revenda(conn, id, st)
        conn.commit()
        return {"mensagem": "Lançamento excluído"}
    finally:
        conn.close()


@router.post("/{id}/definir-envio")
def definir_envio(id: int, body: DefinirEnvioIn, current_user: dict = Depends(get_current_user)):
    """Vendedor informa como o pedido produzido vai sair:
    - transportadora + frete combinado → Aguardando NF (entra na fila da Expedição);
    - retirada pelo cliente → Aguardando retirada;
    - voltar → Produzido (desfaz a escolha enquanto a Expedição não concluiu)."""
    conn = get_conn()
    try:
        ped = conn.execute("SELECT id, status, numero_pedido, vendedor_usuario_id FROM pedidos WHERE id=?", (id,)).fetchone()
        if not ped:
            raise HTTPException(404, "Pedido não encontrado")
        eh_gestor = current_user.get("role") == "gestor"
        if not eh_gestor and ped["vendedor_usuario_id"] != current_user["id"]:
            raise HTTPException(403, "Só o vendedor deste pedido (ou o Gestor) pode definir o envio.")
        if ped["status"] not in ("produzido",) + STATUS_LIBERADOS:
            if ped["status"] in STATUS_CONCLUIDOS:
                raise HTTPException(400, "Este pedido já foi concluído pela Expedição.")
            raise HTTPException(400, "O pedido ainda não foi produzido.")
        usuario = _nome_usuario(current_user)
        modo = (body.modo or "").strip().lower()
        if modo in ("transportadora", "retirada") and ped["status"] == "produzido":
            if _revenda_pendente(conn, id) > 0:
                raise HTTPException(400, "Este pedido tem itens de revenda ainda não separados. "
                                         "Ele será liberado para o frete assim que a separação for concluída.")
            if _embalagem_pendente(conn, id) > 0:
                raise HTTPException(400, "A embalagem deste pedido ainda não foi informada pelo Estoque/Expedição. "
                                         "Ele será liberado para o frete assim que as caixas forem informadas.")
        if modo == "transportadora":
            transp = (body.transportadora or "").strip()
            if not transp:
                raise HTTPException(400, "Informe a transportadora.")
            cad = conn.execute("SELECT nome FROM transportadoras WHERE nome = ? COLLATE NOCASE AND ativo = 1",
                               (transp,)).fetchone()
            if not cad:
                raise HTTPException(400, "Escolha uma transportadora cadastrada.")
            transp = cad["nome"]
            conn.execute("""UPDATE pedidos SET status='aguardando_nf', transportadora=?, frete=?,
                            previsao_entrega=?, retirada_prevista=NULL, obs_vendedor=?,
                            envio_definido_em=datetime('now','localtime'), envio_definido_por=?
                            WHERE id=?""",
                         (transp, float(body.frete or 0), (body.previsao_entrega or "").strip(),
                          (body.obs_vendedor or "").strip(), usuario, id))
            novo = "aguardando_nf"
        elif modo == "retirada":
            conn.execute("""UPDATE pedidos SET status='aguardando_retirada', transportadora=NULL, frete=0,
                            previsao_entrega=NULL, retirada_prevista=?, obs_vendedor=?,
                            envio_definido_em=datetime('now','localtime'), envio_definido_por=?
                            WHERE id=?""",
                         ((body.retirada_prevista or "").strip() or None, (body.obs_vendedor or "").strip(), usuario, id))
            novo = "aguardando_retirada"
        elif modo == "voltar":
            conn.execute("""UPDATE pedidos SET status='produzido', transportadora=NULL, frete=0,
                            previsao_entrega=NULL, retirada_prevista=NULL,
                            envio_definido_em=NULL, envio_definido_por=NULL WHERE id=?""", (id,))
            novo = "produzido"
        else:
            raise HTTPException(400, "Modo inválido. Use 'transportadora', 'retirada' ou 'voltar'.")
        _marcar_usuario_hist(conn, id, current_user)
        conn.commit()
        msgs = {"aguardando_nf": "Enviado para a Expedição (aguardando NF)",
                "aguardando_retirada": "Enviado para a Expedição (aguardando retirada)",
                "produzido": "Pedido voltou para aguardando vendedor"}
        return {"mensagem": msgs[novo], "status": novo}
    finally:
        conn.close()


@router.post("/{id}/retirar")
def registrar_retirada(id: int, body: RetiradaIn, current_user: dict = Depends(get_current_user)):
    """Expedição lança a NF e conclui a retirada pelo cliente."""
    exigir_permissao("expedicao", "despachar", current_user)
    conn = get_conn()
    try:
        ped = conn.execute("SELECT id, status FROM pedidos WHERE id=?", (id,)).fetchone()
        if not ped:
            raise HTTPException(404, "Pedido não encontrado")
        permitidos = ("aguardando_retirada",)
        if current_user.get("role") == "gestor":
            permitidos = permitidos + ("produzido",)
        if ped["status"] not in permitidos:
            raise HTTPException(400, "Este pedido não está aguardando retirada.")
        if not (body.nota_fiscal or "").strip():
            raise HTTPException(400, "Informe o número da nota fiscal.")
        pend = _revenda_pendente(conn, id)
        if pend > 0:
            raise HTTPException(400, f"Ha {pend} item(ns) de revenda/tampa pendente(s) de separacao. Separe antes de liberar a retirada.")
        data_ret = (body.data_retirada or "").strip() or datetime.datetime.now().strftime("%Y-%m-%d")
        conn.execute("""UPDATE pedidos SET status='retirado', nota_fiscal=?, volumes=?, obs_envio=?,
                        data_despacho=?, transportadora=COALESCE(NULLIF(transportadora,''),'Retirada pelo cliente'),
                        concluido_por=? WHERE id=?""",
                     (body.nota_fiscal.strip(), int(body.volumes or 0), (body.obs or "").strip(),
                      data_ret, _nome_usuario(current_user), id))
        _marcar_usuario_hist(conn, id, current_user)
        conn.commit()
        return {"mensagem": "Retirada registrada", "status": "retirado"}
    finally:
        conn.close()


@router.get("/alertas/resumo")
def alertas_pedidos():
    conn = get_conn()
    # Mesma regra do card "Pedidos Críticos" do Dashboard: um pedido já
    # produzido ou enviado só conta como vencido/urgente se ainda tiver
    # item de revenda (tampa etc.) pendente de separação. Sem isso, esse
    # badge (menu lateral) e o banner da Fila de Produção ficavam contando
    # pedidos que na prática não têm mais nada pendente.
    filtro_produzido_enviado = """
        AND (
            p.status NOT IN ('produzido','aguardando_nf','aguardando_retirada','enviado','retirado')
            OR EXISTS (
                SELECT 1 FROM pedidos_itens pi
                JOIN estoque_produtos ep ON pi.produto_id = ep.id
                JOIN estoque_categorias ec ON ep.categoria_id = ec.id
                WHERE pi.pedido_id = p.id AND ec.tipo = 'revenda'
                  AND pi.quantidade > pi.qtd_produzida
            )
        )
    """
    vencidos = conn.execute(f"""
        SELECT COUNT(*) FROM pedidos p
        WHERE p.status NOT IN ('entregue')
        AND julianday(p.prazo_entrega) < julianday('now')
        {filtro_produzido_enviado}
    """).fetchone()[0]
    urgentes = conn.execute(f"""
        SELECT COUNT(*) FROM pedidos p
        WHERE p.status NOT IN ('entregue')
        AND julianday(p.prazo_entrega) - julianday('now') BETWEEN 0 AND 3
        {filtro_produzido_enviado}
    """).fetchone()[0]
    em_aberto = conn.execute("""
        SELECT COUNT(*) FROM pedidos WHERE status = 'aberto'
    """).fetchone()[0]
    rows = conn.execute(f"""
        SELECT p.numero_pedido, c.razao_social as cliente,
               p.prazo_entrega, p.status,
               CAST(julianday(p.prazo_entrega) - julianday('now') AS INTEGER) as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.status NOT IN ('entregue')
        AND julianday(p.prazo_entrega) - julianday('now') <= 3
        {filtro_produzido_enviado}
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
        LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
        WHERE p.status NOT IN ('produzido', 'aguardando_nf', 'aguardando_retirada', 'enviado', 'retirado', 'entregue')
          AND (ec.tipo IS NULL OR ec.tipo != 'revenda')
          AND p.id IN (
              SELECT i2.pedido_id
              FROM pedidos_itens i2
              LEFT JOIN estoque_produtos ep2 ON i2.produto_id = ep2.id
              LEFT JOIN estoque_categorias ec2 ON ep2.categoria_id = ec2.id
              WHERE (ec2.tipo IS NULL OR ec2.tipo != 'revenda')
              GROUP BY i2.pedido_id
              HAVING COUNT(*) > COUNT(CASE WHEN i2.status IN ('produzido','entregue')
                                           OR (i2.qtd_produzida >= i2.quantidade AND i2.quantidade > 0)
                                          THEN 1 END)
          )
    """
    params = []
    if status:
        query += " AND i.status = ?"
        params.append(status)
    query += " ORDER BY p.prazo_entrega ASC, i.id ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/programar-separacao")
def programar_separacao(body: ProgramarSeparacaoIn, current_user: dict = Depends(get_current_user)):
    """Cria entradas de programação (data prevista) para os itens informados,
    permitindo que o estoque antecipe a separação. Não mexe em máquina,
    colaborador nem em producao_diaria — é só um aviso antecipado.
    Bloqueia duplicidade: item que já está com separação pendente não pode
    ser reprogramado até ser marcado como separado."""
    if not body.itens_ids:
        raise HTTPException(400, "Informe ao menos um item")
    hoje = datetime.date.today().isoformat()
    if (body.data_programada or "") < hoje:
        raise HTTPException(400, "A data programada não pode ser no passado")
    conn = get_conn()
    cur = conn.cursor()
    criados = 0
    duplicados = []
    usuario = current_user.get("nome") or current_user.get("username") or "sistema"
    for item_id in body.itens_ids:
        item = cur.execute("SELECT id, quantidade, descricao, status_separacao FROM pedidos_itens WHERE id=?", (item_id,)).fetchone()
        if not item:
            continue
        if item["status_separacao"] == "pendente":
            duplicados.append({"id": item_id, "descricao": item["descricao"]})
            continue
        cur.execute("""INSERT INTO producao_programada (pedido_item_id, data_programada, quantidade_programada)
                       VALUES (?, ?, ?)""", (item_id, body.data_programada, item["quantidade"]))
        cur.execute("UPDATE pedidos_itens SET status_separacao='pendente' WHERE id=?", (item_id,))
        cur.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                       VALUES (?, 'programar_separacao', 'pedidos_itens', ?, ?, ?, ?)""",
                    (usuario, item_id, f"Item '{item['descricao']}' programado para {body.data_programada}",
                     item["status_separacao"] or "", "pendente"))
        criados += 1
    conn.commit()
    conn.close()
    if criados == 0 and duplicados:
        raise HTTPException(409, "Todos os itens selecionados já estão programados, aguardando separação")
    return {
        "mensagem": "Programação enviada para separação",
        "itens_programados": criados,
        "itens_duplicados": duplicados,
    }

@router.get("/separacao")
def listar_separacao(incluir_separados: bool = False):
    """Lista de itens programados para o estoque, ordenada pela data programada
    mais próxima. Por padrão só mostra o que ainda está pendente de separação."""
    conn = get_conn()
    query = """
        SELECT pp.id as programacao_id, pp.data_programada, pp.quantidade_programada,
               i.id as item_id, i.descricao, i.quantidade, i.status_separacao,
               p.id as pedido_id, p.numero_pedido,
               c.razao_social as cliente_nome
        FROM producao_programada pp
        JOIN pedidos_itens i ON i.id = pp.pedido_item_id
        JOIN pedidos p ON p.id = i.pedido_id
        JOIN pedidos_clientes c ON c.id = p.cliente_id
    """
    if not incluir_separados:
        query += " WHERE i.status_separacao != 'separado' OR i.status_separacao IS NULL"
    query += " ORDER BY pp.data_programada ASC, pp.id ASC"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.delete("/itens/{id}/programacao")
def cancelar_programacao_item(id: int, current_user: dict = Depends(get_current_user)):
    """Cancela a programação de separação de um item (uso para corrigir testes
    ou desfazer um envio por engano). Remove os registros de producao_programada
    e volta o item ao estado 'nunca programado'. Não mexe em estoque nem em
    producao_diaria — o pedido/item em si não é afetado."""
    conn = get_conn()
    item = conn.execute("SELECT id, descricao, status_separacao FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item do pedido não encontrado")
    usuario = current_user.get("nome") or current_user.get("username") or "sistema"
    conn.execute("DELETE FROM producao_programada WHERE pedido_item_id=?", (id,))
    conn.execute("UPDATE pedidos_itens SET status_separacao=NULL WHERE id=?", (id,))
    conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                   VALUES (?, 'cancelar_programacao', 'pedidos_itens', ?, ?, ?, ?)""",
                (usuario, id, f"Programação cancelada para o item '{item['descricao']}'", item["status_separacao"] or "", ""))
    conn.commit()
    conn.close()
    return {"mensagem": "Programação cancelada"}

@router.post("/itens/{id}/marcar-separado")
def marcar_item_separado(id: int, body: MarcarSeparadoIn, current_user: dict = Depends(get_current_user)):
    """Marca (ou desfaz) a separação de um item de produção para o estoque.
    Não gera movimentação de estoque — a baixa continua acontecendo somente
    no lançamento da produção diária."""
    conn = get_conn()
    item = conn.execute("SELECT id, descricao, status_separacao FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item do pedido não encontrado")
    novo_status = "separado" if body.marcar else "pendente"
    usuario = current_user.get("nome") or current_user.get("username") or "sistema"
    conn.execute("UPDATE pedidos_itens SET status_separacao=? WHERE id=?", (novo_status, id))
    conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                   VALUES (?, ?, 'pedidos_itens', ?, ?, ?, ?)""",
                (usuario, "marcar_separado" if body.marcar else "desfazer_separado", id,
                 f"Item '{item['descricao']}'", item["status_separacao"] or "", novo_status))
    conn.commit()
    conn.close()
    return {"mensagem": "Item marcado como separado" if body.marcar else "Marcação desfeita", "status_separacao": novo_status}

@router.get("/{id}")
def buscar_pedido(id: int, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    pedido = conn.execute("""
        SELECT p.*, c.razao_social as cliente_nome, c.nome_fantasia,
               c.cnpj as cliente_cnpj, c.telefone as cliente_telefone,
               c.cep as cliente_cep, c.logradouro as cliente_logradouro,
               c.numero as cliente_numero, c.complemento as cliente_complemento,
               c.bairro as cliente_bairro, c.cidade as cliente_cidade, c.uf as cliente_uf,
               c.email as cliente_email, COALESCE(c.estoque_programado,0) as cliente_estoque_programado,
               julianday(p.prazo_entrega) - julianday('now') as dias_restantes
        FROM pedidos p
        JOIN pedidos_clientes c ON p.cliente_id = c.id
        WHERE p.id=?
    """, (id,)).fetchone()
    if not pedido:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    if current_user.get("role") == "comercial" and pedido["vendedor_usuario_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(403, "Este pedido não é seu.")
    itens = conn.execute("""
        SELECT i.*, ep.nome as produto_nome, ep.codigo as produto_codigo, ec.tipo as categoria_tipo
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON i.produto_id = ep.id
        LEFT JOIN estoque_categorias ec ON ep.categoria_id = ec.id
        WHERE i.pedido_id=?
        ORDER BY i.id
    """, (id,)).fetchall()
    parcelas = conn.execute("""
        SELECT id, forma_pagamento, vencimento, valor
        FROM pedidos_parcelas
        WHERE pedido_id = ?
        ORDER BY id
    """, (id,)).fetchall()
    conn.close()
    result = dict(pedido)
    result["itens"] = [dict(i) for i in itens]
    result["parcelas"] = [dict(pa) for pa in parcelas]
    return result

_RE_TAMANHO_COPO = _re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|oz)\b", _re.IGNORECASE)

def _tamanho_do_nome(nome: str) -> str:
    """Extrai o tamanho do copo (ex.: '300 ml') do nome do produto."""
    m = _RE_TAMANHO_COPO.search(nome or "")
    return f"{m.group(1)} {m.group(2).lower()}" if m else ""

@router.get("/{id}/historico-producao")
def historico_producao_pedido(id: int):
    """Lançamentos de produção vinculados a este pedido (pelo número), com
    operador, máquina, data e PRODUTO (nome, marca e tamanho extraído do nome) —
    mais um resumo por produto (pedido x produzido x falta) para conferência.
    Lançamentos multi-produto (producao_diaria_itens) viram uma linha por produto."""
    conn = get_conn()
    pedido = conn.execute("SELECT numero_pedido FROM pedidos WHERE id=?", (id,)).fetchone()
    if not pedido:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    lancamentos = conn.execute("""
        SELECT p.id, p.data,
               COALESCE(pdi.produto_estoque_id, p.produto_estoque_id) as produto_id,
               CASE WHEN pdi.id IS NULL THEN p.producao ELSE pdi.quantidade END as producao,
               CASE WHEN pdi.id IS NULL THEN p.perda_quantidade ELSE pdi.perda_quantidade END as perda_quantidade,
               CASE WHEN pdi.id IS NULL THEN p.sobra_quantidade ELSE pdi.sobra_quantidade END as sobra_quantidade,
               c.nome as colaborador_nome, m.nome as maquina_nome,
               ep.nome as produto_nome, ep.marca as produto_marca
        FROM producao_diaria p
        JOIN colaboradores c ON c.id = p.colaborador_id
        JOIN maquinas m ON m.id = p.maquina_id
        LEFT JOIN producao_diaria_itens pdi ON pdi.producao_diaria_id = p.id
        LEFT JOIN estoque_produtos ep ON ep.id = COALESCE(pdi.produto_estoque_id, p.produto_estoque_id)
        WHERE p.pedido_numero = ?
        ORDER BY p.data ASC, p.id ASC, pdi.id ASC
    """, (pedido["numero_pedido"],)).fetchall()
    itens = conn.execute("""
        SELECT i.produto_id, SUM(i.quantidade) as pedido, ep.nome as produto_nome, ep.marca as produto_marca
        FROM pedidos_itens i
        LEFT JOIN estoque_produtos ep ON ep.id = i.produto_id
        WHERE i.pedido_id = ?
        GROUP BY i.produto_id
        ORDER BY MIN(i.id)
    """, (id,)).fetchall()
    conn.close()

    resultado = []
    for l in lancamentos:
        d = dict(l)
        d["produto_tamanho"] = _tamanho_do_nome(d.get("produto_nome"))
        resultado.append(d)

    # Resumo por produto: o que foi pedido x o que já foi produzido (e perdido)
    resumo = {}
    for it in itens:
        resumo[it["produto_id"]] = {
            "produto_id": it["produto_id"], "produto_nome": it["produto_nome"],
            "produto_marca": it["produto_marca"], "produto_tamanho": _tamanho_do_nome(it["produto_nome"]),
            "pedido": it["pedido"] or 0, "produzido": 0, "perda": 0, "sobra": 0, "fora_do_pedido": False,
        }
    for l in resultado:
        r = resumo.get(l["produto_id"])
        if r is None:  # produziu um produto que não está no pedido: destaca pra conferência
            r = resumo[l["produto_id"]] = {
                "produto_id": l["produto_id"], "produto_nome": l["produto_nome"],
                "produto_marca": l["produto_marca"], "produto_tamanho": l["produto_tamanho"],
                "pedido": 0, "produzido": 0, "perda": 0, "sobra": 0, "fora_do_pedido": True,
            }
        r["produzido"] += l["producao"] or 0
        r["perda"] += l["perda_quantidade"] or 0
        r["sobra"] += l["sobra_quantidade"] or 0
    resumo_lista = []
    for r in resumo.values():
        r["falta"] = max((r["pedido"] or 0) - r["produzido"], 0)
        r["excedente"] = max(r["produzido"] - (r["pedido"] or 0), 0) if r["pedido"] else 0
        resumo_lista.append(r)

    total_produzido = sum((l["producao"] or 0) for l in resultado)
    return {"numero_pedido": pedido["numero_pedido"], "lancamentos": resultado,
            "resumo": resumo_lista, "total_produzido": total_produzido}

@router.post("/")
def criar_pedido(p: PedidoIn, current_user: dict = Depends(get_current_user)):
    conn = get_conn()
    cur = conn.cursor()
    if not p.numero_pedido or not str(p.numero_pedido).strip():
        last = cur.execute("SELECT numero_pedido FROM pedidos WHERE numero_pedido GLOB '[0-9]*' ORDER BY CAST(numero_pedido AS INTEGER) DESC LIMIT 1").fetchone()
        if last and last[0].isdigit():
            p.numero_pedido = str(int(last[0]) + 1)
        else:
            p.numero_pedido = "1"
    dup = cur.execute("SELECT id FROM pedidos WHERE numero_pedido=?", (str(p.numero_pedido),)).fetchone()
    if dup:
        conn.close()
        raise HTTPException(400, f"Pedido número {p.numero_pedido} já existe (pedido #{dup['id']}).")
    cur.execute("""INSERT INTO pedidos
        (numero_pedido, cliente_id, prazo_entrega, vendedor, observacoes, acrescimo, frete, desconto_global, status, precisa_pintura)
        VALUES (?,?,?,?,?,?,?,?,'aberto',?)""",
        (p.numero_pedido, p.cliente_id, (p.prazo_entrega or ""), p.vendedor, p.observacoes, p.acrescimo or 0, p.frete or 0, p.desconto_global or 0, 1 if p.precisa_pintura else 0))
    pedido_id = cur.lastrowid
    if not vincular_pedido(conn, pedido_id) and current_user.get("role") == "comercial":
        # Vendedor cadastrando/importando: sem vendedor reconhecido, o pedido fica com ele
        cur.execute("UPDATE pedidos SET vendedor_usuario_id=? WHERE id=?", (current_user["id"], pedido_id))
    for item in p.itens:
        vunit = item.valor_unitario or 0.0
        if vunit == 0.0 and item.produto_id:
            p_info = cur.execute("SELECT preco FROM estoque_produtos WHERE id=?", (item.produto_id,)).fetchone()
            if p_info:
                vunit = p_info["preco"] or 0.0
        cur.execute("""INSERT INTO pedidos_itens
            (pedido_id, produto_id, descricao, quantidade, unidade, valor_unitario, desconto, insumo_vinculado_id, qtd_produzida, status)
            VALUES (?,?,?,?,?,?,?,?,0,'aberto')""",
            (pedido_id, item.produto_id, item.descricao, item.quantidade, item.unidade, vunit, item.desconto or 0, item.insumo_vinculado_id))
    if p.parcelas:
        for parc in p.parcelas:
            cur.execute("""INSERT INTO pedidos_parcelas
                (pedido_id, forma_pagamento, vencimento, valor)
                VALUES (?,?,?,?)""",
                (pedido_id, (parc.forma_pagamento or ""), (parc.vencimento or ""), parc.valor or 0))
    _auto_vincular_itens(conn)
    alertas = _alertas_estoque_para_pedidos(cur, [pedido_id])
    conn.commit()
    conn.close()
    return {"id": pedido_id, "mensagem": "Pedido criado", "alertas_estoque": alertas}

@router.put("/{id}")
def atualizar_pedido(id: int, p: PedidoIn):
    conn = get_conn()
    cur = conn.cursor()
    atual = cur.execute("SELECT * FROM pedidos WHERE id=?", (id,)).fetchone()
    if not atual:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    numero_antigo = atual["numero_pedido"]
    if not p.numero_pedido or not str(p.numero_pedido).strip():
        last = cur.execute("SELECT numero_pedido FROM pedidos WHERE numero_pedido GLOB '[0-9]*' AND id<>? ORDER BY CAST(numero_pedido AS INTEGER) DESC LIMIT 1", (id,)).fetchone()
        if last and last[0].isdigit():
            p.numero_pedido = str(int(last[0]) + 1)
        else:
            p.numero_pedido = "1"
    p.numero_pedido = str(p.numero_pedido).strip()
    dup = cur.execute("SELECT id FROM pedidos WHERE numero_pedido=? AND id<>?", (p.numero_pedido, id)).fetchone()
    if dup:
        conn.close()
        raise HTTPException(400, f"Pedido número {p.numero_pedido} já existe (pedido #{dup['id']}).")

    # Campos financeiros não enviados (None) mantêm o valor atual — antes eram zerados.
    acrescimo = atual["acrescimo"] if p.acrescimo is None else p.acrescimo
    frete = atual["frete"] if p.frete is None else p.frete
    desconto_global = atual["desconto_global"] if p.desconto_global is None else p.desconto_global
    cur.execute("""UPDATE pedidos SET
        numero_pedido=?, cliente_id=?, prazo_entrega=?, vendedor=?, observacoes=?, acrescimo=?, frete=?, desconto_global=?, precisa_pintura=?
        WHERE id=?""",
        (p.numero_pedido, p.cliente_id, (p.prazo_entrega or ""), p.vendedor, p.observacoes, acrescimo or 0, frete or 0, desconto_global or 0, 1 if p.precisa_pintura else 0, id))
    # Vendedor: se o nome mudou, refaz o vínculo; senão mantém (inclusive atribuição manual)
    if (atual["vendedor"] or "").strip() != (p.vendedor or "").strip():
        vincular_pedido(conn, id, forcar=True)
    else:
        vincular_pedido(conn, id)

    # Produção, pintura e movimentações de estoque se ligam ao pedido pelo NÚMERO:
    # se o número mudou, migra os vínculos para não deixar histórico órfão.
    if numero_antigo and numero_antigo != p.numero_pedido:
        for tabela in ("producao_diaria", "producao_pintura", "estoque_movimentacoes"):
            cur.execute(f"UPDATE {tabela} SET pedido_numero=? WHERE pedido_numero=?", (p.numero_pedido, numero_antigo))

    # Itens: atualiza os existentes NO LUGAR (preserva id, status, qtd_produzida,
    # status_separacao e programação de separação), insere os novos e remove só os
    # que saíram do pedido. Antes tudo era apagado e recriado.
    existentes = {r["id"]: r for r in cur.execute("SELECT * FROM pedidos_itens WHERE pedido_id=?", (id,)).fetchall()}
    usados = set()

    def _achar_existente(item):
        if item.id and item.id in existentes and item.id not in usados:
            return item.id
        # Cliente que não enviou o id: casa por descrição, na ordem (aguenta itens repetidos)
        chave = (item.descricao or "").strip().upper()
        for eid, r in existentes.items():
            if eid not in usados and (r["descricao"] or "").strip().upper() == chave:
                return eid
        return None

    for item in p.itens:
        eid = _achar_existente(item)
        vunit = item.valor_unitario or 0.0
        if eid is not None:
            usados.add(eid)
            if vunit == 0.0:
                vunit = existentes[eid]["valor_unitario"] or 0.0
        if vunit == 0.0 and item.produto_id:
            p_info = cur.execute("SELECT preco FROM estoque_produtos WHERE id=?", (item.produto_id,)).fetchone()
            if p_info:
                vunit = p_info["preco"] or 0.0
        if eid is not None:
            cur.execute("""UPDATE pedidos_itens SET
                produto_id=?, descricao=?, quantidade=?, unidade=?, valor_unitario=?, desconto=?, insumo_vinculado_id=?
                WHERE id=?""",
                (item.produto_id, item.descricao, item.quantidade, item.unidade, vunit, item.desconto or 0, item.insumo_vinculado_id, eid))
        else:
            cur.execute("""INSERT INTO pedidos_itens
                (pedido_id, produto_id, descricao, quantidade, unidade, valor_unitario, desconto, insumo_vinculado_id, qtd_produzida, status)
                VALUES (?,?,?,?,?,?,?,?,0,'aberto')""",
                (id, item.produto_id, item.descricao, item.quantidade, item.unidade, vunit, item.desconto or 0, item.insumo_vinculado_id))

    removidos = [eid for eid in existentes if eid not in usados]
    for eid in removidos:
        # programação de separação aponta pro item (FK sem CASCADE): sai junto com ele
        cur.execute("DELETE FROM producao_programada WHERE pedido_item_id=?", (eid,))
        cur.execute("DELETE FROM pedidos_itens WHERE id=?", (eid,))

    # Parcelas: só substitui se vieram no payload.
    if p.parcelas is not None:
        cur.execute("DELETE FROM pedidos_parcelas WHERE pedido_id=?", (id,))
        for parc in p.parcelas:
            cur.execute("""INSERT INTO pedidos_parcelas
                (pedido_id, forma_pagamento, vencimento, valor)
                VALUES (?,?,?,?)""",
                (id, (parc.forma_pagamento or ""), (parc.vencimento or ""), parc.valor or 0))

    _auto_vincular_itens(conn)
    _recalc_status_pedido(cur, id)
    conn.commit()
    conn.close()
    return {"mensagem": "Pedido atualizado"}

class DespachoIn(BaseModel):
    transportadora: Optional[str] = ""
    nota_fiscal: Optional[str] = ""
    rastreio: Optional[str] = ""
    volumes: Optional[int] = 0
    previsao_entrega: Optional[str] = ""
    frete: Optional[float] = 0
    frete_pago: Optional[float] = 0
    obs_envio: Optional[str] = ""
    data_despacho: Optional[str] = ""
    # Endereço de entrega deste pedido (None = não mexer)
    entrega_cep: Optional[str] = None
    entrega_logradouro: Optional[str] = None
    entrega_numero: Optional[str] = None
    entrega_complemento: Optional[str] = None
    entrega_bairro: Optional[str] = None
    entrega_cidade: Optional[str] = None
    entrega_uf: Optional[str] = None
    atualizar_cadastro_cliente: Optional[bool] = False

class EntregaIn(BaseModel):
    data_entrega: Optional[str] = ""

@router.post("/{id}/despachar")
def despachar_pedido(id: int, body: DespachoIn, current_user: dict = Depends(get_current_user)):
    """Expedição lança a NF e conclui o envio por transportadora.
    Só vale para pedido liberado pelo vendedor (Aguardando NF) ou para corrigir
    um já enviado. O Gestor pode despachar direto um Produzido, como exceção."""
    exigir_permissao("expedicao", "despachar", current_user)
    data_desp = (body.data_despacho or "").strip() or datetime.datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    ped = conn.execute("SELECT id, status FROM pedidos WHERE id=?", (id,)).fetchone()
    if not ped:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    permitidos = ("aguardando_nf", "enviado")
    if current_user.get("role") == "gestor":
        permitidos = permitidos + ("produzido",)
    if ped["status"] not in permitidos:
        conn.close()
        if ped["status"] == "produzido":
            raise HTTPException(400, "Este pedido ainda aguarda o vendedor informar a transportadora e o frete.")
        raise HTTPException(400, "Este pedido não está liberado para despacho.")
    if not (body.nota_fiscal or "").strip():
        conn.close()
        raise HTTPException(400, "Informe o número da nota fiscal.")
    if not (body.transportadora or "").strip():
        conn.close()
        raise HTTPException(400, "Informe a transportadora.")
    # Bloqueia despacho se houver itens de revenda (tampas) ainda nao separados
    pend = _revenda_pendente(conn, id)
    if pend > 0:
        conn.close()
        raise HTTPException(400, f"Ha {pend} item(ns) de revenda/tampa pendente(s) de separacao. Separe antes de despachar.")
    conn.execute(
        """UPDATE pedidos SET transportadora=?, nota_fiscal=?, rastreio=?, volumes=?,
           previsao_entrega=?, frete=?, frete_pago=?, obs_envio=?, data_despacho=?, status='enviado'
           WHERE id=?""",
        ((body.transportadora or "").strip(), (body.nota_fiscal or "").strip(),
         (body.rastreio or "").strip(), int(body.volumes or 0),
         (body.previsao_entrega or "").strip(), float(body.frete or 0), float(body.frete_pago or 0),
         (body.obs_envio or "").strip(), data_desp, id))
    if ped["status"] != "enviado":
        conn.execute("UPDATE pedidos SET concluido_por=? WHERE id=?", (_nome_usuario(current_user), id))
        _marcar_usuario_hist(conn, id, current_user)

    campos_end = ("cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf")
    if any(getattr(body, "entrega_" + c) is not None for c in campos_end):
        end = {c: (getattr(body, "entrega_" + c) or "").strip() for c in campos_end}
        end["cep"] = "".join(ch for ch in end["cep"] if ch.isdigit())
        end["uf"] = end["uf"].upper()[:2]
        conn.execute("""UPDATE pedidos SET entrega_cep=?, entrega_logradouro=?, entrega_numero=?,
                        entrega_complemento=?, entrega_bairro=?, entrega_cidade=?, entrega_uf=? WHERE id=?""",
                     (end["cep"], end["logradouro"], end["numero"], end["complemento"],
                      end["bairro"], end["cidade"], end["uf"], id))
        if body.atualizar_cadastro_cliente:
            ped = conn.execute("SELECT cliente_id, numero_pedido FROM pedidos WHERE id=?", (id,)).fetchone()
            if ped:
                conn.execute("""UPDATE pedidos_clientes SET cep=?, logradouro=?, numero=?, complemento=?,
                                bairro=?, cidade=?, uf=? WHERE id=?""",
                             (end["cep"], end["logradouro"], end["numero"], end["complemento"],
                              end["bairro"], end["cidade"], end["uf"], ped["cliente_id"]))
                usuario = current_user.get("nome") or current_user.get("username") or "sistema"
                conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                               VALUES (?, 'atualizar_endereco', 'pedidos_clientes', ?, ?, '', ?)""",
                             (usuario, ped["cliente_id"],
                              f"Endereço do cliente atualizado no despacho do pedido '{ped['numero_pedido']}'",
                              f"{end['logradouro']}, {end['numero']} - {end['bairro']} - {end['cidade']}/{end['uf']} - CEP {end['cep']}"))
    conn.commit(); conn.close()
    return {"mensagem": "Pedido despachado", "status": "enviado"}

@router.post("/{id}/confirmar-entrega")
def confirmar_entrega(id: int, body: EntregaIn, current_user: dict = Depends(get_current_user)):
    exigir_permissao("expedicao", "despachar", current_user)
    data_ent = (body.data_entrega or "").strip() or datetime.datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    ped = conn.execute("SELECT status FROM pedidos WHERE id=?", (id,)).fetchone()
    if not ped:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    if ped["status"] != "enviado" and current_user.get("role") != "gestor":
        conn.close()
        raise HTTPException(400, "Só pedidos enviados podem ser confirmados como entregues.")
    conn.execute("UPDATE pedidos SET status='entregue', data_entrega=? WHERE id=?", (data_ent, id))
    _marcar_usuario_hist(conn, id, current_user)
    conn.execute("UPDATE pedidos_itens SET status='entregue' WHERE pedido_id=?", (id,))
    conn.commit(); conn.close()
    return {"mensagem": "Entrega confirmada", "status": "entregue"}

@router.post("/{id}/desfazer-despacho")
def desfazer_despacho(id: int, current_user: dict = Depends(get_current_user)):
    """Desfaz a conclusão feita pela Expedição:
    - enviado  → volta para Aguardando NF (mantém transportadora/frete do vendedor);
    - retirado → volta para Aguardando retirada.
    Pedidos despachados antes do fluxo novo (sem frete definido pelo vendedor)
    voltam para Produzido, como era antes."""
    exigir_permissao("expedicao", "desfazer", current_user)
    conn = get_conn()
    ped = conn.execute("SELECT id, status, numero_pedido, envio_definido_em FROM pedidos WHERE id=?", (id,)).fetchone()
    if not ped:
        conn.close()
        raise HTTPException(404, "Pedido não encontrado")
    if ped["status"] not in ("enviado", "retirado"):
        conn.close()
        raise HTTPException(400, "Só é possível desfazer pedidos enviados ou retirados.")
    if ped["status"] == "retirado":
        novo = "aguardando_retirada"
        conn.execute("""UPDATE pedidos SET status=?, nota_fiscal=NULL, volumes=NULL, obs_envio=NULL,
                        data_despacho=NULL, concluido_por=NULL WHERE id=?""", (novo, id))
    elif ped["envio_definido_em"]:
        novo = "aguardando_nf"
        conn.execute("""UPDATE pedidos SET status=?, nota_fiscal=NULL, rastreio=NULL, volumes=NULL,
                        frete_pago=0, obs_envio=NULL, data_despacho=NULL, concluido_por=NULL WHERE id=?""", (novo, id))
    else:
        novo = "produzido"
        conn.execute("""UPDATE pedidos SET status=?, transportadora=NULL, nota_fiscal=NULL,
                        rastreio=NULL, volumes=NULL, frete=0, frete_pago=0, obs_envio=NULL,
                        data_despacho=NULL, previsao_entrega=NULL, concluido_por=NULL WHERE id=?""", (novo, id))
    _marcar_usuario_hist(conn, id, current_user)
    conn.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                   VALUES (?, 'desfazer_despacho', 'pedidos', ?, ?, ?, ?)""",
                (_nome_usuario(current_user), id, f"Conclusão desfeita do pedido '{ped['numero_pedido']}'", ped["status"], novo))
    conn.commit()
    conn.close()
    return {"mensagem": "Desfeito — o pedido voltou para a fila da Expedição", "status": novo}

@router.put("/{id}/status")
def atualizar_status_pedido(id: int, body: StatusItemIn, current_user: dict = Depends(get_current_user)):
    validos = STATUS_VALIDOS_PEDIDO
    if body.status not in validos:
        raise HTTPException(400, f"Status inválido. Use: {validos}")
    if body.status in STATUS_LIBERADOS + STATUS_CONCLUIDOS:
        exigir_gestor(current_user)
    conn = get_conn()
    conn.execute("UPDATE pedidos SET status=? WHERE id=?", (body.status, id))
    _marcar_usuario_hist(conn, id, current_user)
    conn.commit()
    conn.close()
    return {"mensagem": "Status atualizado"}

@router.delete("/{id}")
def deletar_pedido(id: int, current_user = Depends(get_current_user)):
    conn = get_conn()
    try:
        # 1. Verificar permissão
        if not verificar_permissao("pedidos", "deletar", current_user):
            raise HTTPException(403, "Você não tem permissão para excluir pedidos.")

        cur = conn.cursor()
        
        # 2. Buscar o número do pedido para o histórico do estoque
        ped = cur.execute("SELECT numero_pedido, status, vendedor_usuario_id FROM pedidos WHERE id=?", (id,)).fetchone()
        if not ped:
            raise HTTPException(404, "Pedido não encontrado")
        numero_pedido = ped["numero_pedido"]

        # Vendedor (Comercial): só o próprio pedido, ainda Aberto e sem produção lançada.
        if current_user.get("role") == "comercial":
            if ped["vendedor_usuario_id"] != current_user["id"]:
                raise HTTPException(403, "Este pedido não é seu.")
            eh_entrega_estoque = cur.execute("SELECT COALESCE(origem_estoque_cliente,0) FROM pedidos WHERE id=?", (id,)).fetchone()[0]
            if eh_entrega_estoque:
                if ped["status"] != "produzido":
                    raise HTTPException(400, "Esta entrega já foi liberada para a Expedição. Volte o envio antes de excluir.")
            elif (ped["status"] or "aberto") != "aberto":
                raise HTTPException(400, "Só é possível excluir pedidos ainda em aberto. Peça ao Gestor.")
            if cur.execute("SELECT 1 FROM producao_diaria WHERE pedido_numero=? LIMIT 1", (numero_pedido,)).fetchone() \
               or cur.execute("SELECT 1 FROM pedidos_itens WHERE pedido_id=? AND COALESCE(qtd_produzida,0) > 0 LIMIT 1", (id,)).fetchone():
                raise HTTPException(400, "Este pedido já tem produção lançada. Peça ao Gestor para excluir.")

        # 3. Excluir lançamentos de produção vinculados a este pedido (pelo número),
        # revertendo a baixa/sobra/perda de estoque de cada um. Sem isso, o produto
        # ficava "preso" fora do estoque e o operador precisava caçar e apagar
        # cada lançamento manualmente depois de excluir o pedido.
        lancamentos = cur.execute(
            "SELECT id FROM producao_diaria WHERE pedido_numero = ?", (numero_pedido,)
        ).fetchall()
        for lanc in lancamentos:
            lanc_id = lanc["id"]
            _reverter_estoque_producao(cur, lanc_id)
            cur.execute("DELETE FROM producao_diaria_itens WHERE producao_diaria_id = ?", (lanc_id,))
            cur.execute("DELETE FROM producao_diaria WHERE id = ?", (lanc_id,))

        # 4. Buscar todos os itens do pedido que estão com status 'entregue' (separados) e possuem produto_id
        itens_com_estoque = cur.execute("""
            SELECT i.produto_id, i.quantidade, ep.nome as produto_nome
            FROM pedidos_itens i
            JOIN estoque_produtos ep ON i.produto_id = ep.id
            WHERE i.pedido_id = ? AND i.status = 'entregue'
        """, (id,)).fetchall()

        # 5. Devolver a quantidade ao estoque de cada item
        from datetime import date
        for item in itens_com_estoque:
            produto_id = item["produto_id"]
            qtd = item["quantidade"] or 0.0
            if qtd <= 0:
                continue
                
            # Obter saldo atual
            row_saldo = cur.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (produto_id,)).fetchone()
            saldo_anterior = row_saldo["quantidade"] if row_saldo else 0.0
            saldo_posterior = saldo_anterior + qtd
            
            # Registrar movimentação de entrada (estorno)
            motivo = f"Estorno exclusão pedido {numero_pedido}"
            cur.execute("""
                INSERT INTO estoque_movimentacoes
                (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (produto_id, "saida" if qtd < 0 else "entrada", abs(qtd), saldo_anterior, saldo_posterior, motivo, str(date.today())))
            
            # Atualizar saldo
            if row_saldo:
                cur.execute("""
                    UPDATE estoque_saldo 
                    SET quantidade=?, ultima_atualizacao=datetime('now') 
                    WHERE produto_id=?
                """, (saldo_posterior, produto_id))
            else:
                cur.execute("""
                    INSERT INTO estoque_saldo (produto_id, quantidade) 
                    VALUES (?, ?)
                """, (produto_id, saldo_posterior))

        # 6. Excluir o pedido e suas dependências
        cur.execute("""DELETE FROM producao_programada WHERE pedido_item_id IN
                       (SELECT id FROM pedidos_itens WHERE pedido_id=?)""", (id,))
        cur.execute("DELETE FROM pedidos_parcelas WHERE pedido_id=?", (id,))
        cur.execute("DELETE FROM pedidos_itens WHERE pedido_id=?", (id,))
        cur.execute("DELETE FROM pedidos_status_hist WHERE pedido_id=?", (id,))
        cur.execute("DELETE FROM pedidos_volumes WHERE pedido_id=?", (id,))
        # Estoque do cliente: entrega excluída devolve o saldo; pedido de origem excluído tira a entrada
        if cur.execute("SELECT 1 FROM estoque_cliente_mov WHERE pedido_id=? AND tipo='entrada' LIMIT 1", (id,)).fetchone():
            neg = cur.execute("""
                SELECT m.descricao FROM estoque_cliente_mov m
                WHERE m.cliente_id = (SELECT cliente_id FROM pedidos WHERE id=?)
                GROUP BY m.cliente_id, COALESCE(m.produto_id,0), m.descricao
                HAVING SUM(CASE WHEN m.pedido_id = ? AND m.tipo = 'entrada' THEN 0 ELSE m.quantidade END) < 0
            """, (id, id)).fetchone()
            if neg:
                raise HTTPException(400, f"Não dá para excluir: parte deste estoque ({neg['descricao']}) já foi entregue ao cliente.")
        cur.execute("DELETE FROM estoque_cliente_mov WHERE pedido_id=?", (id,))
        cur.execute("DELETE FROM pedidos WHERE id=?", (id,))
        cur.execute("""INSERT INTO auditoria (usuario, acao, entidade, entidade_id, descricao, valor_anterior, valor_novo)
                       VALUES (?, 'excluir_pedido', 'pedidos', ?, ?, ?, '')""",
                    (_nome_usuario(current_user), id, f"Pedido '{numero_pedido}' excluído", ped["status"] or ""))
        
        conn.commit()
    finally:
        conn.close()
    return {"mensagem": "Pedido removido"}


# ─── ITENS ────────────────────────────────────────────────────────────────────

@router.put("/itens/{id}/status")
def atualizar_status_item(id: int, body: StatusItemIn):
    validos = ["aberto", "em_producao", "produzido", "enviado", "entregue"]
    if body.status not in validos:
        raise HTTPException(400, f"Status inválido. Use: {validos}")
    conn = get_conn()
    cur = conn.cursor()
    
    item = cur.execute("SELECT * FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item do pedido não encontrado")
        
    pid = item["pedido_id"]
    
    # Produção parcial NÃO divide mais o item em duas linhas: a linha mantém a
    # quantidade original do pedido e só acumula qtd_produzida (o detalhe de cada
    # dia fica no histórico de produção). Dividir alterava o pedido original e as
    # linhas novas nasciam sem valor, desconto e insumo vinculado.
    # `split_if_partial` continua aceito só por compatibilidade com telas antigas.
    if body.qtd_produzida is not None:
        cur.execute("UPDATE pedidos_itens SET status=?, qtd_produzida=? WHERE id=?",
                    (body.status, body.qtd_produzida, id))
    else:
        cur.execute("UPDATE pedidos_itens SET status=? WHERE id=?", (body.status, id))

    # Recalcular status do pedido pai
    item = cur.execute("SELECT pedido_id FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if item:
        pid = item["pedido_id"]
        _recalc_status_pedido(cur, pid)

    conn.commit()
    conn.close()
    return {"mensagem": "Item atualizado"}

@router.post("/itens/{id}/separar-revenda")
def separar_revenda_item(id: int, body: SepararRevendaIn):
    """Marca um item de revenda como Separado/Entregue (ou desfaz), dando baixa
    (ou estorno) no estoque do produto vinculado. Permite saldo negativo, mas
    sinaliza falta de saldo para o frontend alertar."""
    from datetime import date
    conn = get_conn()
    cur = conn.cursor()
    item = cur.execute("SELECT * FROM pedidos_itens WHERE id=?", (id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item do pedido não encontrado")

    pid = item["pedido_id"]
    produto_id = item["produto_id"]
    qtd = item["quantidade"] or 0
    ped = cur.execute("SELECT numero_pedido FROM pedidos WHERE id=?", (pid,)).fetchone()
    numero = ped["numero_pedido"] if ped and ped["numero_pedido"] else pid

    def _mov(tipo, motivo):
        row = cur.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (produto_id,)).fetchone()
        saldo = row["quantidade"] if row else 0
        novo = saldo + qtd if tipo == "entrada" else saldo - qtd
        cur.execute("""INSERT INTO estoque_movimentacoes
                       (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, data)
                       VALUES (?,?,?,?,?,?,?)""",
                    (produto_id, tipo, qtd, saldo, novo, motivo, str(date.today())))
        if row:
            cur.execute("UPDATE estoque_saldo SET quantidade=?, ultima_atualizacao=datetime('now') WHERE produto_id=?",
                        (novo, produto_id))
        else:
            cur.execute("INSERT INTO estoque_saldo (produto_id, quantidade) VALUES (?, ?)", (produto_id, novo))
        return saldo, novo

    marcar = body.marcar
    indo_entregue = marcar and item["status"] != "entregue"
    voltando = (not marcar) and item["status"] == "entregue"

    sem_vinculo = False
    saldo_atual = None

    if indo_entregue:
        if produto_id:
            # Bloqueia de verdade: não deixa separar mais do que existe em
            # estoque (antes disso era permitido e só avisava depois — o
            # aviso passava despercebido e o saldo ficava negativo sem
            # ninguém perceber o motivo).
            saldo_row = cur.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (produto_id,)).fetchone()
            saldo_disponivel = saldo_row["quantidade"] if saldo_row else 0
            if qtd > saldo_disponivel:
                conn.close()
                raise HTTPException(400, f"Saldo insuficiente para separar este item. Precisa de {qtd:g}, mas só tem {saldo_disponivel:g} em estoque.")
            saldo, novo = _mov("saida", f"Separação pedido {numero}")
            saldo_atual = novo
        else:
            sem_vinculo = True
        cur.execute("UPDATE pedidos_itens SET status='entregue', qtd_produzida=? WHERE id=?", (qtd, id))
    elif voltando:
        if produto_id:
            saldo, novo = _mov("entrada", f"Estorno separação pedido {numero}")
            saldo_atual = novo
        cur.execute("UPDATE pedidos_itens SET status='aberto', qtd_produzida=0 WHERE id=?", (id,))
    else:
        # sem transição de estoque; apenas garante o status alvo
        if marcar:
            cur.execute("UPDATE pedidos_itens SET status='entregue', qtd_produzida=? WHERE id=?", (qtd, id))
        else:
            cur.execute("UPDATE pedidos_itens SET status='aberto', qtd_produzida=0 WHERE id=?", (id,))

    _recalc_status_pedido(cur, pid)
    conn.commit()
    conn.close()
    return {
        "mensagem": "Item separado/entregue" if marcar else "Marcação desfeita",
        "sem_vinculo": sem_vinculo,
        "saldo_atual": saldo_atual,
    }

@router.put("/itens/{id}/produto")
def vincular_produto_item(id: int, body: dict):
    conn = get_conn()
    produto_id = body.get('produto_id')
    conn.execute("UPDATE pedidos_itens SET produto_id = ? WHERE id = ?", (produto_id, id))
    conn.commit()
    conn.close()
    return {"mensagem": "Produto vinculado", "produto_id": produto_id}

@router.delete("/itens/{id}")
def deletar_item(id: int, current_user = Depends(get_current_user)):
    conn = get_conn()
    try:
        # 1. Verificar permissão para editar pedidos (excluir item é parte de editar)
        if not verificar_permissao("pedidos", "editar", current_user):
            raise HTTPException(403, "Você não tem permissão para editar pedidos.")

        cur = conn.cursor()

        # 2. Obter informações do item e do número do pedido
        item = cur.execute("""
            SELECT i.pedido_id, i.produto_id, i.quantidade, i.status, p.numero_pedido
            FROM pedidos_itens i
            JOIN pedidos p ON i.pedido_id = p.id
            WHERE i.id = ?
        """, (id,)).fetchone()
        
        if not item:
            raise HTTPException(404, "Item do pedido não encontrado")

        pedido_id = item["pedido_id"]
        produto_id = item["produto_id"]
        qtd = item["quantidade"] or 0.0
        status_item = item["status"]
        numero_pedido = item["numero_pedido"]

        # 3. Se o item estava separado ('entregue'), estornar o estoque
        if status_item == "entregue" and produto_id:
            from datetime import date
            row_saldo = cur.execute("SELECT quantidade FROM estoque_saldo WHERE produto_id=?", (produto_id,)).fetchone()
            saldo_anterior = row_saldo["quantidade"] if row_saldo else 0.0
            saldo_posterior = saldo_anterior + qtd
            
            motivo = f"Estorno exclusão item pedido {numero_pedido}"
            cur.execute("""
                INSERT INTO estoque_movimentacoes
                (produto_id, tipo, quantidade, saldo_anterior, saldo_posterior, motivo, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (produto_id, "saida" if qtd < 0 else "entrada", abs(qtd), saldo_anterior, saldo_posterior, motivo, str(date.today())))
            
            if row_saldo:
                cur.execute("""
                    UPDATE estoque_saldo 
                    SET quantidade=?, ultima_atualizacao=datetime('now') 
                    WHERE produto_id=?
                """, (saldo_posterior, produto_id))
            else:
                cur.execute("""
                    INSERT INTO estoque_saldo (produto_id, quantidade) 
                    VALUES (?, ?)
                """, (produto_id, saldo_posterior))

        # 4. Deletar programação de separação vinculada (se houver) e o item
        cur.execute("DELETE FROM producao_programada WHERE pedido_item_id=?", (id,))
        cur.execute("DELETE FROM pedidos_itens WHERE id=?", (id,))
        
        # 5. Recalcular o status do pedido
        _recalc_status_pedido(cur, pedido_id)
        
        conn.commit()
    finally:
        conn.close()
    return {"mensagem": "Item removido"}


# ─── ALERTAS ─────────────────────────────────────────────────────────────────