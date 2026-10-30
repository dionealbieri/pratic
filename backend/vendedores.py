"""Vínculo entre o texto "vendedor" do pedido (vem do PDF importado ou digitado)
e o usuário do sistema que é esse vendedor.

Regras:
- Um usuário é encontrado pelo próprio nome e pelos nomes extras cadastrados em
  `usuarios.vendedor_nomes` (um por linha ou separados por ';').
- A comparação ignora maiúsculas, acentos e espaços repetidos.
- Se o mesmo nome bater com mais de um usuário, o pedido NÃO é vinculado
  (fica na lista "sem vendedor vinculado" para o Gestor decidir).
- Só pedidos ainda sem vínculo são vinculados automaticamente: uma atribuição
  manual feita pelo Gestor nunca é sobrescrita.
"""
import re
import unicodedata


def normalizar_nome(nome) -> str:
    if not nome:
        return ""
    s = unicodedata.normalize("NFKD", str(nome))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def separar_nomes(texto) -> list:
    """'JOAO SILVA; J. SILVA\\nJOAO' -> ['JOAO SILVA', 'J. SILVA', 'JOAO'] (sem vazios/duplicados)."""
    if not texto:
        return []
    vistos, saida = set(), []
    for parte in re.split(r"[;\n\r]+", str(texto)):
        p = re.sub(r"\s+", " ", parte).strip()
        n = normalizar_nome(p)
        if n and n not in vistos:
            vistos.add(n)
            saida.append(p)
    return saida


def juntar_nomes(lista) -> str:
    return "; ".join(separar_nomes("; ".join(lista or [])))


def mapa_vendedores(conn) -> dict:
    """{nome_normalizado: usuario_id}. Nomes ambíguos (2+ usuários) ficam com None."""
    mapa = {}
    rows = conn.execute(
        "SELECT id, nome, role, COALESCE(vendedor_nomes,'') AS vendedor_nomes "
        "FROM usuarios WHERE ativo = 1"
    ).fetchall()
    for r in rows:
        nomes = set()
        # O nome do próprio usuário só vale para quem é do Comercial;
        # nomes extras (vendedor_nomes) valem para qualquer perfil.
        if r["role"] == "comercial":
            nomes.add(normalizar_nome(r["nome"]))
        for extra in separar_nomes(r["vendedor_nomes"]):
            nomes.add(normalizar_nome(extra))
        for n in nomes:
            if not n:
                continue
            if n in mapa and mapa[n] != r["id"]:
                mapa[n] = None  # ambíguo
            else:
                mapa[n] = r["id"]
    return mapa


def resolver_vendedor(conn, texto_vendedor, mapa=None):
    """Retorna o id do usuário para o texto do vendedor, ou None."""
    n = normalizar_nome(texto_vendedor)
    if not n:
        return None
    if mapa is None:
        mapa = mapa_vendedores(conn)
    return mapa.get(n)


def vincular_pedido(conn, pedido_id, forcar=False):
    """Vincula um pedido ao vendedor pelo texto do campo `vendedor`.
    Com forcar=False, não mexe em pedido que já tem vínculo."""
    ped = conn.execute(
        "SELECT id, vendedor, vendedor_usuario_id FROM pedidos WHERE id = ?", (pedido_id,)
    ).fetchone()
    if not ped:
        return None
    if ped["vendedor_usuario_id"] and not forcar:
        return ped["vendedor_usuario_id"]
    uid = resolver_vendedor(conn, ped["vendedor"])
    conn.execute("UPDATE pedidos SET vendedor_usuario_id = ? WHERE id = ?", (uid, pedido_id))
    return uid


def vincular_pedidos_sem_vendedor(conn) -> int:
    """Tenta vincular todos os pedidos que ainda não têm vendedor. Retorna quantos vinculou."""
    mapa = mapa_vendedores(conn)
    if not mapa:
        return 0
    rows = conn.execute(
        "SELECT id, vendedor FROM pedidos "
        "WHERE vendedor_usuario_id IS NULL AND vendedor IS NOT NULL AND TRIM(vendedor) != ''"
    ).fetchall()
    vinculados = 0
    for r in rows:
        uid = mapa.get(normalizar_nome(r["vendedor"]))
        if uid:
            conn.execute("UPDATE pedidos SET vendedor_usuario_id = ? WHERE id = ?", (uid, r["id"]))
            vinculados += 1
    return vinculados
