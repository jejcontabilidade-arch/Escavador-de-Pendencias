import os
import sys

# Redireciona stdout e stderr para arquivo de log caso o processo rode sem console ou em modo silencioso
if os.environ.get("SILENT_MODE") == "1" or sys.stdout is None:
    os.makedirs("logs", exist_ok=True)
    try:
        sys.stdout = open(os.path.join("logs", "flask_server.log"), "a", encoding="utf-8", buffering=1)
    except Exception:
        pass
if os.environ.get("SILENT_MODE") == "1" or sys.stderr is None:
    os.makedirs("logs", exist_ok=True)
    try:
        sys.stderr = open(os.path.join("logs", "flask_server.log"), "a", encoding="utf-8", buffering=1)
    except Exception:
        pass

import json
import csv
import glob
import datetime
import subprocess
import shutil
import requests
from flask import Flask, render_template, jsonify, request, send_file, send_from_directory

app = Flask(__name__)

# Variáveis globais para gerenciar os subprocessos da automação e do gateway Node
processo_automacao = None
processo_nota_fiscal_xml = None
processo_gateway = None

def is_process_running_by_script(script_name):
    """
    Verifica se existe algum processo Python em execução com o nome do script
    especificado em sua linha de comando (excluindo este próprio processo do Flask).
    Retorna (True, [pids]) se houver, ou (False, []) caso contrário.
    """
    import subprocess
    import os
    current_pid = os.getpid()
    
    # Monta comando PowerShell para listar processos Python cujo CommandLine contenha o nome do script
    cmd = (
        f'powershell -NoProfile -Command "'
        f'Get-CimInstance Win32_Process -Filter \\"Name like \'%python%\'\\" '
        f'| Where-Object {{ $_.CommandLine -like \\"*{script_name}*\\" -and $_.ProcessId -ne {current_pid} }} '
        f'| Select-Object -ExpandProperty ProcessId"'
    )
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        lines = res.stdout.strip().split()
        pids = [int(line) for line in lines if line.isdigit()]
        return len(pids) > 0, pids
    except Exception:
        pass
    return False, []

def assign_current_process_to_job_object():
    """
    Cria um Job Object no Windows e associa o processo atual (Flask) a ele.
    Configura o Job Object com JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
    Isso garante que se o processo do Flask for encerrado (seja via console,
    taskkill ou clicando no 'X'), o Windows encerrará automaticamente todos
    os subprocessos filhos (como executar.py, consultar_nota_fiscal_xml.py e Chrome).
    """
    import os
    if os.name != 'nt':
        return
        
    try:
        import ctypes
        from ctypes import wintypes
        
        # Constante do Windows
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        
        # Estruturas do ctypes
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]
            
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]
            
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]
            
        # Obter handles
        kernel32 = ctypes.windll.kernel32
        
        # Criar o Job Object
        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            print("[JOB-OBJECT] Falha ao criar Job Object.")
            return
            
        # Configurar informações de limite
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        
        # SetInformationJobObject
        ret = kernel32.SetInformationJobObject(
            h_job,
            9, # JobObjectExtendedLimitInformation
            ctypes.byref(limits),
            ctypes.sizeof(limits)
        )
        if not ret:
            print("[JOB-OBJECT] Falha ao configurar limites do Job Object.")
            return
            
        # Associar o processo atual (Flask) ao Job Object
        h_process = kernel32.GetCurrentProcess()
        ret = kernel32.AssignProcessToJobObject(h_job, h_process)
        if not ret:
            err = kernel32.GetLastError()
            print(f"[JOB-OBJECT] Aviso: Não foi possível associar ao Job Object. Código de erro: {err}")
        else:
            print("[JOB-OBJECT] Processo atual associado com sucesso ao Job Object (Auto-Kill habilitado).")
            
            # Manter referência global para evitar garbage collection do handle
            global _global_job_handle
            _global_job_handle = h_job
            
    except Exception as e:
        print(f"[JOB-OBJECT] Erro ao configurar Job Object: {e}")

def load_config():
    config_path = "config.json"
    private_config_path = "config_private.json"
    config = {
        "headless": False,
        "timeout_ms": 30000,
        "relatorios_dir": "relatorios",
        "clientes_file": "clientes.csv",
        "portal_url": "https://cav.receita.fazenda.gov.br/ecac/",
        "cert_first_char": "J",
        "download_timeout_ms": 60000,
        "whatsapp_enabled": True,
        "whatsapp_number": "",
        "whatsapp_zapi_instance": "",
        "whatsapp_zapi_token": "",
        "whatsapp_zapi_client_token": "",
        "openai_api_key": ""
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                config.update(dados)
        except Exception:
            pass
    if os.path.exists(private_config_path):
        try:
            with open(private_config_path, "r", encoding="utf-8") as f:
                dados_privados = json.load(f)
                config.update(dados_privados)
        except Exception:
            pass
    return config

def save_config(config):
    config_path = "config.json"
    private_config_path = "config_private.json"
    
    chaves_privadas = [
        "whatsapp_zapi_instance", 
        "whatsapp_zapi_token", 
        "whatsapp_zapi_client_token", 
        "openai_api_key",
        "whatsapp_number"
    ]
    
    config_publica = {}
    config_privada = {}
    
    for k, v in config.items():
        if k in chaves_privadas:
            config_privada[k] = v
        else:
            config_publica[k] = v
            
    sucesso = True
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_publica, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Erro ao salvar config.json: {e}")
        sucesso = False
        
    try:
        with open(private_config_path, "w", encoding="utf-8") as f:
            json.dump(config_privada, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Erro ao salvar config_private.json: {e}")
        sucesso = False
        
    return sucesso

# Rota principal para a Interface Web
@app.route("/")
def index():
    return render_template("index.html")

# Rotas de suporte ao PWA na raiz
@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'manifest.json')

@app.route("/service-worker.js")
def serve_service_worker():
    response = send_from_directory(os.path.join(app.root_path, 'static'), 'service-worker.js')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Content-Type'] = 'application/javascript'
    return response

# Rota para encerrar o servidor Flask localmente
@app.route("/api/encerrar-servidor", methods=["POST"])
def encerrar_servidor():
    import signal
    print("Comando de encerramento recebido. Desligando o servidor Flask local...")
    
    # 1. Interromper a automação se estiver rodando para não deixar navegadores abertos
    try:
        global processo_automacao
        rodando, pids = is_process_running_by_script("executar.py")
        pids_to_kill = set(pids)
        if processo_automacao and processo_automacao.poll() is None:
            pids_to_kill.add(processo_automacao.pid)
            
        if pids_to_kill:
            print(f"Encerrando {len(pids_to_kill)} processo(s) de automação ativo(s)...")
            for pid in pids_to_kill:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    except Exception as e:
        print(f"Erro ao parar a automação no encerramento: {e}")
        
    # 1b. Interromper a Nota Fiscal XML se estiver rodando
    try:
        global processo_nota_fiscal_xml
        rodando_xml, pids_xml = is_process_running_by_script("consultar_nota_fiscal_xml.py")
        pids_xml_to_kill = set(pids_xml)
        if processo_nota_fiscal_xml and processo_nota_fiscal_xml.poll() is None:
            pids_xml_to_kill.add(processo_nota_fiscal_xml.pid)
            
        if pids_xml_to_kill:
            print(f"Encerrando {len(pids_xml_to_kill)} processo(s) de Nota Fiscal XML ativo(s)...")
            for pid in pids_xml_to_kill:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    except Exception as e:
        print(f"Erro ao parar a Nota Fiscal XML no encerramento: {e}")
        
    # 2. Chamar parada explícita do gateway Node para não deixá-lo órfão
    try:
        parar_gateway_whatsapp()
    except Exception as e:
        print(f"Erro ao parar gateway do WhatsApp no encerramento: {e}")
        
    # 3. Chamar parada explícita do gerenciador de túneis SSH
    try:
        import tunnel_manager
        tunnel_manager.stop()
    except Exception as e:
        print(f"Erro ao parar o gerenciador de túneis no encerramento: {e}")
        
    # 4. Tentar matar o processo pai (reloader) para evitar que ele reinicie o Flask
    try:
        ppid = os.getppid()
        if ppid and ppid > 0:
            print(f"Desligando o processo pai (reloader) com PID {ppid}...")
            if os.name == 'nt':
                subprocess.run(f"taskkill /F /PID {ppid}", shell=True, capture_output=True)
            else:
                os.kill(ppid, signal.SIGTERM)
    except Exception as e:
        print(f"Erro ao encerrar processo pai (reloader): {e}")
        
    # 5. Finalizar o próprio processo
    try:
        os.kill(os.getpid(), signal.SIGTERM)
        return jsonify({"status": "success", "message": "Servidor encerrando..."})
    except Exception as e:
        print(f"Erro ao encerrar servidor: {e}")
        # Fallback de encerramento bruto do processo
        os._exit(0)

# Rotas de Configuração
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def post_config():
    dados = request.json or {}
    config_atual = load_config()
    
    # Atualizar campos recebidos
    for key in config_atual.keys():
        if key in dados:
            config_atual[key] = dados[key]
            
    if save_config(config_atual):
        return jsonify({"status": "success", "message": "Configurações salvas com sucesso!"})
    else:
        return jsonify({"status": "error", "message": "Falha ao salvar as configurações."}), 500

# Rota para testar o envio de WhatsApp via Gateway local
@app.route("/api/config/testar-whatsapp", methods=["POST"])
def testar_whatsapp():
    dados = request.json or {}
    number = dados.get("whatsapp_number")
    
    if not number:
        return jsonify({"status": "error", "message": "Número de telefone do WhatsApp é obrigatório para o teste."}), 400
        
    url = "http://127.0.0.1:3000/api/send-message"
    payload = {
        "to": number,
        "message": "🤖 *Escavador de Pendências e-CAC*\n\nEste é um teste de comunicação enviado pela sua Instância Local do WhatsApp Web! Conectado com sucesso!"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code in [200, 201]:
            return jsonify({"status": "success", "message": "Mensagem de teste enviada com sucesso!"})
        else:
            return jsonify({"status": "error", "message": f"Erro do gateway local ({response.status_code}): {response.text}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Não foi possível conectar ao gateway local (porta 3000): {str(e)}"}), 500

# Rotas de Gestão de Clientes
@app.route("/api/clientes", methods=["GET"])
def get_clientes():
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    clientes = []
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cnpj = row.get("cnpj", "").strip()
                    nome = row.get("nome", "").strip()
                    ativo = row.get("ativo", "True").strip().lower() in ["true", "1", "yes", "ativo", "sim", "s"]
                    if cnpj:
                        clientes.append({"cnpj": cnpj, "nome": nome, "ativo": ativo})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao ler lista de clientes: {str(e)}"}), 500
    return jsonify(clientes)

@app.route("/api/clientes", methods=["POST"])
def add_cliente():
    dados = request.json or {}
    cnpj = "".join(filter(str.isdigit, dados.get("cnpj", "")))
    nome = dados.get("nome", "").strip()
    ativo = dados.get("ativo", True)
    
    if not cnpj or len(cnpj) not in [11, 14]:
        return jsonify({"status": "error", "message": "CNPJ/CPF inválido. Deve conter 11 (CPF) ou 14 (CNPJ) dígitos."}), 400
    if not nome:
        return jsonify({"status": "error", "message": "Nome do cliente é obrigatório."}), 400
        
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    
    clientes = []
    existe = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    c = "".join(filter(str.isdigit, row.get("cnpj", "").strip()))
                    n = row.get("nome", "").strip()
                    a = row.get("ativo", "True").strip()
                    if c == cnpj:
                        existe = True
                        clientes.append({"cnpj": cnpj, "nome": nome, "ativo": "True" if ativo else "False"})
                    else:
                        clientes.append({"cnpj": c, "nome": n, "ativo": a})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao acessar clientes: {str(e)}"}), 500
            
    if not existe:
        clientes.append({"cnpj": cnpj, "nome": nome, "ativo": "True" if ativo else "False"})
        
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["cnpj", "nome", "ativo"])
            for c in clientes:
                writer.writerow([c["cnpj"], c["nome"], c["ativo"]])
        return jsonify({"status": "success", "message": "Cliente cadastrado/atualizado com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao salvar CSV: {str(e)}"}), 500

@app.route("/api/clientes/<cnpj>", methods=["PUT"])
def update_cliente(cnpj):
    dados = request.json or {}
    ativo = dados.get("ativo")
    nome = dados.get("nome")
    
    cnpj = "".join(filter(str.isdigit, cnpj))
    if not cnpj or len(cnpj) not in [11, 14]:
        return jsonify({"status": "error", "message": "CNPJ/CPF inválido."}), 400
        
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    
    clientes = []
    encontrado = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    c = "".join(filter(str.isdigit, row.get("cnpj", "").strip()))
                    n = row.get("nome", "").strip()
                    a = row.get("ativo", "True").strip()
                    if c == cnpj:
                        encontrado = True
                        n_atualizado = nome.strip() if nome is not None else n
                        a_atualizado = "True" if (ativo if ativo is not None else (a.lower() in ["true", "1", "yes", "ativo"])) else "False"
                        clientes.append({"cnpj": c, "nome": n_atualizado, "ativo": a_atualizado})
                    else:
                        clientes.append({"cnpj": c, "nome": n, "ativo": a})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao processar clientes: {str(e)}"}), 500
            
    if not encontrado:
        return jsonify({"status": "error", "message": "Cliente não encontrado."}), 404
        
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["cnpj", "nome", "ativo"])
            for c in clientes:
                writer.writerow([c["cnpj"], c["nome"], c["ativo"]])
        return jsonify({"status": "success", "message": "Cliente atualizado com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao salvar CSV: {str(e)}"}), 500

@app.route("/api/clientes/<cnpj>", methods=["DELETE"])
def delete_cliente(cnpj):
    cnpj = "".join(filter(str.isdigit, cnpj))
    if not cnpj or len(cnpj) not in [11, 14]:
        return jsonify({"status": "error", "message": "CNPJ/CPF inválido."}), 400
        
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    
    clientes = []
    encontrado = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    c = "".join(filter(str.isdigit, row.get("cnpj", "").strip()))
                    n = row.get("nome", "").strip()
                    a = row.get("ativo", "True").strip()
                    if c == cnpj:
                        encontrado = True
                    else:
                        clientes.append({"cnpj": c, "nome": n, "ativo": a})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao processar clientes: {str(e)}"}), 500
            
    if not encontrado:
        return jsonify({"status": "error", "message": "Cliente não encontrado."}), 404
        
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["cnpj", "nome", "ativo"])
            for c in clientes:
                writer.writerow([c["cnpj"], c["nome"], c["ativo"]])
        return jsonify({"status": "success", "message": "Cliente excluído com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao salvar CSV: {str(e)}"}), 500

# Rotas de Gestão de Contatos/Agentes Autorizados do WhatsApp
@app.route("/api/autorizados", methods=["GET"])
def get_autorizados():
    csv_path = "autorizados.csv"
    contatos = []
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    num = row.get("whatsapp_number", "").strip()
                    nome = row.get("nome", "").strip()
                    perm = row.get("permissao", "operador").strip()
                    if num:
                        contatos.append({"whatsapp_number": num, "nome": nome, "permissao": perm})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao ler contatos autorizados: {str(e)}"}), 500
    return jsonify(contatos)

@app.route("/api/autorizados", methods=["POST"])
def add_autorizados():
    dados = request.json or {}
    number = "".join(filter(str.isdigit, dados.get("whatsapp_number", "")))
    nome = dados.get("nome", "").strip()
    permissao = dados.get("permissao", "operador").strip().lower()
    
    if not number or len(number) < 8:
        return jsonify({"status": "error", "message": "Número de WhatsApp inválido. Deve conter pelo menos 8 dígitos."}), 400
    if not nome:
        return jsonify({"status": "error", "message": "Nome do contato é obrigatório."}), 400
    if permissao not in ["admin", "operador", "agente"]:
        return jsonify({"status": "error", "message": "Permissão inválida. Deve ser admin, operador ou agente."}), 400
        
    csv_path = "autorizados.csv"
    contatos = []
    existe = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    num = "".join(filter(str.isdigit, row.get("whatsapp_number", "").strip()))
                    n = row.get("nome", "").strip()
                    p = row.get("permissao", "operador").strip().lower()
                    if num == number:
                        existe = True
                        contatos.append({"whatsapp_number": number, "nome": nome, "permissao": permissao})
                    else:
                        contatos.append({"whatsapp_number": num, "nome": n, "permissao": p})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao ler contatos autorizados: {str(e)}"}), 500
            
    if not existe:
        contatos.append({"whatsapp_number": number, "nome": nome, "permissao": permissao})
        
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["whatsapp_number", "nome", "permissao"])
            for c in contatos:
                writer.writerow([c["whatsapp_number"], c["nome"], c["permissao"]])
        return jsonify({"status": "success", "message": "Contato cadastrado/atualizado com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao salvar contatos no CSV: {str(e)}"}), 500

@app.route("/api/autorizados/<number>", methods=["DELETE"])
def delete_autorizado(number):
    number = "".join(filter(str.isdigit, number))
    if not number:
        return jsonify({"status": "error", "message": "Número inválido."}), 400
        
    csv_path = "autorizados.csv"
    contatos = []
    encontrado = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    num = "".join(filter(str.isdigit, row.get("whatsapp_number", "").strip()))
                    n = row.get("nome", "").strip()
                    p = row.get("permissao", "operador").strip().lower()
                    if num == number:
                        encontrado = True
                    else:
                        contatos.append({"whatsapp_number": num, "nome": n, "permissao": p})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao ler contatos autorizados: {str(e)}"}), 500
            
    if not encontrado:
        return jsonify({"status": "error", "message": "Contato não encontrado."}), 404
        
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["whatsapp_number", "nome", "permissao"])
            for c in contatos:
                writer.writerow([c["whatsapp_number"], c["nome"], c["permissao"]])
        return jsonify({"status": "success", "message": "Contato excluído com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao salvar CSV de contatos: {str(e)}"}), 500

# Funções de extração inteligente
def extrair_clientes_openai(text, api_key):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    prompt = """Você é um assistente especializado em extrair dados cadastrais de documentos.
Dado o texto bruto abaixo, extraia todos os clientes encontrados. Para cada cliente, você deve identificar:
1. O CNPJ (14 dígitos) ou CPF (11 dígitos).
2. O Nome/Razão Social da empresa ou cliente.

Retorne APENAS um JSON no seguinte formato (sem markdown ou blocos de código):
[
  {"cnpj": "00000000000000", "nome": "NOME DO CLIENTE"},
  {"cnpj": "11111111111", "nome": "NOME DO OUTRO CLIENTE"}
]

Atenção: 
- O campo 'cnpj' deve conter apenas os dígitos numéricos (seja CPF com 11 dígitos ou CNPJ com 14 dígitos).
- Ignore CPFs ou CNPJs da própria contabilidade ou órgãos públicos (como Receita Federal).
- Se não encontrar nenhum cliente, retorne um array vazio.

Texto bruto:
"""
    
    truncated_text = text[:60000]
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Você é um assistente de extração de dados estruturados."},
            {"role": "user", "content": prompt + truncated_text}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            import json
            data = json.loads(content)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list):
                        return v
            return []
        else:
            print(f"Erro na API da OpenAI: Status {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Falha na requisição da OpenAI: {e}")
        return None

def extrair_clientes_heuristica(text):
    import re
    cnpj_pattern = re.compile(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{14}\b')
    cpf_pattern = re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b')
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    extracted = {}
    
    cnpjs_a_excluir = {
        "02241127000128", "38050811000170", "37115714000155",
        "38050753000184", "01599281000103", "37992979000131",
        "37993599000111", "02273061000158", "05443435000124"
    }
    
    def eh_nome_valido(s):
        s = s.strip()
        if len(s) < 3 or len(s) > 80:
            return False
        if sum(c.isdigit() for c in s) > 3:
            return False
        pular_termos = ["cnpj", "cpf", "relatorio", "cadastro", "receita federal", "situação fiscal", "procurador", "emissão", "página", "data", "hora"]
        if any(t in s.lower() for t in pular_termos):
            return False
        return True

    for idx, line in enumerate(lines):
        cnpjs_found = cnpj_pattern.findall(line)
        cpfs_found = cpf_pattern.findall(line)
        
        docs_found = []
        for c in cnpjs_found:
            clean_c = "".join(filter(str.isdigit, c))
            if clean_c not in cnpjs_a_excluir:
                docs_found.append((clean_c, "CNPJ"))
        for c in cpfs_found:
            clean_c = "".join(filter(str.isdigit, c))
            if clean_c not in cnpjs_a_excluir:
                docs_found.append((clean_c, "CPF"))
                
        for doc, tipo in docs_found:
            nome_encontrado = None
            linha_limpa = line
            for raw_doc in (cnpjs_found + cpfs_found):
                linha_limpa = linha_limpa.replace(raw_doc, "")
            for label in ["Empresa:", "CNPJ/CPF:", "CNPJ:", "CPF:", "Nome:", "Cliente:", "Razão Social:", "Razao Social:"]:
                linha_limpa = re.sub(re.escape(label), "", linha_limpa, flags=re.IGNORECASE)
            linha_limpa = re.sub(r'[\s\-:;,/]+', ' ', linha_limpa).strip()
            
            if eh_nome_valido(linha_limpa):
                nome_encontrado = linha_limpa
                
            if not nome_encontrado:
                if idx - 1 >= 0:
                    prev_line = lines[idx - 1]
                    for label in ["Empresa:", "Nome:", "Cliente:", "Razão Social:", "Razao Social:"]:
                        prev_line = re.sub(re.escape(label), "", prev_line, flags=re.IGNORECASE)
                    prev_line = re.sub(r'[\s\-:;,/]+', ' ', prev_line).strip()
                    if eh_nome_valido(prev_line):
                        nome_encontrado = prev_line
            
            if not nome_encontrado:
                if idx + 1 < len(lines):
                    next_line = lines[idx + 1]
                    for label in ["Empresa:", "Nome:", "Cliente:", "Razão Social:", "Razao Social:"]:
                        next_line = re.sub(re.escape(label), "", next_line, flags=re.IGNORECASE)
                    next_line = re.sub(r'[\s\-:;,/]+', ' ', next_line).strip()
                    if eh_nome_valido(next_line):
                        nome_encontrado = next_line
                        
            if not nome_encontrado:
                nome_encontrado = f"Cliente {tipo} {doc[:4]}..."
                
            extracted[doc] = nome_encontrado.upper()
            
    return [{"cnpj": doc, "nome": nome} for doc, nome in extracted.items()]

# Rota para Importação Inteligente de Clientes (PDF/TXT)
@app.route("/api/clientes/importar", methods=["POST"])
def importar_clientes():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Nenhum arquivo enviado."}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "Nome do arquivo vazio."}), 400
        
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".txt")):
        return jsonify({"status": "error", "message": "O arquivo deve ser um PDF ou TXT."}), 400
        
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    ext = "pdf" if filename_lower.endswith(".pdf") else "txt"
    temp_path = os.path.join(temp_dir, f"importar_temp.{ext}")
    file.save(temp_path)
    
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    openai_key = config.get("openai_api_key", "").strip()
    
    try:
        text = ""
        if ext == "pdf":
            import pypdf
            reader = pypdf.PdfReader(temp_path)
            extracted_pages = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    extracted_pages.append(page_text)
            text = "\n".join(extracted_pages)
        else:
            try:
                with open(temp_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                with open(temp_path, "r", encoding="latin-1", errors="ignore") as f:
                    text = f.read()
                    
        if not text.strip():
            return jsonify({"status": "error", "message": "Não foi possível extrair nenhum texto do arquivo enviado."}), 400

        extracted_clients = None
        
        if openai_key:
            print("Tentando extrair clientes usando a OpenAI...")
            extracted_clients = extrair_clientes_openai(text, openai_key)
            if extracted_clients is not None:
                print(f"Extração via OpenAI concluída. Clientes encontrados: {len(extracted_clients)}")
            else:
                print("Extração via OpenAI falhou. Usando fallback de Heurística/Regex local.")
                
        if extracted_clients is None:
            print("Usando extração baseada em Heurística/Regex local...")
            extracted_clients = extrair_clientes_heuristica(text)
            print(f"Extração local concluída. Clientes encontrados: {len(extracted_clients)}")

        clientes_atuais = {}
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8-sig") as f_csv:
                r_csv = csv.DictReader(f_csv)
                for row in r_csv:
                    c = row.get("cnpj", "").strip()
                    n = row.get("nome", "").strip()
                    a = row.get("ativo", "True").strip()
                    if c:
                        clean_c = "".join(filter(str.isdigit, c))
                        clientes_atuais[clean_c] = {"nome": n, "ativo": a}
                        
        cnpjs_a_excluir = {
            "02241127000128", "38050811000170", "37115714000155",
            "38050753000184", "01599281000103", "37992979000131",
            "37993599000111", "02273061000158"
        }
        
        novos_contados = 0
        for item in extracted_clients:
            c = "".join(filter(str.isdigit, item.get("cnpj", "")))
            n = item.get("nome", "").strip().upper()
            
            if not c or len(c) not in [11, 14] or not n:
                continue
            if c in cnpjs_a_excluir:
                continue
                
            if c in clientes_atuais:
                if len(n) > len(clientes_atuais[c]["nome"]):
                    clientes_atuais[c]["nome"] = n
            else:
                clientes_atuais[c] = {"nome": n, "ativo": "True"}
                novos_contados += 1
                
        if "26470042000180" not in clientes_atuais:
            clientes_atuais["26470042000180"] = {"nome": "TOME & LOPES RESTAURANTE E LANCHONETE LTDA", "ativo": "True"}
        if "05443435000124" not in clientes_atuais:
            clientes_atuais["05443435000124"] = {"nome": "J&J SERVICOS PROFISSIONAIS LTDA", "ativo": "True"}
            
        with open(csv_path, "w", newline="", encoding="utf-8") as f_csv:
            writer_csv = csv.writer(f_csv)
            writer_csv.writerow(["cnpj", "nome", "ativo"])
            for c, data in clientes_atuais.items():
                writer_csv.writerow([c, data["nome"], data["ativo"]])
                
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return jsonify({
            "status": "success",
            "message": f"Importação concluída! {novos_contados} novos clientes adicionados. Total na base: {len(clientes_atuais)}."
        })
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"status": "error", "message": f"Erro ao processar arquivo: {str(e)}"}), 500

# Rotas de Execução da Automação
@app.route("/api/executar/iniciar", methods=["POST"])
def iniciar_automacao():
    global processo_automacao
    
    rodando, _ = is_process_running_by_script("executar.py")
    if rodando or (processo_automacao and processo_automacao.poll() is None):
        return jsonify({"status": "error", "message": "A automação já está em execução."}), 400
        
    dados = request.json or {}
    forcar_login = dados.get("forcar_login", False)
    forcar_todos = dados.get("forcar_todos", False)
    
    cmd = [sys.executable, "executar.py"]
    if forcar_login:
        cmd.append("--login")
    if forcar_todos:
        cmd.append("--forcar-todos")
        
    try:
        # Configurar startupinfo no Windows para evitar que o processo herde o estado oculto (SW_HIDE) da VBScript
        startupinfo = None
        creationflags = 0
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 1  # SW_SHOWNORMAL (1) - força as janelas (como o Chrome visível) a aparecerem
            creationflags = subprocess.CREATE_NEW_CONSOLE

        # Iniciar o subprocesso de forma assíncrona, redirecionando saídas para evitar deadlock
        processo_automacao = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        return jsonify({"status": "success", "message": "Automação iniciada com sucesso no servidor."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao iniciar o subprocesso: {str(e)}"}), 500

@app.route("/api/executar/parar", methods=["POST"])
def parar_automacao():
    global processo_automacao
    rodando, pids = is_process_running_by_script("executar.py")
    
    pids_to_kill = set(pids)
    if processo_automacao and processo_automacao.poll() is None:
        pids_to_kill.add(processo_automacao.pid)
        
    if pids_to_kill:
        try:
            for pid in pids_to_kill:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            processo_automacao = None
            return jsonify({"status": "success", "message": "Automação interrompida com sucesso!"})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao encerrar processo: {str(e)}"}), 500
    else:
        return jsonify({"status": "error", "message": "Nenhuma automação em execução no momento."}), 400

# Rotas de Execução para Consulta de Nota Fiscal XML
@app.route("/api/nota_fiscal_xml/iniciar", methods=["POST"])
def iniciar_nota_fiscal_xml():
    global processo_nota_fiscal_xml
    
    rodando, _ = is_process_running_by_script("consultar_nota_fiscal_xml.py")
    if rodando or (processo_nota_fiscal_xml and processo_nota_fiscal_xml.poll() is None):
        return jsonify({"status": "error", "message": "A consulta de Nota Fiscal XML já está em execução."}), 400
        
    dados = request.json or {}
    forcar_todos = dados.get("forcar_todos", False)
    
    cmd = [sys.executable, "consultar_nota_fiscal_xml.py", "--condominios"]
    if forcar_todos:
        cmd.append("--forcar-todos")
        
    try:
        startupinfo = None
        creationflags = 0
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 1
            creationflags = subprocess.CREATE_NEW_CONSOLE
            
        processo_nota_fiscal_xml = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        return jsonify({"status": "success", "message": "Consulta de Nota Fiscal XML iniciada com sucesso no servidor."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao iniciar o subprocesso: {str(e)}"}), 500
 
@app.route("/api/nota_fiscal_xml/parar", methods=["POST"])
def parar_nota_fiscal_xml():
    global processo_nota_fiscal_xml
    rodando, pids = is_process_running_by_script("consultar_nota_fiscal_xml.py")
    
    pids_to_kill = set(pids)
    if processo_nota_fiscal_xml and processo_nota_fiscal_xml.poll() is None:
        pids_to_kill.add(processo_nota_fiscal_xml.pid)
        
    if pids_to_kill:
        try:
            import subprocess
            # Fechar Chrome do perfil de Nota Fiscal XML antes do taskkill principal para liberar lock
            cmd_chrome = (
                'powershell -NoProfile -Command "'
                'Get-CimInstance Win32_Process -Filter \\"Name = \'chrome.exe\' or Name = \'chromedriver.exe\'\\" '
                '| Where-Object { $_.CommandLine -like \'*chrome_profile_nota_fiscal_xml*\' } '
                '| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
            )
            subprocess.run(cmd_chrome, shell=True, capture_output=True)
            
            for pid in pids_to_kill:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            processo_nota_fiscal_xml = None
            
            # Limpar SingletonLock
            lock_path = os.path.join("temp", "chrome_profile_nota_fiscal_xml", "SingletonLock")
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass
            return jsonify({"status": "success", "message": "Consulta de Nota Fiscal XML interrompida com sucesso!"})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao encerrar processo: {str(e)}"}), 500
    else:
        return jsonify({"status": "error", "message": "Nenhuma consulta de Nota Fiscal XML em execução no momento."}), 400
 
@app.route("/api/nota_fiscal_xml/status", methods=["GET"])
def obter_status_nota_fiscal_xml():
    global processo_nota_fiscal_xml
    rodando, _ = is_process_running_by_script("consultar_nota_fiscal_xml.py")
    if not rodando:
        rodando = processo_nota_fiscal_xml is not None and processo_nota_fiscal_xml.poll() is None
    
    state_file = "temp/state_nota_fiscal_xml.json"
    today = datetime.date.today().strftime("%Y-%m-%d")
    status_data = {
        "rodando": rodando,
        "empresa_atual": "Inativo",
        "total_clientes": 0,
        "processados": 0,
        "sucessos": 0,
        "falhas": 0,
        "logs": []
    }
    
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("data_consulta") == today:
                    status_data.update(data)
        except Exception:
            pass
            
    status_data["rodando"] = rodando
    if rodando and status_data["empresa_atual"] == "Inativo":
        status_data["empresa_atual"] = "Inicializando..."
    elif not rodando:
        status_data["empresa_atual"] = "Inativo"
        
    log_file = os.path.join("logs", f"nota_fiscal_xml_{today}.log")
    ultimo_log = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f_log:
                lines = f_log.readlines()
                ultimo_log = [line.strip() for line in lines[-150:]]
        except Exception:
            pass
    status_data["logs"] = ultimo_log
    
    return jsonify(status_data)

import threading

@app.route("/api/webhook/whatsapp", methods=["POST"])
def webhook_whatsapp():
    dados = request.json or {}
    
    # Processar de forma assíncrona para retornar 200 OK imediatamente para a Z-API (evita reenvios por timeout)
    def async_process():
        try:
            import agente_escavador
            config = load_config()
            rodando, _ = is_process_running_by_script("executar.py")
            if not rodando:
                rodando = processo_automacao is not None and processo_automacao.poll() is None
                
            rodando_nota_fiscal_xml, _ = is_process_running_by_script("consultar_nota_fiscal_xml.py")
            if not rodando_nota_fiscal_xml:
                rodando_nota_fiscal_xml = processo_nota_fiscal_xml is not None and processo_nota_fiscal_xml.poll() is None
            
            def iniciar_callback(forcar_todos=False):
                try:
                    from database_manager import DatabaseManager
                    db = DatabaseManager()
                    clientes_ativos = db.listar_clientes_ativos()
                    if not clientes_ativos:
                        return False
                    for c in clientes_ativos:
                        db.criar_job("e-cac", c["cnpj"], forcar_todos=forcar_todos)
                    return True
                except Exception as e:
                    print(f"Erro ao enfileirar e-CAC: {e}")
                    return False
                
            def parar_callback():
                global processo_automacao
                try:
                    from database_manager import DatabaseManager
                    db = DatabaseManager()
                    with db._get_connection() as conn:
                        conn.execute("UPDATE jobs SET status = 'erro', erro_mensagem = 'Cancelado pelo usuário' WHERE status = 'pendente'")
                        conn.commit()
                except Exception:
                    pass
                
                rodando_teste, pids = is_process_running_by_script("executar.py")
                pids_to_kill = set(pids)
                if processo_automacao and processo_automacao.poll() is None:
                    pids_to_kill.add(processo_automacao.pid)
                    
                if pids_to_kill:
                    try:
                        for pid in pids_to_kill:
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                        processo_automacao = None
                        return True
                    except Exception:
                        pass
                return False
 
            def iniciar_xml_callback(forcar_todos=False, destinatario=None, cliente_filtro=None):
                try:
                    from database_manager import DatabaseManager
                    db = DatabaseManager()
                    
                    if cliente_filtro:
                        filtro_limpo = "".join(filter(str.isdigit, cliente_filtro))
                        clientes_ativos = db.listar_clientes_ativos()
                        match_c = None
                        for cli in clientes_ativos:
                            if filtro_limpo and filtro_limpo in cli["cnpj"]:
                                match_c = cli
                                break
                            elif not filtro_limpo and cliente_filtro.lower() in cli["nome"].lower():
                                match_c = cli
                                break
                        if match_c:
                            db.criar_job("nfe_xml", match_c["cnpj"], forcar_todos=forcar_todos, destinatario=destinatario)
                            return True
                        return False
                    else:
                        clientes_ativos = db.listar_clientes_ativos()
                        enfileirados = 0
                        for c in clientes_ativos:
                            if c.get("pfx_path"):
                                db.criar_job("nfe_xml", c["cnpj"], forcar_todos=forcar_todos, destinatario=destinatario)
                                enfileirados += 1
                        return enfileirados > 0
                except Exception as e:
                    print(f"Erro ao enfileirar NFe: {e}")
                    return False
                
            def parar_xml_callback():
                global processo_nota_fiscal_xml
                try:
                    from database_manager import DatabaseManager
                    db = DatabaseManager()
                    with db._get_connection() as conn:
                        conn.execute("UPDATE jobs SET status = 'erro', erro_mensagem = 'Cancelado pelo usuário' WHERE status = 'pendente'")
                        conn.commit()
                except Exception:
                    pass
                
                rodando_teste, pids = is_process_running_by_script("consultar_nota_fiscal_xml.py")
                
                # Fechar Chrome do perfil de Nota Fiscal XML e outros perfis de condomínios
                try:
                    cmd_chrome = (
                        'powershell -NoProfile -Command "'
                        'Get-CimInstance Win32_Process -Filter \\"Name = \'chrome.exe\' or Name = \'chromedriver.exe\'\\" '
                        '| Where-Object { $_.CommandLine -like \'*chrome_profile_nota_fiscal_xml*\' or $_.CommandLine -like \'*chrome_profile_1*\' or $_.CommandLine -like \'*chrome_profile_2*\' or $_.CommandLine -like \'*chrome_profile_3*\' or $_.CommandLine -like \'*chrome_profile_4*\' or $_.CommandLine -like \'*chrome_profile_5*\' or $_.CommandLine -like \'*chrome_profile_6*\' or $_.CommandLine -like \'*chrome_profile_7*\' or $_.CommandLine -like \'*chrome_profile_8*\' or $_.CommandLine -like \'*chrome_profile_9*\' or $_.CommandLine -like \'*chrome_profile_0*\' } '
                        '| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
                    )
                    subprocess.run(cmd_chrome, shell=True, capture_output=True)
                except Exception:
                    pass
                
                pids_to_kill = set(pids)
                if processo_nota_fiscal_xml and processo_nota_fiscal_xml.poll() is None:
                    pids_to_kill.add(processo_nota_fiscal_xml.pid)
                    
                if pids_to_kill:
                    try:
                        for pid in pids_to_kill:
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                        processo_nota_fiscal_xml = None
                        return True
                    except Exception:
                        pass
                return False
                
            agente_escavador.processar_mensagem_recebida(
                payload=dados,
                config=config,
                rodando_atualmente=rodando,
                iniciar_callback=iniciar_callback,
                parar_callback=parar_callback,
                iniciar_xml_callback=iniciar_xml_callback,
                parar_xml_callback=parar_xml_callback,
                processo_xml_ativo=rodando_nota_fiscal_xml
            )
        except Exception as e:
            print(f"Erro no processamento assíncrono do webhook: {e}")
            
    threading.Thread(target=async_process, daemon=True).start()
    return jsonify({"status": "received"}), 200

@app.route("/api/executar/status", methods=["GET"])
def obter_status():
    global processo_automacao
    rodando, _ = is_process_running_by_script("executar.py")
    if not rodando:
        rodando = processo_automacao is not None and processo_automacao.poll() is None
    
    today = datetime.date.today().strftime("%Y-%m-%d")
    log_file = os.path.join("logs", f"execucao_{today}.log")
    
    ultimo_log = []
    processando_empresa = ""
    sucessos = 0
    falhas = 0
    pendentes = 0
    total_ativos = 0
    
    # 1. Carregar lista de clientes ativos do CSV
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f_csv:
                reader = csv.DictReader(f_csv)
                for row in reader:
                    ativo = row.get("ativo", "True").strip().lower() in ["true", "1", "yes", "ativo", "sim", "s"]
                    if ativo:
                        total_ativos += 1
        except Exception:
            pass
            
    # 2. Ler status.json do mês corrente nas pastas de relatórios e filtrar por hoje para estatísticas diárias
    relatorios_dir = config.get("relatorios_dir", "relatorios")
    if os.path.exists(relatorios_dir):
        # Encontra todos os arquivos status.json diretamente na raiz da pasta de cada cliente
        status_files = glob.glob(os.path.join(relatorios_dir, "*", "status.json"))
        for s_file in status_files:
            try:
                with open(s_file, "r", encoding="utf-8") as f_status:
                    data = json.load(f_status)
                    # Apenas computar se a data de consulta for hoje
                    if data.get("data_consulta") == today:
                        status_c = data.get("status", "")
                        if status_c == "Sucesso":
                            sucessos += 1
                        elif status_c == "Erro":
                            falhas += 1
                        elif status_c == "Pendente":
                            pendentes += 1
                            # Se houver um pendente ativo, essa é a empresa que está rodando no momento
                            processando_empresa = data.get("nome", "")
            except Exception:
                pass

    # 3. Ler logs recentes
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f_log:
                # Ler no máximo as últimas 150 linhas para o console web
                lines = f_log.readlines()
                ultimo_log = [line.strip() for line in lines[-150:]]
                
                # Se não identificamos a empresa atual via status.json Pendente, podemos procurar o último "Processando Cliente: " no log
                if not processando_empresa:
                    for line in reversed(lines):
                        if "Processando Cliente:" in line:
                            parts = line.split("Processando Cliente:")
                            if len(parts) > 1:
                                processando_empresa = parts[1].split("(")[0].strip()
                                break
        except Exception:
            pass

    # 4. Ajustar contagem se nenhum status.json foi criado mas o robô está ativo
    progresso_atual = sucessos + falhas
    
    return jsonify({
        "rodando": rodando,
        "empresa_atual": processando_empresa or ("Aguardando início..." if rodando else "Inativo"),
        "total_clientes": total_ativos,
        "processados": progresso_atual,
        "sucessos": sucessos,
        "falhas": falhas,
        "pendentes": pendentes,
        "logs": ultimo_log
    })

# Rotas de Relatórios e Downloads
def migrar_pastas_relatorios(relatorios_dir, csv_path):
    if not os.path.exists(relatorios_dir) or not os.path.exists(csv_path):
        return
    clientes = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                c = row.get("cnpj", "").strip()
                n = row.get("nome", "").strip()
                if c and n:
                    clientes.append({"cnpj": c, "nome": n})
    except Exception as e:
        print(f"Erro na migração ao carregar clientes: {e}")
        return

    def clean_filename(name):
        return "".join(c if c.isalnum() or c in " _-ÇçÁáÉéÍíÓóÚúÃãÕõÂâÊêÔôÀàÜü" else "_" for c in name).strip()

    for c in clientes:
        cnpj_limpo = "".join(filter(str.isdigit, c["cnpj"]))
        nome_limpo = clean_filename(c["nome"])
        
        caminho_antigo = os.path.join(relatorios_dir, nome_limpo)
        caminho_novo = os.path.join(relatorios_dir, f"{cnpj_limpo}_{nome_limpo}")
        
        if os.path.exists(caminho_antigo) and not os.path.exists(caminho_novo):
            try:
                shutil.move(caminho_antigo, caminho_novo)
                print(f"[MIGRAÇÃO] Pasta renomeada: {caminho_antigo} -> {caminho_novo}")
            except Exception as e:
                print(f"[MIGRAÇÃO] Erro ao mover {caminho_antigo}: {e}")

@app.route("/api/relatorios", methods=["GET"])
def listar_relatorios():
    config = load_config()
    relatorios_dir = config.get("relatorios_dir", "relatorios")
    csv_path = config.get("clientes_file", "clientes.csv")
    
    # Rodar migração de pastas
    migrar_pastas_relatorios(relatorios_dir, csv_path)
    
    relatorios_list = []
    
    # 1. Adicionar o Painel Consolidado do Desktop
    desktop_excel = os.path.join(os.path.expanduser("~"), "Desktop", "Painel_Consolidado_Pendencias_eCAC.xlsx")
    if os.path.exists(desktop_excel):
        try:
            size = os.path.getsize(desktop_excel)
            mtime = os.path.getmtime(desktop_excel)
            dt_mod = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
            relatorios_list.append({
                "nome": "Painel_Consolidado_Pendencias_eCAC.xlsx",
                "caminho": "desktop/Painel_Consolidado_Pendencias_eCAC.xlsx",
                "tamanho": f"{size / 1024:.1f} KB",
                "data_mod": dt_mod,
                "empresa": "Geral (Consolidado J&J)",
                "data_pasta": "N/A",
                "tipo": "excel",
                "cnpj": ""
            })
        except Exception:
            pass

    # 2. Varrer recursivamente a pasta relatorios/
    if os.path.exists(relatorios_dir):
        for root, dirs, files in os.walk(relatorios_dir):
            for file in files:
                # Ignorar status.json, arquivos temporários
                if file.endswith(".json") or file.endswith(".tmp"):
                    continue
                    
                filepath = os.path.join(root, file)
                try:
                    size = os.path.getsize(filepath)
                    mtime = os.path.getmtime(filepath)
                    dt_mod = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                    
                    # Obter caminho relativo
                    rel_path = os.path.relpath(filepath, relatorios_dir)
                    parts = rel_path.split(os.sep)
                    
                    # Ignorar arquivos na raiz de relatorios_dir (como consolidados antigos)
                    if len(parts) <= 1:
                        continue
                        
                    empresa_raw = parts[0]
                    # data_pasta é gerada dinamicamente a partir do ano-mês de modificação física do arquivo (usando os.path.getmtime)
                    data_pasta = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m")
                    
                    # Separar CNPJ e Nome da pasta no formato {cnpj}_{nome}
                    cnpj = ""
                    empresa = empresa_raw
                    if "_" in empresa_raw:
                        cnpj_parte, nome_parte = empresa_raw.split("_", 1)
                        if cnpj_parte.isdigit() and len(cnpj_parte) in [11, 14]:
                            cnpj = cnpj_parte
                            empresa = nome_parte.replace("_", " ").strip()
                    
                    if not cnpj:
                        empresa = empresa.replace("_", " ").strip()
                        
                    caminho_web = "relatorio/" + rel_path.replace('\\', '/')
                    relatorios_list.append({
                        "nome": file,
                        "caminho": caminho_web,
                        "tamanho": f"{size / (1024 * 1024):.2f} MB" if size > 1024*1024 else f"{size / 1024:.1f} KB",
                        "data_mod": dt_mod,
                        "empresa": empresa,
                        "data_pasta": data_pasta,
                        "tipo": "excel" if file.endswith(".xlsx") else "pdf" if file.endswith(".pdf") else "imagem" if file.endswith(".png") else "texto" if file.endswith(".txt") else "outro",
                        "cnpj": cnpj
                    })
                except Exception:
                    pass
                    
    # Ordenar por data de modificação decrescente
    try:
        relatorios_list.sort(key=lambda x: x["data_mod"], reverse=True)
    except Exception:
        pass
        
    return jsonify(relatorios_list)

@app.route("/api/nota_fiscal_xml/relatorios", methods=["GET"])
def listar_relatorios_nota_fiscal_xml():
    relatorios_list = []
    
    # 1. Adicionar o Painel Consolidado do Desktop
    desktop_excel = os.path.join(os.path.expanduser("~"), "Desktop", "nota_fiscal_xml.xlsx")
    if os.path.exists(desktop_excel):
        try:
            size = os.path.getsize(desktop_excel)
            mtime = os.path.getmtime(desktop_excel)
            dt_mod = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
            relatorios_list.append({
                "nome": "nota_fiscal_xml.xlsx",
                "caminho": "desktop/nota_fiscal_xml.xlsx",
                "tamanho": f"{size / 1024:.1f} KB",
                "data_mod": dt_mod,
                "empresa": "Geral (Consolidado Nota Fiscal XML)",
                "data_pasta": "N/A",
                "tipo": "excel",
                "cnpj": ""
            })
        except Exception:
            pass
            
    # 2. Varrer recursivamente a pasta documentos de nota fiscal xml/
    target_dir = "documentos de nota fiscal xml"
    if os.path.exists(target_dir):
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".json") or file.endswith(".tmp"):
                    continue
                    
                filepath = os.path.join(root, file)
                try:
                    size = os.path.getsize(filepath)
                    mtime = os.path.getmtime(filepath)
                    dt_mod = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                    
                    # Obter caminho relativo
                    rel_path = os.path.relpath(filepath, target_dir)
                    parts = rel_path.split(os.sep)
                    
                    if len(parts) <= 1:
                        continue
                        
                    empresa_raw = parts[0]
                    data_pasta = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m")
                    
                    cnpj = ""
                    empresa = empresa_raw
                    if "_" in empresa_raw:
                        cnpj_parte, nome_parte = empresa_raw.split("_", 1)
                        if cnpj_parte.isdigit() and len(cnpj_parte) in [11, 14]:
                            cnpj = cnpj_parte
                            empresa = nome_parte.replace("_", " ").strip()
                            
                    if not cnpj:
                        empresa = empresa.replace("_", " ").strip()
                        
                    caminho_web = "nota_fiscal_xml/" + rel_path.replace('\\', '/')
                    relatorios_list.append({
                        "nome": file,
                        "caminho": caminho_web,
                        "tamanho": f"{size / (1024 * 1024):.2f} MB" if size > 1024*1024 else f"{size / 1024:.1f} KB",
                        "data_mod": dt_mod,
                        "empresa": empresa,
                        "data_pasta": data_pasta,
                        "tipo": "excel" if file.endswith(".xlsx") else "xml" if file.endswith(".xml") else "pdf" if file.endswith(".pdf") else "imagem" if file.endswith(".png") else "texto" if file.endswith(".txt") else "outro",
                        "cnpj": cnpj
                    })
                except Exception:
                    pass
                    
    # Ordenar por data de modificação decrescente
    try:
        relatorios_list.sort(key=lambda x: x["data_mod"], reverse=True)
    except Exception:
        pass
        
    return jsonify(relatorios_list)

@app.route("/api/relatorios/download/<path:caminho_completo>", methods=["GET"])
def baixar_relatorio(caminho_completo):
    config = load_config()
    
    # Se o caminho for do desktop para e-CAC
    if caminho_completo == "desktop/Painel_Consolidado_Pendencias_eCAC.xlsx":
        try:
            from rebuild_utils import rebuild_ecac_consolidated_sheet
            rebuild_ecac_consolidated_sheet(config)
        except Exception as e_rebuild:
            print(f"Erro ao regenerar consolidado e-CAC antes do download: {e_rebuild}")
            
        desktop_excel = os.path.join(os.path.expanduser("~"), "Desktop", "Painel_Consolidado_Pendencias_eCAC.xlsx")
        if os.path.exists(desktop_excel):
            return send_file(desktop_excel, as_attachment=True)
        else:
            return jsonify({"status": "error", "message": "Arquivo consolidado e-CAC não encontrado no Desktop."}), 404

    # Se o caminho for do desktop para Nota Fiscal XML
    if caminho_completo == "desktop/nota_fiscal_xml.xlsx":
        try:
            from rebuild_utils import rebuild_xml_consolidated_sheet
            rebuild_xml_consolidated_sheet(config)
        except Exception as e_rebuild:
            print(f"Erro ao regenerar consolidado NF-e XML antes do download: {e_rebuild}")
            
        desktop_excel = os.path.join(os.path.expanduser("~"), "Desktop", "nota_fiscal_xml.xlsx")
        if os.path.exists(desktop_excel):
            return send_file(desktop_excel, as_attachment=True)
        else:
            # Fallback para o arquivo no diretório raiz do projeto
            if os.path.exists("nota_fiscal_xml.xlsx"):
                return send_file("nota_fiscal_xml.xlsx", as_attachment=True)
            return jsonify({"status": "error", "message": "Arquivo consolidado Nota Fiscal XML não encontrado."}), 404
            
    # Se for da pasta de relatórios
    if caminho_completo.startswith("relatorio/"):
        relatorios_dir = config.get("relatorios_dir", "relatorios")
        caminho_rel = caminho_completo.replace("relatorio/", "")
        
        # Validar segurança de caminho (evitar directory traversal)
        abs_relatorios = os.path.abspath(relatorios_dir)
        abs_target = os.path.abspath(os.path.join(relatorios_dir, caminho_rel))
        
        if not abs_target.startswith(abs_relatorios):
            return jsonify({"status": "error", "message": "Acesso não autorizado."}), 403
            
        if os.path.exists(abs_target):
            return send_file(abs_target, as_attachment=True)
        else:
            return jsonify({"status": "error", "message": "Arquivo de relatório não encontrado."}), 404
 
    # Se for da pasta de nota fiscal xml
    if caminho_completo.startswith("nota_fiscal_xml/"):
        target_dir = "documentos de nota fiscal xml"
        caminho_rel = caminho_completo.replace("nota_fiscal_xml/", "")
        
        abs_nota_fiscal_xml = os.path.abspath(target_dir)
        abs_target = os.path.abspath(os.path.join(target_dir, caminho_rel))
        
        if not abs_target.startswith(abs_nota_fiscal_xml):
            return jsonify({"status": "error", "message": "Acesso não autorizado."}), 403
            
        if os.path.exists(abs_target):
            return send_file(abs_target, as_attachment=True)
        else:
            return jsonify({"status": "error", "message": "Arquivo de Nota Fiscal XML não encontrado."}), 404
            
    return jsonify({"status": "error", "message": "Caminho de download inválido."}), 400

# Funções de Gerenciamento do Sub-serviço Node do WhatsApp
def liberar_porta_3000():
    try:
        import subprocess
        # Comando para encontrar PIDs escutando na porta 3000 no Windows
        cmd_find = "netstat -ano | findstr :3000"
        output = subprocess.check_output(cmd_find, shell=True).decode('utf-8', errors='ignore')
        pids = set()
        for line in output.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 5:
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0:
                    pids.add(int(pid))
        
        for pid in pids:
            print(f"Liberando porta 3000: Terminando processo com PID {pid}...")
            # Usar taskkill no Windows de forma silenciosa e forçada (/F /T)
            subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True)
    except Exception:
        # Ignora se não houver processos na porta 3000 ou se o comando falhar
        pass

def iniciar_gateway_whatsapp():
    global processo_gateway
    if processo_gateway and processo_gateway.poll() is None:
        return
        
    # Liberar a porta 3000 para evitar conflitos de processos órfãos
    liberar_porta_3000()
        
    print("Iniciando sub-serviço Node.js do WhatsApp Gateway...")
    cmd = ["node", os.path.join("whatsapp_gateway", "gateway.js")]
    
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
        os.makedirs("logs", exist_ok=True)
        log_file = open(os.path.join("logs", "gateway_node.log"), "a", encoding="utf-8", buffering=1)
        
        processo_gateway = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            cwd=os.getcwd(),
            startupinfo=startupinfo
        )
        print("Sub-serviço Node.js do WhatsApp Gateway iniciado com sucesso.")
    except Exception as e:
        print(f"Falha ao iniciar sub-serviço Node.js do WhatsApp: {e}")

def parar_gateway_whatsapp():
    global processo_gateway
    if processo_gateway and processo_gateway.poll() is None:
        print("Encerrando sub-serviço Node.js do WhatsApp Gateway...")
        try:
            if os.name == 'nt':
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(processo_gateway.pid)], capture_output=True)
            else:
                processo_gateway.terminate()
            print("Sub-serviço Node.js do WhatsApp Gateway encerrado.")
        except Exception as e:
            print(f"Erro ao encerrar sub-serviço Node.js do WhatsApp: {e}")
        processo_gateway = None

import atexit
atexit.register(parar_gateway_whatsapp)

# Endpoints de Proxy para o WhatsApp Gateway local
@app.route("/api/whatsapp/status", methods=["GET"])
def api_whatsapp_status():
    try:
        response = requests.get("http://127.0.0.1:3000/api/status", timeout=5)
        return jsonify(response.json())
    except Exception:
        return jsonify({"status": "disconnected", "error": "Gateway offline"})

@app.route("/api/whatsapp/qr", methods=["GET"])
def api_whatsapp_qr():
    try:
        response = requests.get("http://127.0.0.1:3000/api/qr", timeout=5)
        return jsonify(response.json())
    except Exception:
        return jsonify({"qr": None, "status": "disconnected", "error": "Gateway offline"})

@app.route("/api/whatsapp/desconectar", methods=["POST"])
def api_whatsapp_desconectar():
    try:
        response = requests.post("http://127.0.0.1:3000/api/disconnect", timeout=10)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao desconectar: {str(e)}"}), 500

if __name__ == "__main__":
    # Garantir auto-kill de processos filhos no encerramento (Job Object)
    assign_current_process_to_job_object()
    
    # Garantir que a pasta de logs e templates exista
    os.makedirs("logs", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    # Abrir navegador automaticamente exatamente uma vez (mesmo com reloader de debug)
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        import webbrowser
        try:
            webbrowser.open("http://127.0.0.1:5000")
        except Exception as e:
            print(f"Não foi possível abrir o navegador automaticamente: {e}")
            
    # Iniciar o gateway Node e o túnel SSH (executado apenas uma vez no processo ativo)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        try:
            iniciar_gateway_whatsapp()
        except Exception as e:
            print(f"Erro ao iniciar o gateway WhatsApp: {e}")
            
        try:
            import tunnel_manager
            tunnel_manager.start()
        except Exception as e:
            print(f"Erro ao iniciar o túnel de webhook: {e}")
            
        try:
            import threading
            import worker_pool
            threading.Thread(target=worker_pool.iniciar_worker_pool, daemon=True).start()
            print("[SYSTEM] Worker Pool do Escavador iniciado com sucesso em background.")
        except Exception as e:
            print(f"Erro ao iniciar o Worker Pool: {e}")

    # Iniciar servidor local
    print("Iniciando Painel Web local na porta 5000...")
    app.run(host="127.0.0.1", port=5000, debug=True)
# Recarrega o gateway e inicializa o node do whatsapp com suporte a LID cache
