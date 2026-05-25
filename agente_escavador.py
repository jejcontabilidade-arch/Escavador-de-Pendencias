import os
import re
import csv
import json
import glob
import datetime
import base64
import requests

def log(msg, level="AGENTE"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def enviar_mensagem_whatsapp(mensagem, config):
    if not config.get("whatsapp_enabled"):
        return False
        
    instance = config.get("whatsapp_zapi_instance")
    token = config.get("whatsapp_zapi_token")
    number = config.get("whatsapp_number")
    client_token = config.get("whatsapp_zapi_client_token")
    
    if not instance or not token or not number:
        log("Erro: Configurações de WhatsApp incompletas para envio.", "ERROR")
        return False
        
    number_clean = "".join(filter(str.isdigit, number))
    if not number_clean.startswith("55") and len(number_clean) in [10, 11]:
        number_clean = "55" + number_clean
        
    url = f"https://api.z-api.io/instances/{instance}/token/{token}/send-text"
    headers = {"Content-Type": "application/json"}
    if client_token:
        headers["Client-Token"] = client_token
        
    payload = {
        "phone": number_clean,
        "message": mensagem
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        return response.status_code in [200, 201]
    except Exception as e:
        log(f"Erro ao enviar mensagem via Z-API: {e}", "ERROR")
        return False

def enviar_documento_whatsapp(caminho_arquivo, nome_arquivo, config):
    if not config.get("whatsapp_enabled"):
        return False
        
    instance = config.get("whatsapp_zapi_instance")
    token = config.get("whatsapp_zapi_token")
    number = config.get("whatsapp_number")
    client_token = config.get("whatsapp_zapi_client_token")
    
    if not instance or not token or not number:
        return False
        
    number_clean = "".join(filter(str.isdigit, number))
    if not number_clean.startswith("55") and len(number_clean) in [10, 11]:
        number_clean = "55" + number_clean
        
    # Determinar mime-type por extensão
    ext = os.path.splitext(nome_arquivo)[1].lower()
    mime = "application/octet-stream"
    if ext == ".pdf":
        mime = "application/pdf"
    elif ext == ".xlsx":
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == ".txt":
        mime = "text/plain"
    elif ext == ".png":
        mime = "image/png"
        
    try:
        with open(caminho_arquivo, "rb") as f:
            base64_content = base64.b64encode(f.read()).decode("utf-8")
            
        document_payload = f"data:{mime};base64,{base64_content}"
        
        url = f"https://api.z-api.io/instances/{instance}/token/{token}/send-document"
        headers = {"Content-Type": "application/json"}
        if client_token:
            headers["Client-Token"] = client_token
            
        payload = {
            "phone": number_clean,
            "document": document_payload,
            "fileName": nome_arquivo
        }
        
        log(f"Enviando documento '{nome_arquivo}' ({ext}) via Z-API...")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code in [200, 201]:
            log(f"Documento '{nome_arquivo}' enviado com sucesso!", "SUCCESS")
            return True
        else:
            log(f"Falha ao enviar documento Z-API. Status: {response.status_code}, Resposta: {response.text}", "ERROR")
            return False
    except Exception as e:
        log(f"Erro ao enviar documento via Z-API: {e}", "ERROR")
        return False

def obter_status_resumo(config, rodando_atualmente):
    today = datetime.date.today().strftime("%Y-%m-%d")
    sucessos = 0
    falhas = 0
    pendentes = 0
    total_ativos = 0
    empresa_atual = ""
    
    # Clientes ativos
    csv_path = config.get("clientes_file", "clientes.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("ativo", "True").strip().lower() in ["true", "1", "yes", "ativo", "sim", "s"]:
                        total_ativos += 1
        except Exception:
            pass
            
    # Status dos relatórios
    relatorios_dir = config.get("relatorios_dir", "relatorios")
    if os.path.exists(relatorios_dir):
        status_files = glob.glob(os.path.join(relatorios_dir, "*", "status.json"))
        for s_file in status_files:
            try:
                with open(s_file, "r", encoding="utf-8") as f_status:
                    data = json.load(f_status)
                    if data.get("data_consulta") == today:
                        st = data.get("status", "")
                        if st == "Sucesso":
                            sucessos += 1
                        elif st == "Erro":
                            falhas += 1
                        elif st == "Pendente":
                            pendentes += 1
                            empresa_atual = data.get("nome", "")
            except Exception:
                pass
                
    status_str = "🟢 EM EXECUÇÃO" if rodando_atualmente else "🔴 INATIVO"
    resumo = (
        f"🤖 *STATUS DA VARREDURA e-CAC*\n\n"
        f"• *Estado do Robô*: {status_str}\n"
        f"• *Total de Clientes*: {total_ativos}\n"
        f"• *Sucessos Hoje*: {sucessos}\n"
        f"• *Falhas Hoje*: {falhas}\n"
    )
    
    if rodando_atualmente:
        resumo += f"• *Processando agora*: {empresa_atual or 'Iniciando Fila...'}\n"
        
    return resumo

def listar_clientes_por_status(config, st_procurado):
    today = datetime.date.today().strftime("%Y-%m-%d")
    relatorios_dir = config.get("relatorios_dir", "relatorios")
    clientes_list = []
    
    if os.path.exists(relatorios_dir):
        status_files = glob.glob(os.path.join(relatorios_dir, "*", "status.json"))
        for s_file in status_files:
            try:
                with open(s_file, "r", encoding="utf-8") as f_status:
                    data = json.load(f_status)
                    if data.get("data_consulta") == today:
                        if data.get("status") == st_procurado:
                            clientes_list.append(f" - {data.get('nome')} ({data.get('cnpj')})")
            except Exception:
                pass
                
    titulo = "Lista de Clientes OK (Sucesso)" if st_procurado == "Sucesso" else "Lista de Clientes Pendentes/Com Erros"
    if not clientes_list:
        return f"🤖 *{titulo}*:\nNenhum cliente registrado sob este status hoje."
        
    return f"🤖 *{titulo}*:\n" + "\n".join(clientes_list)

def localizar_e_enviar_documento(nome_pesquisa, config):
    relatorios_dir = config.get("relatorios_dir", "relatorios")
    if not os.path.exists(relatorios_dir):
        return "Diretório de relatórios não encontrado."
        
    # Sanitizar nome da busca
    busca_term = nome_pesquisa.strip().lower()
    if len(busca_term) < 3:
        return "Por favor, digite um nome de empresa com pelo menos 3 caracteres para a busca."
        
    pastas = [d for d in os.listdir(relatorios_dir) if os.path.isdir(os.path.join(relatorios_dir, d))]
    pasta_selecionada = None
    
    # 1. Tentar encontrar pasta contendo o termo de busca
    for p in pastas:
        if busca_term in p.lower():
            pasta_selecionada = p
            break
            
    if not pasta_selecionada:
        return f"❌ Cliente '{nome_pesquisa}' não localizado nas pastas de relatórios do sistema."
        
    caminho_pasta = os.path.join(relatorios_dir, pasta_selecionada)
    
    # 2. Varrer arquivos na pasta do cliente
    arquivos = glob.glob(os.path.join(caminho_pasta, "*.*"))
    if not arquivos:
        return f"A pasta do cliente '{pasta_selecionada}' está vazia no momento."
        
    # Priorizar PDF (Certidão > Relatório)
    arquivos_ordenados = []
    for arq in arquivos:
        nome_arq = os.path.basename(arq)
        if nome_arq.endswith(".json"):
            continue
            
        peso = 0
        if "certidao" in nome_arq.lower():
            peso = 3
        elif "relatorio" in nome_arq.lower():
            peso = 2
        elif nome_arq.endswith(".pdf"):
            peso = 1
            
        arquivos_ordenados.append((peso, os.path.getmtime(arq), arq))
        
    if not arquivos_ordenados:
        return f"Nenhum arquivo elegível (PDF, Excel ou Texto) localizado para '{pasta_selecionada}'."
        
    # Ordenar por peso decrescente, e depois por data de modificação decrescente
    arquivos_ordenados.sort(key=lambda x: (x[0], x[1]), reverse=True)
    caminho_final = arquivos_ordenados[0][2]
    nome_final = os.path.basename(caminho_final)
    
    # Enviar documento
    enviado = enviar_documento_whatsapp(caminho_final, nome_final, config)
    if enviado:
        return f"✅ Envei o documento '{nome_final}' para o seu chat!"
    else:
        return f"❌ Falha ao enviar o documento '{nome_final}' via WhatsApp. Verifique as configurações da Z-API."

def interpretar_mensagem_com_gpt(texto_mensagem, config):
    openai_key = config.get("openai_api_key", "").strip()
    if not openai_key:
        # Fallback se não tiver chave OpenAI
        log("OpenAI API Key não encontrada no config_private.json. Usando interpretador Heurístico.", "WARNING")
        return interpretar_mensagem_heuristica(texto_mensagem)
        
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}"
    }
    
    prompt = """Você é o Agente Escavador, o assistente virtual inteligente da J&J Contabilidade que controla o sistema de automação e-CAC.
O usuário é o Willian, administrador do sistema.
Sua tarefa é analisar a mensagem do usuário, deduzir sua intenção operacional e gerar uma resposta em linguagem natural que seja extremamente humana, amigável, natural e adequada ao contexto.

As intenções suportadas são:
1. "iniciar_varredura" (Iniciar varredura comum do dia, ignorando quem já deu sucesso)
2. "iniciar_varredura_total" (Forçar escavação completa de todos os clientes do início)
3. "interromper_varredura" (Interromper ou parar a execução ativa do robô)
4. "obter_status" (Consultar status atual, progresso e logs do robô)
5. "listar_clientes_ok" (Consultar lista de clientes com sucesso hoje)
6. "listar_clientes_pendentes_erro" (Consultar lista de clientes com falhas ou pendentes hoje)
7. "baixar_documento" (Baixar ou obter a certidão/relatório de um cliente específico. Requer o parâmetro 'empresa')
8. "conversa_casual" (Outro tipo de mensagem, dúvidas gerais sobre o sistema ou saudações)

Retorne estritamente um JSON no seguinte formato (sem formatação markdown ou blocos de código):
{
  "intencao": "uma das intenções acima",
  "empresa": "nome ou cnpj da empresa se a intenção for baixar_documento, senão nulo",
  "resposta_humana": "uma resposta humana, amigável e profissional em português para o Willian, confirmando o que você vai fazer ou respondendo a dúvida dele de forma natural e empática"
}
"""
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": texto_mensagem}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            log(f"Erro OpenAI API: {response.text}", "ERROR")
            return interpretar_mensagem_heuristica(texto_mensagem)
    except Exception as e:
        log(f"Erro de conexão com OpenAI: {e}", "ERROR")
        return interpretar_mensagem_heuristica(texto_mensagem)

def interpretar_mensagem_heuristica(texto):
    t = texto.strip().lower()
    
    # Heurística simples
    if "parar" in t or "interromper" in t or "para" in t or "cancela" in t:
        return {"intencao": "interromper_varredura", "empresa": None, "resposta_humana": None}
    elif "status" in t or "como esta" in t or "como está" in t or "progresso" in t or "log" in t:
        return {"intencao": "obter_status", "empresa": None, "resposta_humana": None}
    elif "todos" in t or "completo" in t or "forçar todos" in t or "do inicio" in t:
        return {"intencao": "iniciar_varredura_total", "empresa": None, "resposta_humana": None}
    elif "iniciar" in t or "começar" in t or "rodar" in t or "executar" in t:
        return {"intencao": "iniciar_varredura", "empresa": None, "resposta_humana": None}
    elif "inadimplente" in t or "falha" in t or "erro" in t or "pendente" in t:
        return {"intencao": "listar_clientes_pendentes_erro", "empresa": None, "resposta_humana": None}
    elif "ok" in t or "sucesso" in t or "regular" in t:
        return {"intencao": "listar_clientes_ok", "empresa": None, "resposta_humana": None}
    elif "cnd" in t or "certidao" in t or "documento" in t or "relatorio" in t or "manda" in t or "envia" in t:
        # Extrair potencial nome de empresa da frase
        palavras = texto.split()
        empresa = None
        if len(palavras) > 1:
            # Pega as palavras após o comando básico
            empresa = " ".join(palavras[1:])
        return {"intencao": "baixar_documento", "empresa": empresa, "resposta_humana": None}
    else:
        return {
            "intencao": "conversa_casual", 
            "empresa": None, 
            "resposta_humana": "Olá! Sou o Agente Escavador da J&J Contabilidade. Consigo entender comandos como 'Iniciar varredura', 'Como está o status?', 'Lista de erros', 'Lista de sucessos', 'Parar automação' ou 'Me mande a certidão de [Nome da Empresa]'."
        }

def processar_mensagem_recebida(payload, config, rodando_atualmente, iniciar_callback, parar_callback):
    # 1. Validar se o remetente é o número autorizado
    # A Z-API envia o número no payload em 'phone'
    sender_phone = payload.get("phone", "")
    sender_clean = "".join(filter(str.isdigit, sender_phone))
    
    auth_number = config.get("whatsapp_number", "")
    auth_clean = "".join(filter(str.isdigit, auth_number))
    
    if not auth_clean:
        log("Alerta: Nenhum número autorizado cadastrado no config_private.json ('whatsapp_number').", "WARNING")
        return False
        
    # Verificar se as strings terminam com os mesmos dígitos (para ignorar prefixos como 55, etc.)
    if not sender_clean.endswith(auth_clean) and not auth_clean.endswith(sender_clean):
        log(f"Mensagem recebida de número não autorizado ({sender_clean}). Ignorando por segurança.", "SECURITY")
        return False
        
    # 2. Extrair texto da mensagem
    # Z-API coloca o texto em text.message
    message_obj = payload.get("text", {})
    texto_mensagem = message_obj.get("message", "").strip()
    
    if not texto_mensagem:
        return False
        
    log(f"Mensagem recebida do usuário autorizado: '{texto_mensagem}'")
    
    # 3. Chamar interpretador NLP
    res = interpretar_mensagem_com_gpt(texto_mensagem, config)
    intencao = res.get("intencao")
    empresa = res.get("empresa")
    resposta_humana = res.get("resposta_humana")
    
    log(f"Intenção detectada: '{intencao}' (Empresa: '{empresa}')")
    
    # 4. Executar a Intenção
    # Sempre enviar a resposta humana da IA primeiro se ela existir (para dar um tom natural e conversacional)
    if resposta_humana:
        enviar_mensagem_whatsapp(resposta_humana, config)
        
    if intencao == "iniciar_varredura":
        if rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 O robô já está executando uma varredura no momento.", config)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 *Entendido!* Estou iniciando a varredura inteligente comum agora em segundo plano. Vou te notificar do andamento.", config)
            iniciar_callback(forcar_todos=False)
            
    elif intencao == "iniciar_varredura_total":
        if rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 O robô já está executando uma varredura. Interrompa a atual se quiser reiniciar do zero.", config)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 *Entendido!* Estou iniciando a varredura completa (forçando todos) agora em segundo plano. Isso pode levar mais tempo.", config)
            iniciar_callback(forcar_todos=True)
            
    elif intencao == "interromper_varredura":
        if not rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 Nenhuma varredura ativa para interromper no momento.", config)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🔴 *Parada Forçada:* Estou parando a automação e encerrando todos os navegadores abertos no servidor...", config)
            parar_callback()
            enviar_mensagem_whatsapp("✅ Automação interrompida e limpa com sucesso!", config)
            
    elif intencao == "obter_status":
        resumo = obter_status_resumo(config, rodando_atualmente)
        enviar_mensagem_whatsapp(resumo, config)
        
    elif intencao == "listar_clientes_ok":
        lista = listar_clientes_por_status(config, "Sucesso")
        enviar_mensagem_whatsapp(lista, config)
        
    elif intencao == "listar_clientes_pendentes_erro":
        lista = listar_clientes_por_status(config, "Erro")
        enviar_mensagem_whatsapp(lista, config)
        
    elif intencao == "baixar_documento":
        if not empresa:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 Por favor, informe o nome do cliente. Exemplo: 'Me mande a certidão da Tome & Lopes'.", config)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp(f"🔍 Buscando arquivos fiscais de *{empresa}*...", config)
            msg_resposta = localizar_e_enviar_documento(empresa, config)
            enviar_mensagem_whatsapp(msg_resposta, config)
            
    elif intencao == "conversa_casual":
        if not resposta_humana:
            enviar_mensagem_whatsapp("🤖 Não consegui entender seu comando. Tente dizer 'iniciar varredura' ou 'status'.", config)
            
    return True
