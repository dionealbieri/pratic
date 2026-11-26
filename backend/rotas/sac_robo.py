"""
Robô do SAC Varejo (Softline) — lê as vendas sozinho e coloca na caixa "Pedidos SAC".

Como funciona (o mesmo caminho que o navegador faz):
  1. Login em /site/Default.aspx (licença + usuário + senha; formulário ASP.NET, sem captcha).
  2. Lista de vendas: POST /site/ServiceFacadeHandler.ashx  {Method: FIND, Entidade: ListaVendasBEC}
     filtrando DT_LANCAMENTO >= data. Vem venda, lançamento, cliente, situação (A/L/C) e total.
  3. Para cada venda nova com situação A: abre /site/Vendas/EmissaoOrdemEntregaRel.aspx?CD=<venda>
     (o ícone da impressora) e baixa o PDF pelo link de exportação do relatório.
  4. Vendas que já estão no PRATIC só têm a situação conferida (A -> C vira alerta/cancelamento).

Variáveis no Coolify (app teste):
  SAC_USUARIO, SAC_SENHA         login do SAC (obrigatórias)
  SAC_LICENCA                    nº da licença (padrão 3382)
  SAC_AUTO=0                     desliga a leitura a cada 15 min (o botão "Sincronizar agora" continua)
No app de treinamento (PRATIC_AMBIENTE definido) o robô fica desligado: lá os dados vêm do teste.
"""
import os
import re
import json
import asyncio
import datetime
import tempfile
import traceback
from urllib.parse import quote, urljoin

import httpx

from database import get_conn

DISPONIVEL = True
INTERVALO_MIN = 15
BASE = (os.environ.get("SAC_BASE_URL") or "https://www.sacvarejo.com.br/site/").rstrip("/") + "/"
JANELA_CANCEL_DIAS = 30        # confere cancelamentos das vendas dos últimos 30 dias
MAX_PDFS_POR_LEITURA = 40

_lock = asyncio.Lock()
_tarefa = None


# ─── utilidades ──────────────────────────────────────────────────────────────
def _hoje() -> datetime.date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except Exception:
        return (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).date()


def _agora() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def configurado() -> bool:
    return bool((os.environ.get("SAC_USUARIO") or "").strip() and (os.environ.get("SAC_SENHA") or "").strip())


def motivo_desligado() -> str:
    if (os.environ.get("PRATIC_AMBIENTE") or "").strip():
        return "No treinamento o robô fica desligado (os dados vêm do app teste)."
    return ""


def automatico() -> bool:
    return configurado() and not motivo_desligado() and (os.environ.get("SAC_AUTO") or "1").strip() != "0"


def _cfg_set(conn, chave, valor, desc=""):
    conn.execute("""INSERT INTO configuracoes (chave, valor, descricao) VALUES (?,?,?)
                    ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor""", (chave, valor, desc))


def _cfg_get(conn, chave):
    r = conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
    return r["valor"] if r else None


def _data_sac(v):
    """'/Date(1764126000000-0300)/', '2026-11-26T00:00:00' ou '26/11/2026' -> date."""
    if v is None:
        return None
    s = str(v)
    m = re.search(r"/Date\((-?\d+)([+-]\d{4})?\)/", s)
    if m:
        ms = int(m.group(1))
        off = m.group(2) or "-0300"
        h = int(off[:3]); mi = int(off[0] + off[3:])
        dt = datetime.datetime.utcfromtimestamp(ms / 1000) + datetime.timedelta(hours=h, minutes=mi)
        return dt.date()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _campo(reg: dict, *nomes):
    """Pega um campo aceitando NomePropriedade, NOME_COLUNA ou objeto aninhado (CliFor.NomeCliFor)."""
    for n in nomes:
        cur = reg
        ok = True
        for parte in n.split("."):
            if isinstance(cur, dict) and parte in cur:
                cur = cur[parte]
            else:
                ok = False
                break
        if ok and cur not in (None, ""):
            return cur
    return None


def _hidden_inputs(html: str) -> dict:
    campos = {}
    for tag in re.findall(r"<input\b[^>]*>", html, re.I):
        n = re.search(r'\bname="([^"]+)"', tag)
        if not n:
            continue
        v = re.search(r'\bvalue="([^"]*)"', tag)
        tipo = (re.search(r'\btype="([^"]+)"', tag) or [None, ""])[1].lower()
        if tipo in ("checkbox", "radio") and "checked" not in tag.lower():
            continue
        import html as _h
        campos[n.group(1)] = _h.unescape(v.group(1)) if v else ""
    return campos


def _texto(r: httpx.Response) -> str:
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        return r.content.decode("latin-1", errors="replace")


# ─── cliente do SAC ──────────────────────────────────────────────────────────
class ErroSac(Exception):
    pass


class SacCliente:
    def __init__(self):
        self.c = httpx.AsyncClient(follow_redirects=True, timeout=60, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9",
        })

    async def fechar(self):
        await self.c.aclose()

    async def login(self):
        r = await self.c.get(BASE + "Default.aspx")
        html = _texto(r)
        if "txt_senha" not in html:
            raise ErroSac("A tela de login do SAC mudou (não achei o campo de senha).")
        m = re.search(r'<form[^>]*\baction="([^"]*)"', html, re.I)
        acao = urljoin(str(r.url), (m.group(1) if m else "Default.aspx").replace("&amp;", "&"))
        if "opr=LOGOFF" in acao:
            acao = BASE + "Default.aspx"
        dados = _hidden_inputs(html)
        nome = lambda sufixo: next((k for k in dados if k.endswith(sufixo)), "ctl00$conteudoMaster$" + sufixo)
        dados[nome("txt_mt")] = (os.environ.get("SAC_LICENCA") or "3382").strip()
        dados[nome("txt_login")] = os.environ.get("SAC_USUARIO", "").strip()
        dados[nome("txt_senha")] = os.environ.get("SAC_SENHA", "")
        dados["__EVENTTARGET"] = "ctl00$conteudoMaster$btnContinuar"
        dados["__EVENTARGUMENT"] = ""
        r = await self.c.post(acao, data=dados, headers={"Referer": str(r.url)})
        html = _texto(r)
        if 'type="password"' in html and "txt_senha" in html:
            msg = re.search(r"MontaToastr\(\s*['\"]([^'\"]{3,160})", html) or re.search(r'class="[^"]*(?:erro|error|alert)[^"]*"[^>]*>([^<]{3,160})<', html, re.I)
            raise ErroSac("O SAC recusou o login" + (f": {msg.group(1).strip()}" if msg else " (confira licença, usuário e senha)."))
        return True

    async def _find(self, entidade: str, filtro: dict, tipo: int = 7):
        env = {"Method": "FIND", "Entidade": entidade, "FindFilter": filtro, "FindTypeFind": tipo, "LimiteNivel": 6}
        corpo = quote(json.dumps(env, ensure_ascii=False), safe="")
        r = await self.c.post(BASE + "ServiceFacadeHandler.ashx", content=corpo, headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=ISO-8859-15",
            "X-Requested-With": "XMLHttpRequest", "Referer": BASE + "Vendas/VendasLST.aspx"})
        txt = _texto(r).strip()
        if r.status_code != 200 or not txt or txt == "ERRO":
            raise ErroSac(f"A lista de vendas do SAC não respondeu (HTTP {r.status_code}).")
        if txt.lstrip().startswith("<"):
            raise ErroSac("A sessão do SAC caiu durante a leitura (voltou a tela de login).")
        res = json.loads(txt)
        erros = res.get("Errors") or []
        if erros:
            raise ErroSac("O SAC respondeu com erro: " + "; ".join(str(e.get("Message", e)) if isinstance(e, dict) else str(e) for e in erros)[:300])
        return res

    async def listar_vendas(self, desde: datetime.date, ate: datetime.date = None):
        vendas, pagina = [], 1
        while pagina <= 20:
            crit = [{"Nome": "DT_LANCAMENTO", "Valor": desde.strftime("%d/%m/%Y"), "Conector": "AND", "Tipo": "GREAT_THAN"}]
            if ate:
                crit.append({"Nome": "DT_LANCAMENTO", "Valor": ate.strftime("%d/%m/%Y"), "Conector": "AND", "Tipo": "LESS_THAN"})
            filtro = {"Criterios": crit,
                      "Orders": [{"NomePropriedade": "ID_VENDA", "Nome": "ID_VENDA", "OrderDirecao": "DESC"}],
                      "PagesNavigation": {}, "MaxPages": 50, "PageCount": 0, "CurrentBlock": 0,
                      "CurrentPage": pagina, "ItensPorPagina": 200, "HavePagination": True,
                      "CacheLocal": False, "Cache": False, "CarregaVinculadaUmParaMuitos": False,
                      "CarregaVinculadaUmParaUm": True, "FonteDado": "", "LimiteRetorno": 0,
                      "QtdRegistrosBusca": 0, "SubProcesso": "", "Distinct": False}
            res = await self._find("ListaVendasBEC", filtro)
            col = res.get("COL") or res.get("Col") or []
            vendas.extend(col)
            total_pag = (res.get("Filter") or res.get("FindFilter") or {}).get("PageCount") or 0
            if len(col) < 200 or (total_pag and pagina >= total_pag):
                break
            pagina += 1
        return vendas

    async def baixar_pdf(self, venda: str, destino: str):
        url = f"{BASE}Vendas/EmissaoOrdemEntregaRel.aspx?CD={venda}"
        r = await self.c.get(url, headers={"Referer": BASE + "Vendas/VendasLST.aspx"})
        html = _texto(r)
        m = re.search(r'"ExportUrlBase"\s*:\s*"([^"]+)"', html)
        if not m:
            if "txt_senha" in html:
                raise ErroSac("A sessão do SAC caiu antes de abrir o relatório.")
            raise ErroSac(f"Não achei o botão de exportar no relatório da venda {venda}.")
        base = m.group(1).encode().decode("unicode_escape").replace("&amp;", "&")
        r = await self.c.get(urljoin(BASE, base + "PDF"), headers={"Referer": url})
        if not r.content.startswith(b"%PDF"):
            raise ErroSac(f"O SAC não devolveu um PDF para a venda {venda}.")
        with open(destino, "wb") as f:
            f.write(r.content)


# ─── leitura ─────────────────────────────────────────────────────────────────
async def sincronizar(origem: str = "manual") -> dict:
    if not configurado():
        return {"ok": False, "mensagem": "Falta o login do SAC (SAC_USUARIO / SAC_SENHA)."}
    if _lock.locked():
        return {"ok": True, "mensagem": "Já tem uma leitura do SAC em andamento — aguarde um instante."}
    async with _lock:
        from rotas import sac as sacmod
        conn = get_conn()
        try:
            sacmod.tabelas(conn)
            desde_txt = _cfg_get(conn, "sac_importar_desde")
        finally:
            conn.close()
        try:
            desde = datetime.date.fromisoformat(desde_txt) if desde_txt else _hoje()
        except ValueError:
            desde = _hoje()
        consulta = min(desde, _hoje() - datetime.timedelta(days=JANELA_CANCEL_DIAS))

        res = {"novas": 0, "ja_existiam": 0, "canceladas": 0, "ignoradas_L": 0, "erros": []}
        cli = SacCliente()
        try:
            await cli.login()
            lista = await cli.listar_vendas(consulta)
            conn = get_conn()
            try:
                conhecidas = {r["venda"] for r in conn.execute("SELECT venda FROM sac_vendas")}
            finally:
                conn.close()

            baixar = []
            for reg in lista:
                venda = str(_campo(reg, "IdVenda", "ID_VENDA") or "").strip()
                if not venda:
                    continue
                sit = str(_campo(reg, "Situacao", "SITUACAO") or "").strip().upper()[:1]
                lanc = _data_sac(_campo(reg, "DtLancamento", "DT_LANCAMENTO"))
                meta = {"venda": venda,
                        "cliente": _campo(reg, "CliFor.NomeCliFor", "NomeCliFor", "CliFor.NOME_CLIFOR"),
                        "total": _num(_campo(reg, "ValorTotal", "VALOR_TOTAL")),
                        "lancamento": lanc.isoformat() if lanc else None}
                if venda in conhecidas:
                    conn = get_conn()
                    try:
                        mud = sacmod.atualizar_situacao(conn, venda, sit, meta)
                    finally:
                        conn.close()
                    res["ja_existiam"] += 1
                    if mud and mud.startswith("cancelada"):
                        res["canceladas"] += 1
                    continue
                if sit != "A":
                    if sit == "L":
                        res["ignoradas_L"] += 1
                    continue
                if lanc and lanc < desde:
                    continue
                tipo = str(_campo(reg, "TipoLancamento", "TIPO_LANCAMENTO") or "V").upper()[:1]
                if tipo not in ("V", ""):
                    continue
                baixar.append(meta)

            for meta in sorted(baixar, key=lambda m: int(m["venda"]) if m["venda"].isdigit() else 0)[:MAX_PDFS_POR_LEITURA]:
                tmp = os.path.join(tempfile.gettempdir(), f"sac_{meta['venda']}.pdf")
                try:
                    await cli.baixar_pdf(meta["venda"], tmp)
                    def _registrar(caminho=tmp, m=meta):
                        c2 = get_conn()
                        try:
                            return sacmod.registrar_pdf(c2, caminho, f"venda_{m['venda']}.pdf", "robo", "A", m)
                        finally:
                            c2.close()
                    r = await asyncio.to_thread(_registrar)
                    if r.get("status") == "registrada":
                        res["novas"] += 1
                    elif r.get("status") == "erro":
                        res["erros"].append(f"{meta['venda']}: {r.get('motivo')}")
                except Exception as e:
                    res["erros"].append(f"{meta['venda']}: {e}")
                finally:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            if len(baixar) > MAX_PDFS_POR_LEITURA:
                res["erros"].append(f"Ficaram {len(baixar) - MAX_PDFS_POR_LEITURA} vendas para a próxima leitura.")

            partes = [f"{res['novas']} venda(s) nova(s)"]
            if res["canceladas"]:
                partes.append(f"{res['canceladas']} cancelada(s) no SAC")
            msg = "Leitura do SAC concluída: " + ", ".join(partes) + "."
            if res["erros"]:
                msg += f" {len(res['erros'])} aviso(s)."
            conn = get_conn()
            try:
                _cfg_set(conn, "sac_ultima_leitura", _agora(), "Pedidos SAC: última leitura do robô")
                _cfg_set(conn, "sac_ultimo_erro", "; ".join(res["erros"])[:500] if res["erros"] and not res["novas"] and len(res["erros"]) >= len(baixar) else "", "Pedidos SAC: erro da última leitura")
                _cfg_set(conn, "sac_ultimo_resumo", json.dumps({**res, "origem": origem, "em": _agora()}, ensure_ascii=False)[:2000], "")
                conn.commit()
            finally:
                conn.close()
            return {"ok": True, "mensagem": msg, **res}
        except Exception as e:
            erro = str(e) if isinstance(e, ErroSac) else f"Falha inesperada: {e}"
            if not isinstance(e, ErroSac):
                traceback.print_exc()
            conn = get_conn()
            try:
                _cfg_set(conn, "sac_ultimo_erro", f"{_agora()} — {erro}"[:500], "Pedidos SAC: erro da última leitura")
                conn.commit()
            finally:
                conn.close()
            return {"ok": False, "mensagem": erro, **res}
        finally:
            await cli.fechar()


async def _loop():
    await asyncio.sleep(90)
    while True:
        try:
            if automatico():
                await sincronizar("automatico")
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(INTERVALO_MIN * 60)


def iniciar():
    global _tarefa
    if _tarefa is None and not motivo_desligado():
        _tarefa = asyncio.get_event_loop().create_task(_loop())
