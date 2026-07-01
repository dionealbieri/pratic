import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "banco", "pratic.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS maquinas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            setor TEXT,
            meta_padrao REAL DEFAULT 8000,
            ativa INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS comunicacao_recados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT NOT NULL,
            autor_id INTEGER,
            autor_nome TEXT,
            autor_setor TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            resolvido INTEGER DEFAULT 0,
            resolvido_por TEXT,
            resolvido_em TEXT
        );

        CREATE TABLE IF NOT EXISTS colaborador_tipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS colaboradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            maquina_id INTEGER,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (maquina_id) REFERENCES maquinas(id)
        );

        CREATE TABLE IF NOT EXISTS producao_diaria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            maquina_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            mes_referencia TEXT NOT NULL,
            meta REAL NOT NULL,
            producao REAL NOT NULL,
            excedente REAL,
            produto_estoque_id INTEGER DEFAULT NULL,
            perda_quantidade REAL DEFAULT 0,
            sobra_quantidade REAL DEFAULT 0,
            pedido_numero TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
            FOREIGN KEY (maquina_id) REFERENCES maquinas(id)
        );

        CREATE TABLE IF NOT EXISTS premiacao_operador (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            mes_referencia TEXT NOT NULL,
            total_producao REAL,
            dias_trabalhados INTEGER,
            media_diaria REAL,
            meta REAL,
            excedente_total REAL,
            elegivel INTEGER DEFAULT 0,
            valor_premio REAL DEFAULT 0,
            ranking INTEGER,
            fechado INTEGER DEFAULT 0,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
        );

        CREATE TABLE IF NOT EXISTS premiacao_auxiliar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            mes_referencia TEXT NOT NULL,
            posicao INTEGER,
            valor_bonus REAL DEFAULT 0,
            observacao TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id)
        );



        CREATE TABLE IF NOT EXISTS epis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT,
            descricao TEXT,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS funcao_epis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            funcao TEXT NOT NULL,
            epi_id INTEGER NOT NULL,
            FOREIGN KEY (epi_id) REFERENCES epis(id)
        );

        CREATE TABLE IF NOT EXISTS epi_entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            epi_id INTEGER NOT NULL,
            data_entrega TEXT NOT NULL,
            data_validade TEXT NOT NULL,
            motivo TEXT,
            responsavel TEXT,
            observacao TEXT,
            status TEXT DEFAULT 'ativo',
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
            FOREIGN KEY (epi_id) REFERENCES epis(id)
        );

        CREATE TABLE IF NOT EXISTS estoque_categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            descricao TEXT,
            tipo TEXT DEFAULT 'producao',
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS estoque_produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            categoria_id INTEGER,
            nome TEXT NOT NULL,
            marca TEXT,
            unidade TEXT DEFAULT 'unidade',
            estoque_minimo REAL DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (categoria_id) REFERENCES estoque_categorias(id)
        );

        CREATE TABLE IF NOT EXISTS estoque_saldo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER UNIQUE,
            quantidade REAL DEFAULT 0,
            ultima_atualizacao TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (produto_id) REFERENCES estoque_produtos(id)
        );

        CREATE TABLE IF NOT EXISTS estoque_movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            quantidade REAL NOT NULL,
            saldo_anterior REAL,
            saldo_posterior REAL,
            motivo TEXT,
            tipo_perda TEXT,
            responsavel TEXT,
            fornecedor TEXT,
            custo_unitario REAL,
            observacao TEXT,
            data TEXT NOT NULL,
            nota_fiscal TEXT,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (produto_id) REFERENCES estoque_produtos(id)
        );

        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave TEXT UNIQUE NOT NULL,
            valor TEXT NOT NULL,
            descricao TEXT
        );

        CREATE TABLE IF NOT EXISTS pedidos_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj TEXT,
            razao_social TEXT NOT NULL,
            nome_fantasia TEXT,
            ie TEXT,
            email TEXT,
            telefone TEXT,
            cep TEXT,
            logradouro TEXT,
            numero TEXT,
            complemento TEXT,
            bairro TEXT,
            cidade TEXT,
            uf TEXT,
            observacoes TEXT,
            ativo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_pedido TEXT NOT NULL,
            cliente_id INTEGER NOT NULL,
            prazo_entrega TEXT NOT NULL,
            vendedor TEXT,
            observacoes TEXT,
            status TEXT DEFAULT 'aberto',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (cliente_id) REFERENCES pedidos_clientes(id)
        );

        CREATE TABLE IF NOT EXISTS pedidos_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            produto_id INTEGER,
            descricao TEXT NOT NULL,
            quantidade REAL NOT NULL,
            unidade TEXT DEFAULT 'unidade',
            qtd_produzida REAL DEFAULT 0,
            status TEXT DEFAULT 'aberto',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        );

        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT DEFAULT 'sistema',
            acao TEXT NOT NULL,
            entidade TEXT NOT NULL,
            entidade_id INTEGER,
            descricao TEXT,
            valor_anterior TEXT,
            valor_novo TEXT,
            criado_em TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS app_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arquivo TEXT NOT NULL,
            caminho TEXT NOT NULL,
            tamanho_bytes INTEGER DEFAULT 0,
            motivo TEXT,
            criado_em TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    # Tabelas de segurança para controle de acesso e sessões
    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('gestor', 'producao', 'comercial', 'estoque')),
            nome TEXT NOT NULL,
            ativo INTEGER DEFAULT 1,
            deve_alterar_senha INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS sessoes (
            session_id TEXT PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            expira_em TEXT NOT NULL,
            criado_em TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );
    """)

    # Adicionar coluna deve_alterar_senha se não existir para bancos de dados já criados
    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN deve_alterar_senha INTEGER DEFAULT 1")
        # Como o banco de dados já existia, definimos deve_alterar_senha = 0 para todos os usuários atuais
        # para que o acesso deles não seja interrompido abruptamente. Novos usuários criados herdarão 1.
        c.execute("UPDATE usuarios SET deve_alterar_senha = 0")
    except sqlite3.OperationalError:
        pass

    # Liberação da Comunicação por usuário (0 = não participa, 1 = participa)
    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN comunicacao_ativa INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Liberação de canais por usuário (lista separada por vírgulas, ex: 'geral,producao')
    try:
        c.execute("ALTER TABLE usuarios ADD COLUMN canais_permitidos TEXT DEFAULT 'geral'")
        # Para usuários antigos (não gestores), liberamos também o canal do próprio setor (role)
        c.execute("""
            UPDATE usuarios 
            SET canais_permitidos = 'geral,' || role 
            WHERE role != 'gestor' AND role IS NOT NULL
        """)
        # Para gestores, liberamos todos os canais por padrão
        c.execute("""
            UPDATE usuarios 
            SET canais_permitidos = 'geral,producao,comercial,estoque' 
            WHERE role = 'gestor'
        """)
    except sqlite3.OperationalError:
        pass

    # Seed de usuários padrão se a tabela de usuários estiver vazia
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        import hashlib
        import secrets
        
        def _hash_pass(password: str) -> str:
            salt = secrets.token_bytes(16)
            key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            return salt.hex() + "." + key.hex()
            
        default_users = [
            ("admin", _hash_pass("admin"), "gestor", "Administrador", 0),
            ("producao", _hash_pass("producao123"), "producao", "Produção", 0),
            ("comercial", _hash_pass("comercial123"), "comercial", "Comercial", 0),
            ("estoque", _hash_pass("estoque123"), "estoque", "Almoxarifado", 0)
        ]
        c.executemany("""
            INSERT INTO usuarios (username, password_hash, role, nome, deve_alterar_senha)
            VALUES (?, ?, ?, ?, ?)
        """, default_users)


    # Migrações leves para bancos já existentes
    # Tipos de colaboradores configuráveis: remove a trava antiga que aceitava somente operador/auxiliar
    # e cria uma tabela simples para o usuário cadastrar novas funções/tipos pela tela.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS colaborador_tipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        )
    """)
    for tipo_padrao in ("operador", "auxiliar"):
        conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (tipo_padrao,))
    for row in conn.execute("SELECT DISTINCT tipo FROM colaboradores WHERE COALESCE(tipo,'')<>''").fetchall():
        conn.execute("INSERT OR IGNORE INTO colaborador_tipos (nome, ativo) VALUES (?, 1)", (row[0],))

    # Migração: controle por tipo de colaborador
    #   aparece_producao = aparece na seleção da Produção Diária e conta nos totais/ranking
    #   concorre_premio  = concorre ao prêmio de operador
    cols_tipos = [r[1] for r in conn.execute("PRAGMA table_info(colaborador_tipos)").fetchall()]
    primeira_migracao_flags = "aparece_producao" not in cols_tipos
    if "aparece_producao" not in cols_tipos:
        conn.execute("ALTER TABLE colaborador_tipos ADD COLUMN aparece_producao INTEGER DEFAULT 0")
    if "concorre_premio" not in cols_tipos:
        conn.execute("ALTER TABLE colaborador_tipos ADD COLUMN concorre_premio INTEGER DEFAULT 1")
    if primeira_migracao_flags:
        # Defaults aplicados só na primeira migração (não sobrescreve escolhas futuras do gestor)
        conn.execute("UPDATE colaborador_tipos SET aparece_producao=1, concorre_premio=1 WHERE LOWER(nome)='operador'")
        conn.execute("UPDATE colaborador_tipos SET aparece_producao=0 WHERE LOWER(nome)='auxiliar'")
        # Tipos de liderança (lider, líder, operador lider, operador líder, etc.):
        # produzem como operador, mas não concorrem ao prêmio.
        conn.execute("""
            UPDATE colaborador_tipos
               SET aparece_producao=1, concorre_premio=0
             WHERE nome LIKE '%lider%' OR nome LIKE '%líder%'
        """)

    # Migração: módulo de vendas (preço no produto, valores no item, totais e parcelas do pedido)
    cols_prod = [r[1] for r in conn.execute("PRAGMA table_info(estoque_produtos)").fetchall()]
    if "preco" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN preco REAL DEFAULT 0")
    if "custo" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN custo REAL DEFAULT 0")
    if "oculta_pdv" not in cols_prod:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN oculta_pdv INTEGER DEFAULT 0")
    cols_cat = [r[1] for r in conn.execute("PRAGMA table_info(estoque_categorias)").fetchall()]
    if "parent_id" not in cols_cat:
        conn.execute("ALTER TABLE estoque_categorias ADD COLUMN parent_id INTEGER")
    if "oculta_pdv" not in cols_cat:
        conn.execute("ALTER TABLE estoque_categorias ADD COLUMN oculta_pdv INTEGER DEFAULT 0")
    cols_pi = [r[1] for r in conn.execute("PRAGMA table_info(pedidos_itens)").fetchall()]
    if "valor_unitario" not in cols_pi:
        conn.execute("ALTER TABLE pedidos_itens ADD COLUMN valor_unitario REAL DEFAULT 0")
    if "desconto" not in cols_pi:
        conn.execute("ALTER TABLE pedidos_itens ADD COLUMN desconto REAL DEFAULT 0")
    if "status_separacao" not in cols_pi:
        conn.execute("ALTER TABLE pedidos_itens ADD COLUMN status_separacao TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS producao_programada (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_item_id INTEGER NOT NULL,
            data_programada TEXT NOT NULL,
            quantidade_programada REAL NOT NULL,
            criado_em TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (pedido_item_id) REFERENCES pedidos_itens(id)
        )
    """)
    cols_ped = [r[1] for r in conn.execute("PRAGMA table_info(pedidos)").fetchall()]
    if "acrescimo" not in cols_ped:
        conn.execute("ALTER TABLE pedidos ADD COLUMN acrescimo REAL DEFAULT 0")
    if "frete" not in cols_ped:
        conn.execute("ALTER TABLE pedidos ADD COLUMN frete REAL DEFAULT 0")
    if "desconto_global" not in cols_ped:
        conn.execute("ALTER TABLE pedidos ADD COLUMN desconto_global REAL DEFAULT 0")
    for _c, _t in [("transportadora","TEXT"),("nota_fiscal","TEXT"),("rastreio","TEXT"),
                   ("volumes","INTEGER"),("previsao_entrega","TEXT"),("obs_envio","TEXT"),
                   ("data_despacho","TEXT"),("data_entrega","TEXT"),("frete_pago","REAL DEFAULT 0")]:
        if _c not in cols_ped:
            conn.execute(f"ALTER TABLE pedidos ADD COLUMN {_c} {_t}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_parcelas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            forma_pagamento TEXT,
            vencimento TEXT,
            valor REAL DEFAULT 0,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        )
    """)

    colaboradores_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='colaboradores'").fetchone()
    if colaboradores_sql and "CHECK(tipo IN" in (colaboradores_sql[0] or ""):
        # A recriação precisa ocorrer fora de transação e com legacy_alter_table ligado,
        # para as FKs das tabelas de produção/EPIs continuarem apontando para colaboradores.
        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA legacy_alter_table=ON")
        conn.execute("ALTER TABLE colaboradores RENAME TO colaboradores_old")
        conn.execute("""
            CREATE TABLE colaboradores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL,
                maquina_id INTEGER,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (maquina_id) REFERENCES maquinas(id)
            )
        """)
        conn.execute("""
            INSERT INTO colaboradores (id, nome, tipo, maquina_id, ativo, criado_em)
            SELECT id, nome, tipo, maquina_id, ativo, criado_em FROM colaboradores_old
        """)
        conn.execute("DROP TABLE colaboradores_old")
        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.execute("PRAGMA foreign_keys=ON")

    cols = [row[1] for row in conn.execute("PRAGMA table_info(estoque_produtos)").fetchall()]
    if "codigo" not in cols:
        conn.execute("ALTER TABLE estoque_produtos ADD COLUMN codigo TEXT")

    # pedidos_clientes: garante colunas de contato/endereco em bancos antigos
    # (tabela usa CREATE IF NOT EXISTS, entao tabelas antigas nao recebem colunas novas)
    cols_cli = [row[1] for row in conn.execute("PRAGMA table_info(pedidos_clientes)").fetchall()]
    for _col in ("cnpj", "nome_fantasia", "ie", "email", "telefone",
                 "cep", "logradouro", "numero", "complemento",
                 "bairro", "cidade", "uf", "observacoes"):
        if _col not in cols_cli:
            conn.execute(f"ALTER TABLE pedidos_clientes ADD COLUMN {_col} TEXT")

    cols_prod = [row[1] for row in conn.execute("PRAGMA table_info(producao_diaria)").fetchall()]
    if "pedido_numero" not in cols_prod:
        conn.execute("ALTER TABLE producao_diaria ADD COLUMN pedido_numero TEXT")

    cols_cat = [row[1] for row in conn.execute("PRAGMA table_info(estoque_categorias)").fetchall()]
    if "tipo" not in cols_cat:
        conn.execute("ALTER TABLE estoque_categorias ADD COLUMN tipo TEXT DEFAULT 'producao'")

    # Anexos na comunicação (foto/documento por recado)
    cols_com = [row[1] for row in conn.execute("PRAGMA table_info(comunicacao_recados)").fetchall()]
    if "anexo_nome" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN anexo_nome TEXT")
    if "anexo_tipo" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN anexo_tipo TEXT")
    if "anexo_arquivo" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN anexo_arquivo TEXT")
    if "conversa_setor" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN conversa_setor TEXT")
        # Legado: cada recado vai para a conversa do setor de quem escreveu (menos gestor)
        conn.execute("""UPDATE comunicacao_recados SET conversa_setor = autor_setor
                        WHERE conversa_setor IS NULL AND autor_setor IS NOT NULL
                          AND autor_setor != 'gestor'""")
    if "conversa_usuario_id" not in cols_com:
        conn.execute("ALTER TABLE comunicacao_recados ADD COLUMN conversa_usuario_id INTEGER")
        # Legado: cada recado vai para a conversa do próprio autor (menos gestor)
        conn.execute("""UPDATE comunicacao_recados SET conversa_usuario_id = autor_id
                        WHERE conversa_usuario_id IS NULL AND autor_setor IS NOT NULL
                          AND autor_setor != 'gestor'""")

    # Migração para adicionar campo nota_fiscal em estoque_movimentacoes
    cols_mov = [row[1] for row in conn.execute("PRAGMA table_info(estoque_movimentacoes)").fetchall()]
    if "nota_fiscal" not in cols_mov:
        conn.execute("ALTER TABLE estoque_movimentacoes ADD COLUMN nota_fiscal TEXT")

    # Migração do campo Código/ID:
    # A versão anterior criou um índice UNIQUE apenas em codigo. Isso gerava erro 500
    # ao editar um produto quando existia o mesmo código em produto inativo/excluído.
    # A validação de duplicidade ativa fica no backend, retornando erro amigável 400.
    conn.execute("DROP INDEX IF EXISTS idx_estoque_produtos_codigo")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_estoque_produtos_codigo_lookup ON estoque_produtos(codigo)")

    # Garante que todas as chaves de Dados da Empresa existam em bancos antigos.
    # INSERT OR IGNORE preserva os dados já preenchidos pelo usuário.
    default_configs = [
        ("empresa_nome", "PRATIC", "Nome da empresa"),
        ("empresa_cnpj", "", "CNPJ da empresa"),
        ("empresa_telefone", "", "Telefone da empresa"),
        ("empresa_email", "", "E-mail da empresa"),
        ("empresa_cep", "", "CEP da empresa"),
        ("empresa_logradouro", "", "Logradouro da empresa"),
        ("empresa_numero", "", "Número da empresa"),
        ("empresa_bairro", "", "Bairro da empresa"),
        ("empresa_complemento", "", "Complemento da empresa"),
        ("empresa_cidade", "", "Cidade da empresa"),
        ("empresa_uf", "", "UF da empresa"),
        ("empresa_logo", "", "Logo da empresa em base64"),
        ("perm_gestor", "dashboard,producao,premiacao,colaboradores,maquinas,pedidos,estoque,epi,saldo-demanda,graficos,relatorios,configuracoes,backup,perm-usuarios,permissoes,empresa,mobile,estoque_mobile", "Permissões do perfil Gestor"),
        ("perm_producao", "dashboard,producao,premiacao,colaboradores,maquinas,epi,relatorios", "Permissões do perfil Produção"),
        ("perm_comercial", "dashboard,pedidos,relatorios", "Permissões do perfil Comercial"),
        ("perm_estoque", "dashboard,estoque,relatorios,estoque_mobile", "Permissões do perfil Estoque"),
        ("chat_p2p_permitido", "0", "Permitir chat 1:1 privado entre colaboradores"),
    ]
    for chave, valor, descricao in default_configs:
        conn.execute(
            "INSERT OR IGNORE INTO configuracoes (chave, valor, descricao) VALUES (?, ?, ?)",
            (chave, valor, descricao)
        )

    # Tabela de permissões por usuário (separada por causa do UNIQUE constraint)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuario_permissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            modulo TEXT NOT NULL,
            acao TEXT NOT NULL,
            permitido INTEGER DEFAULT 1,
            UNIQUE(usuario_id, modulo, acao)
        )
    """)

    conn.commit()
    conn.close()

def seed_data():
    conn = get_conn()
    c = conn.cursor()

    # Só faz seed se banco estiver vazio
    c.execute("SELECT COUNT(*) FROM maquinas")
    if c.fetchone()[0] > 0:
        conn.close()
        return

    # Máquina
    c.execute("INSERT INTO maquinas (nome, setor, meta_padrao) VALUES (?, ?, ?)",
              ("CNC 30", "Produção", 8000))
    maquina_id = c.lastrowid

    # Colaboradores
    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Hyngrisson", "operador", maquina_id))
    hyn_id = c.lastrowid

    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Talita", "operador", maquina_id))
    tal_id = c.lastrowid

    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Hyngrid", "auxiliar", None))
    c.execute("INSERT INTO colaboradores (nome, tipo, maquina_id) VALUES (?, ?, ?)",
              ("Sofia", "auxiliar", None))

    # Dados de Abril (datas seriais Excel convertidas)
    # 46127 = 2026-04-01, etc.
    abril_dados = [
        # (colaborador_id, data, producao)
        (hyn_id, "2026-04-01", 10000),
        (tal_id, "2026-04-01", 9850),
        (hyn_id, "2026-04-02", 10100),
        (tal_id, "2026-04-02", 7150),
        (hyn_id, "2026-04-03", 11200),
        (tal_id, "2026-04-03", 8000),
        (hyn_id, "2026-04-07", 10000),
        (tal_id, "2026-04-07", 8000),
        (hyn_id, "2026-04-09", 6050),
        (tal_id, "2026-04-09", 8000),
        (hyn_id, "2026-04-10", 8000),
        (tal_id, "2026-04-10", 10000),
        (hyn_id, "2026-04-11", 9500),
        (tal_id, "2026-04-11", 7000),
        (hyn_id, "2026-04-14", 9000),
        (tal_id, "2026-04-14", 8000),
        (hyn_id, "2026-04-15", 9500),
        (tal_id, "2026-04-15", 8500),
        (hyn_id, "2026-04-16", 8250),
        (tal_id, "2026-04-16", 6650),
        (hyn_id, "2026-04-17", 7000),
        (tal_id, "2026-04-17", 7000),
    ]

    for col_id, data, producao in abril_dados:
        meta = 8000
        excedente = (producao - meta) if producao > 0 else 0
        mes = "2026-04"
        c.execute("""INSERT INTO producao_diaria 
                     (colaborador_id, maquina_id, data, mes_referencia, meta, producao, excedente)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (col_id, maquina_id, data, mes, meta, producao, excedente))

    # Dados de Maio (Planilha4)
    maio_dados = [
        (hyn_id, "2026-05-05", 6300),
        (tal_id, "2026-05-05", 7250),
        (hyn_id, "2026-05-06", 10000),
        (tal_id, "2026-05-06", 8950),
        (hyn_id, "2026-05-07", 10500),
        (tal_id, "2026-05-07", 8200),
        (hyn_id, "2026-05-08", 12000),
        (tal_id, "2026-05-08", 9400),
        (hyn_id, "2026-05-09", 11600),
        (tal_id, "2026-05-09", 8300),
        (hyn_id, "2026-05-12", 10900),
        (tal_id, "2026-05-12", 8300),
        (hyn_id, "2026-05-13", 7300),
        (tal_id, "2026-05-13", 8700),
        (hyn_id, "2026-05-14", 8000),
        (tal_id, "2026-05-14", 7800),
        (hyn_id, "2026-05-15", 7700),
        (tal_id, "2026-05-15", 8800),
        (hyn_id, "2026-05-16", 8300),
        (tal_id, "2026-05-16", 8000),
        (hyn_id, "2026-05-19", 8000),
        (tal_id, "2026-05-19", 8300),
        (hyn_id, "2026-05-20", 5864),
        (tal_id, "2026-05-20", 9700),
        (hyn_id, "2026-05-21", 7200),
        (tal_id, "2026-05-21", 10700),
        (hyn_id, "2026-05-22", 8800),
        (tal_id, "2026-05-22", 10300),
        (hyn_id, "2026-05-23", 8600),
        (tal_id, "2026-05-23", 7500),
        (hyn_id, "2026-05-26", 10300),
        (tal_id, "2026-05-26", 8700),
        (hyn_id, "2026-05-27", 10400),
        (tal_id, "2026-05-27", 8600),
        (hyn_id, "2026-05-28", 0),
        (tal_id, "2026-05-28", 7800),
        (hyn_id, "2026-05-29", 0),
        (tal_id, "2026-05-29", 7800),
    ]

    for col_id, data, producao in maio_dados:
        meta = 8000
        excedente = (producao - meta) if producao > 0 else 0
        mes = "2026-05"
        c.execute("""INSERT INTO producao_diaria 
                     (colaborador_id, maquina_id, data, mes_referencia, meta, producao, excedente)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (col_id, maquina_id, data, mes, meta, producao, excedente))

    # Premiação auxiliares Abril
    c.execute("SELECT id FROM colaboradores WHERE nome = 'Hyngrid'")
    hyngrid_id = c.fetchone()[0]
    c.execute("SELECT id FROM colaboradores WHERE nome = 'Sofia'")
    sofia_id = c.fetchone()[0]

    c.execute("INSERT INTO premiacao_auxiliar (colaborador_id, mes_referencia, posicao, valor_bonus) VALUES (?, ?, ?, ?)",
              (sofia_id, "2026-04", 1, 200))
    c.execute("INSERT INTO premiacao_auxiliar (colaborador_id, mes_referencia, posicao, valor_bonus) VALUES (?, ?, ?, ?)",
              (hyngrid_id, "2026-04", 2, 100))

    # Configurações padrão
    configs = [
        ("meta_padrao", "8000", "Meta diária padrão de produção (peças)"),
        ("empresa_nome", "PRATIC", "Nome da empresa"),
        ("empresa_cnpj", "", "CNPJ da empresa"),
        ("empresa_endereco", "", "Endereço da empresa"),
        ("empresa_cep", "", "CEP da empresa"),
        ("empresa_numero", "", "Número da empresa"),
        ("empresa_logradouro", "", "Logradouro da empresa"),
        ("empresa_bairro", "", "Bairro da empresa"),
        ("empresa_complemento", "", "Complemento da empresa"),
        ("empresa_cidade", "", "Cidade da empresa"),
        ("empresa_uf", "", "UF da empresa"),
        ("empresa_telefone", "", "Telefone da empresa"),
        ("empresa_email", "", "E-mail da empresa"),
        ("empresa_logo", "", "Logo da empresa em base64"),
        ("valor_premio_operador", "300", "Valor do prêmio para operador que bater a média"),
        ("valor_premio_operador_1", "300", "Valor do prêmio para o 1º colocado operador"),
        ("valor_premio_operador_2", "200", "Valor do prêmio para o 2º colocado operador"),
        ("qtd_auxiliares_premiados", "2", "Quantidade de auxiliares premiados por mês"),
        ("bonus_auxiliar_1", "200", "Valor do bônus para o 1º auxiliar destaque"),
        ("bonus_auxiliar_2", "100", "Valor do bônus para o 2º auxiliar destaque"),
        ("bonus_auxiliar_3", "50", "Valor do bônus para o 3º auxiliar destaque"),
    ]
    for chave, valor, descricao in configs:
        c.execute("INSERT OR IGNORE INTO configuracoes (chave, valor, descricao) VALUES (?, ?, ?)",
                  (chave, valor, descricao))

    conn.commit()
    conn.close()
