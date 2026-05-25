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

def enviar_mensagem_whatsapp(mensagem, config, destinatario=None):
    if not config.get("whatsapp_enabled"):
        return False
        
    number = destinatario or config.get("whatsapp_number")
    if not number:
        log("Erro: Número de telefone do WhatsApp não configurado.", "ERROR")
        return False
        
    url = "http://127.0.0.1:3000/api/send-message"
    payload = {
        "to": number,
        "message": mensagem
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.status_code in [200, 201]
    except Exception as e:
        log(f"Erro ao enviar mensagem via gateway local: {e}", "ERROR")
        return False

def enviar_documento_whatsapp(caminho_arquivo, nome_arquivo, config, destinatario=None):
    if not config.get("whatsapp_enabled"):
        return False
        
    number = destinatario or config.get("whatsapp_number")
    if not number:
        return False
        
    try:
        with open(caminho_arquivo, "rb") as f:
            base64_content = base64.b64encode(f.read()).decode("utf-8")
            
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
            
        document_payload = f"data:{mime};base64,{base64_content}"
        
        url = "http://127.0.0.1:3000/api/send-document"
        payload = {
            "to": number,
            "document": document_payload,
            "fileName": nome_arquivo
        }
        
        log(f"Enviando documento '{nome_arquivo}' ({ext}) via gateway local...")
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            log(f"Documento '{nome_arquivo}' enviado com sucesso!", "SUCCESS")
            return True
        else:
            log(f"Falha ao enviar documento. Status: {response.status_code}, Resposta: {response.text}", "ERROR")
            return False
    except Exception as e:
        log(f"Erro ao enviar documento via gateway local: {e}", "ERROR")
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

def localizar_e_enviar_documento(nome_pesquisa, config, destinatario=None):
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
    enviado = enviar_documento_whatsapp(caminho_final, nome_final, config, destinatario)
    if enviado:
        return f"✅ Envei o documento '{nome_final}' para o seu chat!"
    else:
        return f"❌ Falha ao enviar o documento '{nome_final}' via WhatsApp. Verifique as configurações da Z-API."

def adicionar_novo_cliente_csv(cnpj, nome, config):
    csv_path = config.get("clientes_file", "clientes.csv")
    cnpj_clean = "".join(filter(str.isdigit, cnpj))
    nome_clean = nome.strip().upper()
    
    # 1. Verificar se o cliente já existe
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_cnpj = "".join(filter(str.isdigit, row.get("cnpj", "")))
                    if row_cnpj == cnpj_clean:
                        return f"O cliente '{nome_clean}' com CNPJ/CPF {cnpj_clean} já está cadastrado no sistema!"
        except Exception as e:
            log(f"Erro ao ler clientes.csv: {e}", "ERROR")
            
    # 2. Adicionar o cliente
    try:
        # Abre o arquivo para append
        # Verifica se termina com newline para não colar na linha anterior
        has_newline = True
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            with open(csv_path, "rb") as f_bin:
                f_bin.seek(-1, os.SEEK_END)
                last_char = f_bin.read(1)
                has_newline = last_char in [b'\n', b'\r']
                
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            if not has_newline:
                f.write("\n")
            writer = csv.writer(f)
            writer.writerow([cnpj_clean, nome_clean, "True"])
        log(f"Cliente {nome_clean} ({cnpj_clean}) adicionado com sucesso ao CSV.", "SUCCESS")
        return f"✅ *Cliente adicionado com sucesso!*\n• *Nome:* {nome_clean}\n• *CNPJ/CPF:* {cnpj_clean}\n• *Status:* Ativo"
    except Exception as e:
        log(f"Erro ao adicionar cliente no CSV: {e}", "ERROR")
        return f"❌ Erro ao adicionar o cliente no arquivo do sistema: {e}"

def carregar_contatos_autorizados():
    contatos = []
    csv_path = "autorizados.csv"
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    num = row.get("whatsapp_number", "").strip()
                    nome = row.get("nome", "").strip()
                    perm = row.get("permissao", "operador").strip().lower()
                    if num:
                        contatos.append({
                            "whatsapp_number": "".join(filter(str.isdigit, num)),
                            "nome": nome,
                            "permissao": perm
                        })
        except Exception as e:
            log(f"Erro ao ler autorizados.csv: {e}", "ERROR")
    return contatos

def verificar_permissao_numero(numero, config):
    if not numero:
        return None
        
    num_clean = "".join(filter(str.isdigit, numero))
    contatos = carregar_contatos_autorizados()
    
    for c in contatos:
        c_num = c["whatsapp_number"]
        if (num_clean == c_num) or num_clean.endswith(c_num) or c_num.endswith(num_clean):
            return c
        if len(num_clean) >= 8 and len(c_num) >= 8:
            if num_clean[-8:] == c_num[-8:]:
                return c
                
    auth_number = config.get("whatsapp_number", "")
    auth_clean = "".join(filter(str.isdigit, auth_number))
    if auth_clean:
        if (num_clean == auth_clean) or num_clean.endswith(auth_clean) or auth_clean.endswith(num_clean):
            return {"whatsapp_number": auth_clean, "nome": "Willian Administrador", "permissao": "admin"}
        if len(num_clean) >= 8 and len(auth_clean) >= 8:
            if num_clean[-8:] == auth_clean[-8:]:
                return {"whatsapp_number": auth_clean, "nome": "Willian Administrador", "permissao": "admin"}
                
    return None

def interpretar_mensagem_com_gpt(texto_mensagem, config, usuario_nome="Usuário", usuario_role="operador"):
    openai_key = config.get("openai_api_key", "").strip()
    if not openai_key:
        log("OpenAI API Key não encontrada no config_private.json. Usando interpretador Heurístico.", "WARNING")
        return interpretar_mensagem_heuristica(texto_mensagem)
        
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}"
    }
    
    prompt = f"""Você é o Agente Escavador, o assistente virtual inteligente da J&J Contabilidade que controla o sistema de automação e-CAC.
O usuário atual que está interagindo com você é o '{usuario_nome}' com o papel de '{usuario_role}'.
Sua tarefa é analisar a mensagem do usuário, deduzir sua intenção operacional e gerar uma resposta em linguagem natural que seja extremamente humana, amigável, natural e adequada ao contexto.

As intenções suportadas são:
1. "iniciar_varredura" (Iniciar varredura comum do dia, ignorando quem já deu sucesso. Restrito a administradores e operadores)
2. "iniciar_varredura_total" (Forçar escavação completa de todos os clientes do início. Restrito a administradores)
3. "interromper_varredura" (Interromper ou parar a execução ativa do robô. Restrito a administradores)
4. "obter_status" (Consultar status atual, progresso e logs do robô. Permitido a todos)
5. "listar_clientes_ok" (Consultar lista de clientes com sucesso hoje. Permitido a todos)
6. "listar_clientes_pendentes_erro" (Consultar lista de clientes com falhas ou pendentes hoje. Permitido a todos)
7. "baixar_documento" (Baixar ou obter a certidão/relatório de um cliente específico. Requer o parâmetro 'empresa')
8. "adicionar_cliente" (Adicionar um novo cliente/empresa ao sistema. Requer o nome completo em 'empresa' e o CNPJ/CPF em 'cnpj'. Restrito a administradores e operadores)
9. "conversa_casual" (Outro tipo de mensagem, saudações ou dúvidas gerais)

Retorne estritamente um JSON no seguinte formato (sem formatação markdown ou blocos de código):
{{
  "intencao": "uma das intenções acima",
  "empresa": "nome ou cnpj da empresa se a intenção for baixar_documento, ou o nome completo se for adicionar_cliente, senão nulo",
  "cnpj": "o CNPJ ou CPF do cliente (apenas números) se a intenção for adicionar_cliente, senão nulo",
  "resposta_humana": "uma resposta humana, amigável e profissional em português para o {usuario_nome}, confirmando o que você vai fazer ou respondendo de forma natural e empática"
}}
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
        return {"intencao": "interromper_varredura", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "status" in t or "como esta" in t or "como está" in t or "progresso" in t or "log" in t:
        return {"intencao": "obter_status", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "todos" in t or "completo" in t or "forçar todos" in t or "do inicio" in t:
        return {"intencao": "iniciar_varredura_total", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "iniciar" in t or "começar" in t or "rodar" in t or "executar" in t:
        return {"intencao": "iniciar_varredura", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "inadimplente" in t or "falha" in t or "erro" in t or "pendente" in t:
        return {"intencao": "listar_clientes_pendentes_erro", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "ok" in t or "sucesso" in t or "regular" in t:
        return {"intencao": "listar_clientes_ok", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "adicionar" in t or "cadastrar" in t or "novo cliente" in t or "inserir" in t:
        # Extrair potencial CNPJ/CPF da mensagem (apenas dígitos)
        numeros = "".join(filter(str.isdigit, texto))
        cnpj = numeros if len(numeros) in [11, 14] else None
        
        # Tentar extrair nome (tudo que não é verbo/número)
        palavras = [p for p in texto.split() if not p.isdigit()]
        empresa = None
        if len(palavras) > 2:
            empresa = " ".join(palavras[2:]) if "novo" in palavras else " ".join(palavras[1:])
        return {"intencao": "adicionar_cliente", "empresa": empresa, "cnpj": cnpj, "resposta_humana": None}
    elif "cnd" in t or "certidao" in t or "documento" in t or "relatorio" in t or "manda" in t or "envia" in t:
        # Extrair potencial nome de empresa da frase
        palavras = texto.split()
        empresa = None
        if len(palavras) > 1:
            # Pega as palavras após o comando básico
            empresa = " ".join(palavras[1:])
        return {"intencao": "baixar_documento", "empresa": empresa, "cnpj": None, "resposta_humana": None}
    else:
        return {
            "intencao": "conversa_casual", 
            "empresa": None, 
            "cnpj": None,
            "resposta_humana": "Olá! Sou o Agente Escavador da J&J Contabilidade. Consigo entender comandos como 'Iniciar varredura', 'Como está o status?', 'Lista de erros', 'Lista de sucessos', 'Parar automação' ou 'Me mande a certidão de [Nome da Empresa]'."
        }

def processar_mensagem_recebida(payload, config, rodando_atualmente, iniciar_callback, parar_callback):
    sender_phone = payload.get("phone", "")
    if not sender_phone:
        return False
        
    sender_clean = "".join(filter(str.isdigit, sender_phone))
    usuario = verificar_permissao_numero(sender_clean, config)
    
    if not usuario:
        log(f"Mensagem recebida de número não autorizado ({sender_clean}). Ignorando por segurança.", "SECURITY")
        enviar_mensagem_whatsapp(
            "Olá! Sou o Agente Escavador da J&J Contabilidade. 🔒 Este canal de atendimento é privado para operadores e agentes autorizados da empresa. Se você faz parte da equipe, solicite seu cadastro ao administrador.",
            config,
            destinatario=sender_clean
        )
        return False
        
    usuario_nome = usuario["nome"]
    usuario_role = usuario["permissao"]
    
    message_obj = payload.get("text", {})
    texto_mensagem = message_obj.get("message", "").strip()
    
    if not texto_mensagem:
        return False
        
    log(f"Mensagem recebida de {usuario_nome} ({usuario_role}): '{texto_mensagem}'")
    
    res = interpretar_mensagem_com_gpt(texto_mensagem, config, usuario_nome, usuario_role)
    intencao = res.get("intencao")
    empresa = res.get("empresa")
    cnpj = res.get("cnpj")
    resposta_humana = res.get("resposta_humana")
    
    log(f"Intenção detectada: '{intencao}' (Empresa: '{empresa}', CNPJ: '{cnpj}')")
    
    # Restrições de papel
    restrito_admin = ["interromper_varredura", "iniciar_varredura_total"]
    restrito_admin_operador = ["iniciar_varredura", "adicionar_cliente"]
    
    if usuario_role == "agente":
        if intencao in restrito_admin or intencao in restrito_admin_operador:
            enviar_mensagem_whatsapp(
                f"🤖 Olá {usuario_nome}. Ação '{intencao}' recusada. Como um Agente de IA, você não possui permissão para comandar a infraestrutura da automação. Permissões limitadas a consultas.",
                config,
                destinatario=sender_clean
            )
            return False
            
    elif usuario_role == "operador":
        if intencao in restrito_admin:
            enviar_mensagem_whatsapp(
                f"🤖 Desculpe, {usuario_nome}. Ação '{intencao}' recusada. Ações administrativas estão disponíveis apenas para o administrador.",
                config,
                destinatario=sender_clean
            )
            return False
            
    # Executar a Intenção
    if resposta_humana:
        enviar_mensagem_whatsapp(resposta_humana, config, destinatario=sender_clean)
        
    if intencao == "iniciar_varredura":
        if rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 O robô já está executando uma varredura no momento.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 *Entendido!* Estou iniciando a varredura inteligente comum agora em segundo plano. Vou te notificar do andamento.", config, destinatario=sender_clean)
            iniciar_callback(forcar_todos=False)
            
    elif intencao == "iniciar_varredura_total":
        if rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 O robô já está executando uma varredura. Interrompa a atual se quiser reiniciar do zero.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 *Entendido!* Estou iniciando a varredura completa (forçando todos) agora em segundo plano. Isso pode levar mais tempo.", config, destinatario=sender_clean)
            iniciar_callback(forcar_todos=True)
            
    elif intencao == "interromper_varredura":
        if not rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 Nenhuma varredura ativa para interromper no momento.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🔴 *Parada Forçada:* Estou parando a automação e encerrando todos os navegadores abertos no servidor...", config, destinatario=sender_clean)
            parar_callback()
            enviar_mensagem_whatsapp("✅ Automação interrompida e limpa com sucesso!", config, destinatario=sender_clean)
            
    elif intencao == "obter_status":
        resumo = obter_status_resumo(config, rodando_atualmente)
        enviar_mensagem_whatsapp(resumo, config, destinatario=sender_clean)
        
    elif intencao == "listar_clientes_ok":
        lista = listar_clientes_por_status(config, "Sucesso")
        enviar_mensagem_whatsapp(lista, config, destinatario=sender_clean)
        
    elif intencao == "listar_clientes_pendentes_erro":
        lista = listar_clientes_por_status(config, "Erro")
        enviar_mensagem_whatsapp(lista, config, destinatario=sender_clean)
        
    elif intencao == "baixar_documento":
        if not empresa:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 Por favor, informe o nome do cliente. Exemplo: 'Me mande a certidão da Tome & Lopes'.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp(f"🔍 Buscando arquivos fiscais de *{empresa}*...", config, destinatario=sender_clean)
            msg_resposta = localizar_e_enviar_documento(empresa, config, destinatario=sender_clean)
            enviar_mensagem_whatsapp(msg_resposta, config, destinatario=sender_clean)
            
    elif intencao == "adicionar_cliente":
        if not empresa or not cnpj:
            msg_erro = f"🤖 {usuario_nome}, para cadastrar o novo cliente preciso do *Nome Completo* e também do *CNPJ ou CPF*. Pode me enviar novamente com essas informações?"
            enviar_mensagem_whatsapp(msg_erro, config, destinatario=sender_clean)
        else:
            resultado = adicionar_novo_cliente_csv(cnpj, empresa, config)
            enviar_mensagem_whatsapp(resultado, config, destinatario=sender_clean)
            
    elif intencao == "conversa_casual":
        if not resposta_humana:
            enviar_mensagem_whatsapp("🤖 Não consegui entender seu comando. Tente dizer 'iniciar varredura' ou 'status'.", config, destinatario=sender_clean)
            
    return True
