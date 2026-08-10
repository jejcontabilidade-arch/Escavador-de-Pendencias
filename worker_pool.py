import os
import sys
import time
import subprocess
import datetime
import json
from database_manager import DatabaseManager

def load_config():
    config = {}
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass
    if os.path.exists("config_private.json"):
        try:
            with open("config_private.json", "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception:
            pass
    return config

# Configurações globais do Worker Pool
POLL_INTERVAL = 5 # segundos entre checagens na fila
MAX_CONCURRENT_NFE = 3 # limite de processos NF-e paralelos
MAX_CONCURRENT_ECAC = 1 # limite de processos e-CAC paralelos (evitar concorrência de sessão do procurador)
MAX_TOTAL_WORKERS = 3  # limite total de processos paralelos

def log(msg, level="WORKER"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def iniciar_worker_pool():
    log("Iniciando Worker Pool - Escavador de Pendências", "SYSTEM")
    log(f"Configurações: Max Total={MAX_TOTAL_WORKERS}, Max e-CAC={MAX_CONCURRENT_ECAC}, Max NF-e={MAX_CONCURRENT_NFE}", "SYSTEM")
    
    db = DatabaseManager()
    active_jobs = {} # mapeia job_id -> { "process": Popen, "tipo_job": str, "cnpj": str, "log_file": str }
    
    os.makedirs("logs", exist_ok=True)
    
    try:
        while True:
            # 1. Checar processos ativos e atualizar status dos finalizados
            finished_ids = []
            for job_id, job_info in active_jobs.items():
                proc = job_info["process"]
                # Se o processo terminou
                if proc.poll() is not None:
                    exit_code = proc.returncode
                    tipo = job_info["tipo_job"]
                    cnpj = job_info["cnpj"]
                    
                    if exit_code == 0:
                        log(f"Job {job_id} ({tipo} para {cnpj}) concluído com SUCESSO.", "SUCCESS")
                        db.atualizar_status_job(job_id, "sucesso")
                    else:
                        err_msg = f"Processo finalizado com código de erro {exit_code}."
                        # Ler últimas linhas do log do job para tentar capturar o erro
                        try:
                            if os.path.exists(job_info["log_file"]):
                                with open(job_info["log_file"], "r", encoding="utf-8", errors="replace") as lf:
                                    lines = lf.readlines()
                                    if lines:
                                        err_msg += " Últimos logs: " + " | ".join([ln.strip() for ln in lines[-3:]])
                        except Exception:
                            pass
                            
                        log(f"Job {job_id} ({tipo} para {cnpj}) falhou: {err_msg}", "ERROR")
                        db.atualizar_status_job(job_id, "erro", erro_mensagem=err_msg[:500])
                    
                    finished_ids.append(job_id)
            
            # Remover finalizados do dicionário de ativos
            for jid in finished_ids:
                del active_jobs[jid]
                
            # 2. Verificar se podemos iniciar novos jobs
            total_ativos = len(active_jobs)
            ativos_ecac = sum(1 for j in active_jobs.values() if j["tipo_job"] == "e-cac")
            ativos_nfe = sum(1 for j in active_jobs.values() if j["tipo_job"] == "nfe_xml")
            
            if total_ativos < MAX_TOTAL_WORKERS:
                # Buscar o próximo job pendente
                # Observação: Para gerenciar concorrência fina, nós vamos consultar todos os pendentes e escolher o primeiro viável
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT * FROM jobs 
                        WHERE status = 'pendente' 
                        ORDER BY criado_em ASC
                    """)
                    jobs_pendentes = [dict(r) for r in cursor.fetchall()]
                
                proximo_job = None
                for job in jobs_pendentes:
                    tipo = job["tipo_job"]
                    # Verifica limites específicos por tipo de job
                    if tipo == "e-cac" and ativos_ecac >= MAX_CONCURRENT_ECAC:
                        continue # pula esse e-cac por enquanto
                    if tipo == "nfe_xml" and ativos_nfe >= MAX_CONCURRENT_NFE:
                        continue # pula esse nfe por enquanto
                        
                    proximo_job = job
                    break
                
                if proximo_job:
                    job_id = proximo_job["id"]
                    tipo = proximo_job["tipo_job"]
                    cnpj = proximo_job["cnpj_cliente"]
                    forcar_todos = proximo_job.get("forcar_todos", 0)
                    destinatario = proximo_job.get("destinatario")
                    
                    log(f"Iniciando Job {job_id} ({tipo}) para o cliente CNPJ {cnpj}...", "ACTION")
                    
                    # Atualiza status para rodando no banco de dados
                    db.atualizar_status_job(job_id, "rodando")
                    
                    # Define comandos de execução
                    if tipo == "e-cac":
                        cmd = [sys.executable, "executar.py", "--cliente", cnpj]
                        if forcar_todos:
                            cmd.append("--forcar-todos")
                    elif tipo == "nfe_xml":
                        # Tenta rodar a API de DF-e primeiro como via principal (Fase 3 - Camada de API DF-e)
                        api_sucesso = False
                        try:
                            import nfe_api
                            config = load_config()
                            api_sucesso = nfe_api.baixar_notas_api(cnpj, config, destinatario)
                        except Exception as e_api:
                            log(f"Erro ao tentar rodar a API FocusNFe: {e_api}", "WARNING")
                            api_sucesso = False
                            
                        if api_sucesso:
                            log(f"Job {job_id} (nfe_xml para {cnpj}) resolvido via API de DF-e com SUCESSO. Ignorando browser.", "SUCCESS")
                            db.atualizar_status_job(job_id, "sucesso")
                            continue # Pula a criação do subprocesso e avança para a próxima iteração
                            
                        # Se falhar a API, usa o fallback em Playwright
                        log(f"API FocusNFe falhou ou não configurada para CNPJ {cnpj}. Iniciando contingência via Playwright...", "WARNING")
                        cmd = [sys.executable, "consultar_nota_fiscal_xml.py", "--condominios", "--cliente", cnpj]
                        if forcar_todos:
                            cmd.append("--forcar-todos")
                        if destinatario:
                            cmd.extend(["--destinatario", destinatario])
                    else:
                        log(f"Tipo de job desconhecido: {tipo}", "ERROR")
                        db.atualizar_status_job(job_id, "erro", erro_mensagem=f"Tipo de job desconhecido: {tipo}")
                        continue
                        
                    # Prepara arquivos de log específicos do job
                    log_path = os.path.abspath(os.path.join("logs", f"job_{job_id}_{tipo}_{cnpj}.log"))
                    log_file = open(log_path, "w", encoding="utf-8")
                    
                    # Lança o subprocesso isolado
                    startupinfo = None
                    creationflags = 0
                    if os.name == 'nt':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = 0 # Ocultar console para não abrir janelas cmd pretas irritantes
                        creationflags = subprocess.CREATE_NO_WINDOW
                        
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            cwd=os.getcwd(),
                            startupinfo=startupinfo,
                            creationflags=creationflags
                        )
                        
                        active_jobs[job_id] = {
                            "process": proc,
                            "tipo_job": tipo,
                            "cnpj": cnpj,
                            "log_file": log_path,
                            "log_handle": log_file
                        }
                        
                        # Atualiza localmente a contagem de ativos
                        if tipo == "e-cac":
                            ativos_ecac += 1
                        else:
                            ativos_nfe += 1
                        total_ativos += 1
                        
                        log(f"Job {job_id} iniciado com sucesso como PID {proc.pid}. Logs: {os.path.basename(log_path)}", "SUCCESS")
                    except Exception as e_proc:
                        log(f"Erro crítico ao iniciar subprocesso para Job {job_id}: {e_proc}", "ERROR")
                        db.atualizar_status_job(job_id, "erro", erro_mensagem=str(e_proc))
                        log_file.close()
            
            # Aguarda POLL_INTERVAL segundos antes de checar a fila novamente
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        log("Interrupção manual recebida. Finalizando processos ativos do worker pool...", "WARNING")
        for job_id, job_info in active_jobs.items():
            proc = job_info["process"]
            if proc.poll() is None:
                log(f"Encerrando processo de Job {job_id} (PID {proc.pid})...", "WARNING")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            try:
                job_info["log_handle"].close()
            except Exception:
                pass
        log("Worker pool finalizado com sucesso.", "SYSTEM")

if __name__ == "__main__":
    iniciar_worker_pool()
