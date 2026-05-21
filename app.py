import os
import sys
import json
import csv
import glob
import datetime
import subprocess
import shutil
import requests
from flask import Flask, render_template, jsonify, request, send_file, send_from_directory

app = Flask(__name__)

# Variáveis globais para gerenciar o subprocesso da automação
processo_automacao = None

def load_config():
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "headless": False,
        "timeout_ms": 30000,
        "relatorios_dir": "relatorios",
        "clientes_file": "clientes.csv",
        "portal_url": "https://cav.receita.fazenda.gov.br/ecac/",
        "cert_first_char": "J",
        "download_timeout_ms": 60000,
        "whatsapp_enabled": False,
        "whatsapp_number": "",
        "whatsapp_zapi_instance": "",
        "whatsapp_zapi_token": "",
        "whatsapp_zapi_client_token": ""
    }

def save_config(config):
    config_path = "config.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erro ao salvar config.json: {e}")
        return False

# Rota principal para a Interface Web
@app.route("/")
def index():
    return render_template("index.html")

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

# Rota para testar o envio de WhatsApp via Z-API
@app.route("/api/config/testar-whatsapp", methods=["POST"])
def testar_whatsapp():
    dados = request.json or {}
    instance = dados.get("whatsapp_zapi_instance")
    token = dados.get("whatsapp_zapi_token")
    number = dados.get("whatsapp_number")
    client_token = dados.get("whatsapp_zapi_client_token")
    
    if not instance or not token or not number:
        return jsonify({"status": "error", "message": "Instância, Token e Número do WhatsApp são obrigatórios para o teste."}), 400
        
    number_clean = "".join(filter(str.isdigit, number))
    if not number_clean.startswith("55") and len(number_clean) in [10, 11]:
        number_clean = "55" + number_clean
        
    url = f"https://api.z-api.io/instances/{instance}/token/{token}/send-text"
    headers = {"Content-Type": "application/json"}
    if client_token:
        headers["Client-Token"] = client_token
        
    payload = {
        "phone": number_clean,
        "message": "🤖 *Escavador de Pendências e-CAC*\n\nEste é um teste de comunicação da integração Z-API enviado pelo Painel de Controle Web. Configuração validada com sucesso!"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            return jsonify({"status": "success", "message": "Mensagem de teste enviada com sucesso!"})
        else:
            return jsonify({"status": "error", "message": f"Erro Z-API ({response.status_code}): {response.text}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro de conexão com a Z-API: {str(e)}"}), 500

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
    
    if not cnpj or len(cnpj) != 14:
        return jsonify({"status": "error", "message": "CNPJ inválido. Deve conter 14 dígitos."}), 400
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
                    c = row.get("cnpj", "").strip()
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
    if not cnpj or len(cnpj) != 14:
        return jsonify({"status": "error", "message": "CNPJ inválido."}), 400
        
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    
    clientes = []
    encontrado = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    c = row.get("cnpj", "").strip()
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
    if not cnpj or len(cnpj) != 14:
        return jsonify({"status": "error", "message": "CNPJ inválido."}), 400
        
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    
    clientes = []
    encontrado = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    c = row.get("cnpj", "").strip()
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

# Rota para Importação de PDF
@app.route("/api/clientes/importar-pdf", methods=["POST"])
def importar_pdf():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Nenhum arquivo enviado."}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "Nome do arquivo vazio."}), 400
        
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"status": "error", "message": "O arquivo deve ser um PDF."}), 400
        
    # Salvar temporariamente
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, "importar_temp.pdf")
    file.save(temp_path)
    
    config = load_config()
    csv_path = config.get("clientes_file", "clientes.csv")
    
    try:
        import pypdf
        reader = pypdf.PdfReader(temp_path)
        extracted_companies = {}
        
        for page in reader.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            company_name = None
            cnpj = None
            
            for idx, line in enumerate(lines):
                if "Código Nome Admissão Vcto" in line or "Código Nome Admissão" in line:
                    if idx + 1 < len(lines):
                        company_name = lines[idx + 1]
                if "Empresa: CNPJ/CPF:" in line:
                    parts = line.split("Empresa: CNPJ/CPF:")
                    if len(parts) > 1:
                        raw_cnpj = parts[1].strip()
                        cnpj = "".join(filter(str.isdigit, raw_cnpj))
                        
            if company_name and cnpj:
                company_name = company_name.replace("Emissão:", "").strip()
                if cnpj not in extracted_companies or len(company_name) > len(extracted_companies[cnpj]):
                    extracted_companies[cnpj] = company_name
                    
        # CNPJs de exemplo a excluir do PDF
        cnpjs_a_excluir = {
            "02241127000128", "38050811000170", "37115714000155",
            "38050753000184", "01599281000103", "37992979000131",
            "37993599000111", "02273061000158"
        }
        
        # Carregar clientes existentes
        clientes_atuais = {}
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8-sig") as f_csv:
                r_csv = csv.DictReader(f_csv)
                for row in r_csv:
                    c = row.get("cnpj", "").strip()
                    n = row.get("nome", "").strip()
                    a = row.get("ativo", "True").strip()
                    if c:
                        clientes_atuais[c] = {"nome": n, "ativo": a}
                        
        # Mesclar novos clientes extraídos do PDF
        novos_contados = 0
        for c, n in extracted_companies.items():
            if c in cnpjs_a_excluir:
                continue
            if c in clientes_atuais:
                # Atualiza nome se o extraído for maior
                if len(n) > len(clientes_atuais[c]["nome"]):
                    clientes_atuais[c]["nome"] = n
            else:
                clientes_atuais[c] = {"nome": n, "ativo": "True"}
                novos_contados += 1
                
        # Garantir Tome & Lopes e JEJ
        if "26470042000180" not in clientes_atuais:
            clientes_atuais["26470042000180"] = {"nome": "TOME & LOPES RESTAURANTE E LANCHONETE LTDA", "ativo": "True"}
        if "05443435000124" not in clientes_atuais:
            clientes_atuais["05443435000124"] = {"nome": "J&J SERVICOS PROFISSIONAIS LTDA", "ativo": "True"}
            
        # Gravar de volta no CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f_csv:
            writer_csv = csv.writer(f_csv)
            writer_csv.writerow(["cnpj", "nome", "ativo"])
            for c, data in clientes_atuais.items():
                writer_csv.writerow([c, data["nome"], data["ativo"]])
                
        # Limpar arquivo temporário
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return jsonify({
            "status": "success",
            "message": f"Importação concluída! {novos_contados} novos clientes adicionados. Total na base: {len(clientes_atuais)}."
        })
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"status": "error", "message": f"Erro ao processar PDF: {str(e)}"}), 500

# Rotas de Execução da Automação
@app.route("/api/executar/iniciar", methods=["POST"])
def iniciar_automacao():
    global processo_automacao
    
    if processo_automacao and processo_automacao.poll() is None:
        return jsonify({"status": "error", "message": "A automação já está em execução."}), 400
        
    dados = request.json or {}
    forcar_login = dados.get("forcar_login", False)
    
    cmd = [sys.executable, "executar.py"]
    if forcar_login:
        cmd.append("--login")
        
    try:
        # Iniciar o subprocesso de forma assíncrona, redirecionando saídas para evitar deadlock
        processo_automacao = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd()
        )
        return jsonify({"status": "success", "message": "Automação iniciada com sucesso no servidor."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao iniciar o subprocesso: {str(e)}"}), 500

@app.route("/api/executar/parar", methods=["POST"])
def parar_automacao():
    global processo_automacao
    if processo_automacao and processo_automacao.poll() is None:
        try:
            # Taskkill força a interrupção da árvore de processos, fechando o Chrome e drivers do Playwright
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(processo_automacao.pid)], capture_output=True)
            processo_automacao = None
            return jsonify({"status": "success", "message": "Automação interrompida com sucesso!"})
        except Exception as e:
            try:
                processo_automacao.terminate()
                processo_automacao = None
                return jsonify({"status": "success", "message": "Sinal de encerramento enviado."})
            except Exception as ex:
                return jsonify({"status": "error", "message": f"Erro ao encerrar processo: {str(ex)}"}), 500
    else:
        return jsonify({"status": "error", "message": "Nenhuma automação em execução no momento."}), 400

@app.route("/api/executar/status", methods=["GET"])
def obter_status():
    global processo_automacao
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
        current_month = datetime.date.today().strftime("%Y-%m")
        # Encontra todos os arquivos status.json na pasta do mês corrente
        status_files = glob.glob(os.path.join(relatorios_dir, "*", current_month, "status.json"))
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
@app.route("/api/relatorios", methods=["GET"])
def listar_relatorios():
    config = load_config()
    relatorios_dir = config.get("relatorios_dir", "relatorios")
    relatorios_list = []
    
    # 1. Adicionar o Painel Consolidado do Desktop
    desktop_excel = r"C:\Users\jejco\Desktop\Painel_Consolidado_Pendencias_eCAC.xlsx"
    if os.path.exists(desktop_excel):
        try:
            size = os.path.getsize(desktop_excel)
            mtime = os.path.getmtime(desktop_excel)
            dt_mod = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
            relatorios_list.append({
                "nome": "Painel_Consolidado_Pendencias_eCAC.xlsx",
                "caminho": "desktop/Painel_Consolidado_Pendencias_eCAC.xlsx",
                "tamanho": f"{size / (1024):.1f} KB",
                "data_mod": dt_mod,
                "empresa": "Geral (Consolidado J&J)",
                "data_pasta": "N/A",
                "tipo": "excel"
            })
        except Exception:
            pass

    # 2. Varrer recursivamente a pasta relatorios/
    if os.path.exists(relatorios_dir):
        for root, dirs, files in os.walk(relatorios_dir):
            for file in files:
                # Ignorar status.json, screenshots e arquivos que não sejam PDF ou Excel
                if file == "status.json" or file.endswith(".png") or file.endswith(".tmp"):
                    continue
                    
                filepath = os.path.join(root, file)
                try:
                    size = os.path.getsize(filepath)
                    mtime = os.path.getmtime(filepath)
                    dt_mod = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                    
                    # Obter caminho relativo
                    rel_path = os.path.relpath(filepath, relatorios_dir)
                    parts = rel_path.split(os.sep)
                    
                    empresa = parts[0] if len(parts) > 0 else "Outros"
                    data_pasta = parts[1] if len(parts) > 1 else "N/A"
                    
                    caminho_web = "relatorio/" + rel_path.replace('\\', '/')
                    relatorios_list.append({
                        "nome": file,
                        "caminho": caminho_web,
                        "tamanho": f"{size / (1024 * 1024):.2f} MB" if size > 1024*1024 else f"{size / 1024:.1f} KB",
                        "data_mod": dt_mod,
                        "empresa": empresa,
                        "data_pasta": data_pasta,
                        "tipo": "excel" if file.endswith(".xlsx") else "pdf" if file.endswith(".pdf") else "outro"
                    })
                except Exception:
                    pass
                    
    # Ordenar por data de modificação decrescente
    try:
        # Converter string da data de volta para datetime para ordenação correta se possível,
        # ou apenas ordenar por string invertida
        relatorios_list.sort(key=lambda x: x["data_mod"], reverse=True)
    except Exception:
        pass
        
    return jsonify(relatorios_list)

@app.route("/api/relatorios/download/<path:caminho_completo>", methods=["GET"])
def baixar_relatorio(caminho_completo):
    config = load_config()
    
    # Se o caminho for do desktop
    if caminho_completo == "desktop/Painel_Consolidado_Pendencias_eCAC.xlsx":
        desktop_excel = r"C:\Users\jejco\Desktop\Painel_Consolidado_Pendencias_eCAC.xlsx"
        if os.path.exists(desktop_excel):
            return send_file(desktop_excel, as_attachment=True)
        else:
            return jsonify({"status": "error", "message": "Arquivo consolidado não encontrado no Desktop."}), 404
            
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
            
    return jsonify({"status": "error", "message": "Caminho de download inválido."}), 400

if __name__ == "__main__":
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
            
    # Iniciar servidor local
    print("Iniciando Painel Web local na porta 5000...")
    app.run(host="127.0.0.1", port=5000, debug=True)
