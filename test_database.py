import unittest
import os
import tempfile
import shutil
from database_manager import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory to isolate test database file
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_escavador.db")
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        # Trigger garbage collection to release file handles on Windows
        import gc
        gc.collect()
        # Remove the temporary directory after tests
        try:
            shutil.rmtree(self.test_dir)
        except Exception:
            pass

    def test_database_initialization(self):
        """Test if the database file is created and contains correct tables."""
        self.assertTrue(os.path.exists(self.db_path))
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            self.assertIn("clientes", tables)
            self.assertIn("notas_fiscais", tables)
            self.assertIn("alertas_caixa_postal", tables)
            self.assertIn("jobs", tables)

    def test_save_and_retrieve_client(self):
        """Test saving a client (insert/update on conflict)."""
        cnpj = "05.443.435/0001-24"
        nome = "J&J Serviços"
        
        # Save new client
        self.db.salvar_cliente(cnpj, nome, ativo=1, pfx_path="path/to/pfx.pfx", senha="123")
        client = self.db.obter_cliente("05443435000124")
        
        self.assertIsNotNone(client)
        self.assertEqual(client["cnpj"], "05443435000124")
        self.assertEqual(client["nome"], "J&J Serviços")
        self.assertEqual(client["ativo"], 1)
        self.assertEqual(client["pfx_path"], "path/to/pfx.pfx")
        self.assertEqual(client["senha"], "123")

        # Update client
        self.db.salvar_cliente(cnpj, "J&J Serviços Profissionais", ativo=0)
        updated = self.db.obter_cliente("05443435000124")
        self.assertEqual(updated["nome"], "J&J Serviços Profissionais")
        self.assertEqual(updated["ativo"], 0)

    def test_save_and_retrieve_invoice(self):
        """Test saving and retrieving invoice XML details."""
        chave = "35260505443435000124550010000001231000001234"
        self.db.salvar_nota_fiscal(
            chave_acesso=chave,
            numero_nf="123",
            serie="1",
            data_emissao="2026-05-28",
            cnpj_emitente="12345678000199",
            nome_emitente="Emitente Teste",
            cnpj_destinatario="05443435000124",
            nome_destinatario="J&J Serviços",
            valor_produtos=100.0,
            valor_nota=105.0,
            pis=1.5,
            cofins=4.5,
            icms=18.0,
            caminho_xml="xmls/nota.xml"
        )
        
        nf = self.db.obter_nota_fiscal(chave)
        self.assertIsNotNone(nf)
        self.assertEqual(nf["numero_nf"], "123")
        self.assertEqual(nf["valor_nota"], 105.0)
        self.assertEqual(nf["cnpj_destinatario"], "05443435000124")

        # List notes for client
        notes = self.db.listar_notas_cliente("05443435000124")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["chave_acesso"], chave)

    def test_save_and_resolve_alert(self):
        """Test alerts recording and resolution."""
        cnpj = "05443435000124"
        self.db.salvar_alerta_caixa_postal(cnpj, "Exclusão do Simples", "Conteúdo do alerta")
        
        alerts = self.db.listar_alertas_cliente(cnpj)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["assunto"], "Exclusão do Simples")
        self.assertEqual(alerts[0]["resolvido"], 0)

        # Mark as resolved
        self.db.marcar_alerta_como_resolvido(alerts[0]["id"])
        alerts_resolved = self.db.listar_alertas_cliente(cnpj, apenas_nao_resolvidos=True)
        self.assertEqual(len(alerts_resolved), 0)

    def test_job_queue_states(self):
        """Test job scheduling and worker queue transitions."""
        # Setup job
        job_id = self.db.criar_job("nfe_xml", "05443435000124")
        
        # Get next job
        job = self.db.obter_proximo_job_pendente()
        self.assertIsNotNone(job)
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["tipo_job"], "nfe_xml")
        self.assertEqual(job["status"], "pendente")

        # Update status to running
        self.db.atualizar_status_job(job_id, "rodando")
        job_running = self.db.obter_proximo_job_pendente()
        self.assertIsNone(job_running)  # No pending jobs left

        # Verify job is updated
        status_list = self.db.obter_status_jobs()
        self.assertEqual(len(status_list), 1)
        self.assertEqual(status_list[0]["status"], "rodando")
        self.assertEqual(status_list[0]["tentativas"], 1)

        # Update status to success
        self.db.atualizar_status_job(job_id, "sucesso")
        status_list_final = self.db.obter_status_jobs()
        self.assertEqual(status_list_final[0]["status"], "sucesso")

if __name__ == "__main__":
    unittest.main()
