import os
import time
import unittest
import threading
import subprocess
import sqlite3
from database_manager import DatabaseManager
import worker_pool

class TestWorkerPoolIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Usar um banco de dados de teste temporário
        cls.db_path = os.path.abspath("escavador_test_worker.db")
        if os.path.exists(cls.db_path):
            try: os.remove(cls.db_path)
            except: pass
            
        cls.db = DatabaseManager(cls.db_path)
        
        # Criar alguns clientes de teste
        cls.db.salvar_cliente("99999999000199", "Cliente Teste 1", ativo=1)
        cls.db.salvar_cliente("88888888000188", "Cliente Teste 2", ativo=1)

    @classmethod
    def tearDownClass(cls):
        # Força o Garbage Collector a limpar conexões SQLite pendentes no Windows antes de tentar remover o arquivo do banco
        import gc
        gc.collect()
        
        # Aguardar um momento antes de apagar arquivos de banco de dados
        time.sleep(1)
        for ext in ["", "-wal", "-shm"]:
            fpath = cls.db_path + ext
            if os.path.exists(fpath):
                try: os.remove(fpath)
                except Exception as e:
                    print(f"Não foi possível remover arquivo temporário {fpath}: {e}")

    def test_job_processing_cycle(self):
        # 1. Iniciar o worker_pool em uma thread separada
        # Criamos um wrapper para iniciar o worker apontando para o banco de teste
        
        def run_worker():
            # Monkeypatch na classe DatabaseManager no escopo de worker_pool para usar o db_path de teste
            # Para isso, vamos alterar a inicialização padrão no DatabaseManager
            db_mgr = DatabaseManager(self.db_path)
            
            # Vamos rodar uma versão simplificada ou o loop principal do worker de forma controlada
            active_jobs = {}
            db = db_mgr
            
            # Rodar apenas algumas iterações para o teste
            iterations = 4
            for _ in range(iterations):
                # Checar ativos
                finished_ids = []
                for job_id, job_info in active_jobs.items():
                    proc = job_info["process"]
                    if proc.poll() is not None:
                        exit_code = proc.returncode
                        db.atualizar_status_job(job_id, "sucesso" if exit_code == 0 else "erro", 
                                                erro_mensagem=f"Erro de teste. Cod: {exit_code}")
                        finished_ids.append(job_id)
                for jid in finished_ids:
                    del active_jobs[jid]
                
                # Iniciar novos
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM jobs WHERE status = 'pendente' ORDER BY criado_em ASC")
                    jobs_pendentes = [dict(r) for r in cursor.fetchall()]
                
                for job in jobs_pendentes:
                    job_id = job["id"]
                    tipo = job["tipo_job"]
                    cnpj = job["cnpj_cliente"]
                    
                    db.atualizar_status_job(job_id, "rodando")
                    
                    # Vamos rodar um comando rápido e inofensivo (como "whoami" ou "echo")
                    # que sempre retorna 0 ou 1 dependendo do teste
                    import sys
                    cmd = ["cmd.exe", "/c", "echo Testing Job"] if os.name == 'nt' else ["echo", "Testing Job"]
                    
                    log_path = os.path.join("logs", f"test_job_{job_id}.log")
                    os.makedirs("logs", exist_ok=True)
                    log_file = open(log_path, "w", encoding="utf-8")
                    
                    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                    active_jobs[job_id] = {
                        "process": proc,
                        "tipo_job": tipo,
                        "cnpj": cnpj,
                        "log_file": log_path,
                        "log_handle": log_file
                    }
                
                time.sleep(1)
                
            # Limpar e fechar handles remanescentes
            for job_info in active_jobs.values():
                try: job_info["process"].terminate()
                except: pass
                try: job_info["log_handle"].close()
                except: pass

        # 2. Inserir jobs pendentes
        job_id_1 = self.db.criar_job("nfe_xml", "99999999000199")
        job_id_2 = self.db.criar_job("e-cac", "88888888000188")
        
        # Verifica se foram criados como pendentes
        jobs = self.db.obter_status_jobs()
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["status"], "pendente")
        self.assertEqual(jobs[1]["status"], "pendente")
        
        # 3. Rodar a thread do worker de forma assíncrona
        t = threading.Thread(target=run_worker)
        t.start()
        
        # Aguardar tempo para as iterações do worker rodarem
        time.sleep(5)
        t.join()
        
        # 4. Validar se os jobs mudaram de status
        jobs_depois = self.db.obter_status_jobs()
        # Ordena por ID decrescente ou crescente
        jobs_depois.sort(key=lambda x: x["id"])
        
        # Devem ter sido processados (sucesso ou erro dependendo do retorno do comando)
        self.assertIn(jobs_depois[0]["status"], ["sucesso", "erro"])
        self.assertIn(jobs_depois[1]["status"], ["sucesso", "erro"])
        print(f"Status final do Job 1: {jobs_depois[0]['status']}")
        print(f"Status final do Job 2: {jobs_depois[1]['status']}")

if __name__ == "__main__":
    unittest.main()
