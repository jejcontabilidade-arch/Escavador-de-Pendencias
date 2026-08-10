import sqlite3
import os
import datetime

DB_PATH = os.path.abspath("escavador.db")

class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.inicializar_banco()

    def _get_connection(self):
        # Conecta com timeout de 30 segundos para evitar travamentos de concorrência
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Habilita o modo WAL para melhor performance em concorrência
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def inicializar_banco(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabela de clientes
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                cnpj TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                ativo INTEGER DEFAULT 1,
                pfx_path TEXT,
                senha TEXT,
                data_validade_certificado TEXT,
                atualizado_em TEXT
            );
            """)

            # Tabela de notas fiscais
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS notas_fiscais (
                chave_acesso TEXT PRIMARY KEY,
                numero_nf TEXT,
                serie TEXT,
                data_emissao TEXT,
                cnpj_emitente TEXT,
                nome_emitente TEXT,
                cnpj_destinatario TEXT,
                nome_destinatario TEXT,
                valor_produtos REAL,
                valor_nota REAL,
                pis REAL,
                cofins REAL,
                icms REAL,
                caminho_xml TEXT,
                data_captura TEXT
            );
            """)

            # Tabela de alertas da caixa postal
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS alertas_caixa_postal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj_cliente TEXT,
                assunto TEXT,
                conteudo TEXT,
                data_captura TEXT,
                resolvido INTEGER DEFAULT 0
            );
            """)

            # Tabela de jobs da fila
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_job TEXT NOT NULL, -- 'e-cac' ou 'nfe_xml'
                cnpj_cliente TEXT NOT NULL,
                status TEXT DEFAULT 'pendente', -- 'pendente', 'rodando', 'sucesso', 'erro'
                tentativas INTEGER DEFAULT 0,
                erro_mensagem TEXT,
                criado_em TEXT,
                iniciado_em TEXT,
                finalizado_em TEXT,
                forcar_todos INTEGER DEFAULT 0,
                destinatario TEXT
            );
            """)
            
            # Tentar adicionar colunas caso o banco já existisse
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN forcar_todos INTEGER DEFAULT 0;")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE jobs ADD COLUMN destinatario TEXT;")
            except sqlite3.OperationalError:
                pass
            
            conn.commit()

    # --- Métodos para Tabela Clientes ---
    def salvar_cliente(self, cnpj, nome, ativo=1, pfx_path=None, senha=None, data_validade=None):
        cnpj_clean = "".join(filter(str.isdigit, str(cnpj))).zfill(14)
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO clientes (cnpj, nome, ativo, pfx_path, senha, data_validade_certificado, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cnpj) DO UPDATE SET
                nome=excluded.nome,
                ativo=excluded.ativo,
                pfx_path=coalesce(excluded.pfx_path, pfx_path),
                senha=coalesce(excluded.senha, senha),
                data_validade_certificado=coalesce(excluded.data_validade_certificado, data_validade_certificado),
                atualizado_em=?
            """, (cnpj_clean, nome, int(ativo), pfx_path, senha, data_validade, agora, agora))
            conn.commit()

    def obter_cliente(self, cnpj):
        cnpj_clean = "".join(filter(str.isdigit, str(cnpj))).zfill(14)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clientes WHERE cnpj = ?", (cnpj_clean,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def listar_clientes_ativos(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clientes WHERE ativo = 1")
            return [dict(r) for r in cursor.fetchall()]

    # --- Métodos para Tabela Notas Fiscais ---
    def salvar_nota_fiscal(self, chave_acesso, numero_nf, serie, data_emissao, cnpj_emitente, nome_emitente,
                           cnpj_destinatario, nome_destinatario, valor_produtos, valor_nota, pis, cofins, icms, caminho_xml):
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cnpj_dest_clean = "".join(filter(str.isdigit, str(cnpj_destinatario))).zfill(14)
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO notas_fiscais (
                chave_acesso, numero_nf, serie, data_emissao, cnpj_emitente, nome_emitente,
                cnpj_destinatario, nome_destinatario, valor_produtos, valor_nota, pis, cofins, icms, caminho_xml, data_captura
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chave_acesso) DO UPDATE SET
                numero_nf=excluded.numero_nf,
                serie=excluded.serie,
                data_emissao=excluded.data_emissao,
                cnpj_emitente=excluded.cnpj_emitente,
                nome_emitente=excluded.nome_emitente,
                cnpj_destinatario=?,
                nome_destinatario=excluded.nome_destinatario,
                valor_produtos=excluded.valor_produtos,
                valor_nota=excluded.valor_nota,
                pis=excluded.pis,
                cofins=excluded.cofins,
                icms=excluded.icms,
                caminho_xml=excluded.caminho_xml,
                data_captura=?
            """, (chave_acesso, numero_nf, serie, data_emissao, cnpj_emitente, nome_emitente,
                  cnpj_dest_clean, nome_destinatario, valor_produtos, valor_nota, pis, cofins, icms, caminho_xml, agora,
                  cnpj_dest_clean, agora))
            conn.commit()

    def obter_nota_fiscal(self, chave_acesso):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notas_fiscais WHERE chave_acesso = ?", (chave_acesso,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def listar_notas_cliente(self, cnpj_destinatario):
        cnpj_clean = "".join(filter(str.isdigit, str(cnpj_destinatario))).zfill(14)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notas_fiscais WHERE cnpj_destinatario = ? ORDER BY data_emissao DESC", (cnpj_clean,))
            return [dict(r) for r in cursor.fetchall()]

    # --- Métodos para Tabela Alertas Caixa Postal ---
    def salvar_alerta_caixa_postal(self, cnpj_cliente, assunto, conteudo):
        cnpj_clean = "".join(filter(str.isdigit, str(cnpj_cliente))).zfill(14)
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO alertas_caixa_postal (cnpj_cliente, assunto, conteudo, data_captura, resolvido)
            VALUES (?, ?, ?, ?, 0)
            """, (cnpj_clean, assunto, conteudo, agora))
            conn.commit()

    def listar_alertas_cliente(self, cnpj_cliente, apenas_nao_resolvidos=True):
        cnpj_clean = "".join(filter(str.isdigit, str(cnpj_cliente))).zfill(14)
        query = "SELECT * FROM alertas_caixa_postal WHERE cnpj_cliente = ?"
        params = [cnpj_clean]
        if apenas_nao_resolvidos:
            query += " AND resolvido = 0"
        query += " ORDER BY data_captura DESC"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def marcar_alerta_como_resolvido(self, alerta_id):
        with self._get_connection() as conn:
            conn.execute("UPDATE alertas_caixa_postal SET resolvido = 1 WHERE id = ?", (alerta_id,))
            conn.commit()

    # --- Métodos para Tabela Jobs (Fila de Tarefas) ---
    def criar_job(self, tipo_job, cnpj_cliente, forcar_todos=0, destinatario=None):
        cnpj_clean = "".join(filter(str.isdigit, str(cnpj_cliente))).zfill(14) if cnpj_cliente else ""
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO jobs (tipo_job, cnpj_cliente, status, tentativas, criado_em, forcar_todos, destinatario)
            VALUES (?, ?, 'pendente', 0, ?, ?, ?)
            """, (tipo_job, cnpj_clean, agora, int(forcar_todos), destinatario))
            conn.commit()
            return cursor.lastrowid

    def obter_proximo_job_pendente(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Busca o job mais antigo na fila
            cursor.execute("""
            SELECT * FROM jobs 
            WHERE status = 'pendente' 
            ORDER BY criado_em ASC LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None

    def atualizar_status_job(self, job_id, status, erro_mensagem=None):
        agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            if status == "rodando":
                conn.execute("""
                UPDATE jobs 
                SET status = ?, iniciado_em = ?, tentativas = tentativas + 1 
                WHERE id = ?
                """, (status, agora, job_id))
            elif status in ["sucesso", "erro"]:
                conn.execute("""
                UPDATE jobs 
                SET status = ?, finalizado_em = ?, erro_mensagem = ? 
                WHERE id = ?
                """, (status, agora, erro_mensagem, job_id))
            else:
                conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
            conn.commit()

    def obter_status_jobs(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs ORDER BY criado_em DESC LIMIT 50")
            return [dict(r) for r in cursor.fetchall()]
