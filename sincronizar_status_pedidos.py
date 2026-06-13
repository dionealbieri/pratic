"""
Sincroniza o status dos pedidos e itens a partir do progresso real de produção
(qtd_produzida). Corrige pedidos antigos que ficaram como "aberto" mesmo já
estando produzidos (como o pedido 14758).

COMO USAR (rode uma única vez, na pasta do backend):
    python sincronizar_status_pedidos.py

Faz um backup automático do banco antes de alterar.
"""
import os
import sqlite3
import shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "banco", "pratic.db")


def recalc_status_pedido(cur, pedido_id):
    counts = cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN status='entregue' THEN 1 END) as entregues,
               COUNT(CASE WHEN status IN ('produzido','entregue')
                           OR (qtd_produzida >= quantidade AND quantidade > 0) THEN 1 END) as produzidos,
               COUNT(CASE WHEN qtd_produzida > 0
                           OR status IN ('em_producao','produzido','entregue') THEN 1 END) as iniciados
        FROM pedidos_itens WHERE pedido_id=?
    """, (pedido_id,)).fetchone()
    total = counts[0] or 0
    if total == 0:
        novo = 'aberto'
    elif counts[1] == total:
        novo = 'entregue'
    elif counts[2] == total:
        novo = 'produzido'
    elif counts[3] > 0:
        novo = 'em_producao'
    else:
        novo = 'aberto'
    cur.execute("UPDATE pedidos SET status=? WHERE id=?", (novo, pedido_id))
    return novo


def main():
    if not os.path.exists(DB_PATH):
        print(f"Banco não encontrado em: {DB_PATH}")
        return

    backup = DB_PATH + ".bak_sync_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB_PATH, backup)
    print(f"Backup criado: {backup}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    n_prod = cur.execute("""SELECT COUNT(*) FROM pedidos_itens
        WHERE qtd_produzida >= quantidade AND quantidade > 0 AND status NOT IN ('entregue')""").fetchone()[0]
    cur.execute("""UPDATE pedidos_itens SET status='produzido'
        WHERE qtd_produzida >= quantidade AND quantidade > 0 AND status NOT IN ('entregue')""")

    n_parc = cur.execute("""SELECT COUNT(*) FROM pedidos_itens
        WHERE qtd_produzida > 0 AND qtd_produzida < quantidade AND status='aberto'""").fetchone()[0]
    cur.execute("""UPDATE pedidos_itens SET status='em_producao'
        WHERE qtd_produzida > 0 AND qtd_produzida < quantidade AND status='aberto'""")

    ped_ids = [r[0] for r in cur.execute("SELECT id FROM pedidos").fetchall()]
    alterados = 0
    for pid in ped_ids:
        antes = cur.execute("SELECT status FROM pedidos WHERE id=?", (pid,)).fetchone()[0]
        depois = recalc_status_pedido(cur, pid)
        if antes != depois:
            alterados += 1

    conn.commit()
    conn.close()
    print(f"Itens marcados como produzidos: {n_prod}")
    print(f"Itens marcados como em produção: {n_parc}")
    print(f"Pedidos com status corrigido: {alterados} (de {len(ped_ids)})")
    print("Concluído.")


if __name__ == "__main__":
    main()
