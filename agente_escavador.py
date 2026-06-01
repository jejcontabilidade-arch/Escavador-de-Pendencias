import os
import time
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
        elif ext == ".xml":
            mime = "application/xml"
            
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

def obter_status_resumo_nfe(config, processo_xml_ativo):
    state_file = "temp/state_nota_fiscal_xml.json"
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    rodando = processo_xml_ativo
    empresa_atual = ""
    total = 0
    processados = 0
    sucessos = 0
    falhas = 0
    
    # Tenta carregar dados do arquivo de estado
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("data_consulta") == today:
                    total = data.get("total_clientes", 0)
                    processados = data.get("processados", 0)
                    sucessos = data.get("sucessos", 0)
                    falhas = data.get("falhas", 0)
                    empresa_atual = data.get("empresa_atual", "")
        except Exception:
            pass
            
    # Se não houver arquivo de estado ou for antigo, tenta contar a partir de clientes.csv
    if total == 0:
        csv_path = config.get("clientes_file", "clientes.csv")
        if os.path.exists(csv_path):
            try:
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("ativo", "True").strip().lower() in ["true", "1", "yes", "ativo", "sim", "s"]:
                            total += 1
            except Exception:
                pass
                
    status_str = "🟢 EM EXECUÇÃO" if rodando else "🔴 INATIVO"
    resumo = (
        f"🤖 *STATUS DA CONSULTA NF-e XML*\n\n"
        f"• *Estado do Robô*: {status_str}\n"
        f"• *Total de Clientes*: {total}\n"
        f"• *Processados*: {processados}\n"
        f"• *Sucessos Hoje*: {sucessos}\n"
        f"• *Falhas Hoje*: {falhas}\n"
    )
    
    if rodando:
        resumo += f"• *Processando agora*: {empresa_atual or 'Inicializando...'}\n"
        
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

def localizar_e_enviar_documento(nome_pesquisa, config, destinatario=None, apenas_xml=False):
    # Sanitizar nome da busca
    busca_term = nome_pesquisa.strip().lower()
    if len(busca_term) < 3:
        return "Por favor, digite um nome de empresa com pelo menos 3 caracteres para a busca."
        
    relatorios_dir = config.get("relatorios_dir", "relatorios")
    xml_dir = "documentos de nota fiscal xml"
    
    if apenas_xml:
        # Busca focada apenas na pasta de XMLs de Notas Fiscais
        pastas_candidatas = []
        if os.path.exists(xml_dir):
            for d in os.listdir(xml_dir):
                if os.path.isdir(os.path.join(xml_dir, d)) and busca_term in d.lower():
                    pastas_candidatas.append((os.path.join(xml_dir, d), d))
                    
        if not pastas_candidatas:
            return f"❌ Não localizei nenhuma pasta de Notas Fiscais XML para o cliente '{nome_pesquisa}'. Deseja que eu inicie uma busca agora no portal nacional da NF-e para este cliente? (Diga: 'iniciar busca de nota para {nome_pesquisa}')"
            
        xmls_encontrados = []
        for caminho_pasta, nome_pasta in pastas_candidatas:
            arquivos = glob.glob(os.path.join(caminho_pasta, "*.xml"))
            for arq in arquivos:
                xmls_encontrados.append((os.path.getmtime(arq), arq))
                
        if not xmls_encontrados:
            return f"❌ Não encontrei nenhum arquivo de nota fiscal (.xml) para o cliente '{nome_pesquisa}'. Deseja iniciar uma busca? (Diga: 'iniciar busca de nota para {nome_pesquisa}')"
            
        # Ordenar por data de modificação decrescente (mais recentes primeiro)
        xmls_encontrados.sort(key=lambda x: x[0], reverse=True)
        
        # Enviar até os 5 XMLs mais recentes para não sobrecarregar
        qtd_enviar = min(len(xmls_encontrados), 5)
        enviados = 0
        for i in range(qtd_enviar):
            arq_path = xmls_encontrados[i][1]
            nome_arq = os.path.basename(arq_path)
            if enviar_documento_whatsapp(arq_path, nome_arq, config, destinatario):
                enviados += 1
                time.sleep(1.0)
                
        if enviados > 0:
            return f"✅ Enviei {enviados} nota(s) fiscal(is) XML mais recente(s) de '{nome_pesquisa}' para o seu chat!"
        else:
            return f"❌ Falha ao enviar as notas fiscais de '{nome_pesquisa}' via WhatsApp. Verifique as configurações do gateway."
            
    # Caso geral (e-CAC ou busca padrão)
    # Encontrar pastas candidatas em ambos os diretórios
    pastas_candidatas = []
    if os.path.exists(relatorios_dir):
        for d in os.listdir(relatorios_dir):
            if os.path.isdir(os.path.join(relatorios_dir, d)) and busca_term in d.lower():
                pastas_candidatas.append((os.path.join(relatorios_dir, d), d, "e-CAC"))
                
    if os.path.exists(xml_dir):
        for d in os.listdir(xml_dir):
            if os.path.isdir(os.path.join(xml_dir, d)) and busca_term in d.lower():
                pastas_candidatas.append((os.path.join(xml_dir, d), d, "XML/NF-e"))
                
    if not pastas_candidatas:
        return f"❌ Cliente '{nome_pesquisa}' não localizado nas pastas de relatórios ou de notas fiscais do sistema."
        
    arquivos_ordenados = []
    for caminho_pasta, nome_pasta, tipo_origem in pastas_candidatas:
        arquivos = glob.glob(os.path.join(caminho_pasta, "*.*"))
        for arq in arquivos:
            nome_arq = os.path.basename(arq)
            if nome_arq.endswith(".json") or nome_arq.endswith(".tmp"):
                continue
                
            peso = 0
            if "certidao" in nome_arq.lower() or "cnd" in nome_arq.lower():
                peso = 4
            elif "relatorio" in nome_arq.lower():
                peso = 3
            elif nome_arq.endswith(".pdf"):
                peso = 2
            elif nome_arq.endswith(".xml"):
                peso = 1
                
            arquivos_ordenados.append((peso, os.path.getmtime(arq), arq, tipo_origem))
            
    if not arquivos_ordenados:
        return f"A pasta de documentos do cliente está vazia no momento."
        
    # Ordenar por data de modificação decrescente, e depois por peso decrescente
    arquivos_ordenados.sort(key=lambda x: (x[0], x[1]), reverse=True)
    caminho_final = arquivos_ordenados[0][2]
    nome_final = os.path.basename(caminho_final)
    tipo_origem = arquivos_ordenados[0][3]
    
    # Enviar documento
    enviado = enviar_documento_whatsapp(caminho_final, nome_final, config, destinatario)
    if enviado:
        return f"✅ Enviei o documento '{nome_final}' ({tipo_origem}) para o seu chat!"
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

def normalizar_numero(num):
    if not num:
        return ""
    num_clean = "".join(filter(str.isdigit, str(num)))
    # Se o número brasileiro incluir o código de país '55' com DDD (tamanho 12 ou 13 dígitos)
    if num_clean.startswith("55") and len(num_clean) in [12, 13]:
        return num_clean[2:]
    return num_clean

def verificar_permissao_numero(numero, config):
    if not numero:
        return None
        
    num_clean = normalizar_numero(numero)
    if not num_clean:
        return None
        
    contatos = carregar_contatos_autorizados()
    
    for c in contatos:
        c_num = normalizar_numero(c["whatsapp_number"])
        if num_clean == c_num:
            return c
        # Comparação robusta (tolerância a 9º dígito): DDD + últimos 8 dígitos iguais
        if len(num_clean) >= 10 and len(c_num) >= 10:
            if num_clean[:2] == c_num[:2] and num_clean[-8:] == c_num[-8:]:
                return c
            
    auth_number = config.get("whatsapp_number", "")
    auth_clean = normalizar_numero(auth_number)
    if auth_clean:
        if num_clean == auth_clean:
            return {"whatsapp_number": auth_clean, "nome": "Willian Administrador", "permissao": "admin"}
        if len(num_clean) >= 10 and len(auth_clean) >= 10:
            if num_clean[:2] == auth_clean[:2] and num_clean[-8:] == auth_clean[-8:]:
                return {"whatsapp_number": auth_clean, "nome": "Willian Administrador", "permissao": "admin"}
        
    return None

def carregar_historico_chat(sender_clean):
    os.makedirs("temp", exist_ok=True)
    history_file = os.path.join("temp", f"chat_history_{sender_clean}.json")
    if os.path.exists(history_file):
        try:
            mtime = os.path.getmtime(history_file)
            # Limpa histórico se estiver inativo há mais de 30 minutos (1800s)
            if time.time() - mtime > 1800:
                log(f"Histórico expirado por inatividade para {sender_clean}.", "INFO")
                return []
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                if isinstance(history, list):
                    return history
        except Exception as e:
            log(f"Erro ao ler histórico de chat: {e}", "WARNING")
    return []

def salvar_historico_chat(sender_clean, history):
    if not sender_clean:
        return
    os.makedirs("temp", exist_ok=True)
    history_file = os.path.join("temp", f"chat_history_{sender_clean}.json")
    try:
        # Limita o histórico às últimas 10 mensagens
        history = history[-10:]
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log(f"Erro ao salvar histórico de chat: {e}", "WARNING")

def interpretar_mensagem_com_gpt(texto_mensagem, config, usuario_nome="Usuário", usuario_role="operador", sender_clean=None):
    openai_key = config.get("openai_api_key", "").strip()
    if not openai_key:
        log("OpenAI API Key não encontrada no config_private.json. Usando interpretador Heurístico.", "WARNING")
        return interpretar_mensagem_heuristica(texto_mensagem)
        
    # Tratamento de comando para limpar/resetar o chat
    msg_lower = texto_mensagem.lower().strip()
    if msg_lower in ["limpar", "reset", "limpar histórico", "limpar historico", "limpar conversa", "resetar"]:
        if sender_clean:
            salvar_historico_chat(sender_clean, [])
        return {
            "intencao": "conversa_casual",
            "empresa": None,
            "cnpj": None,
            "resposta_humana": f"🤖 Certo, {usuario_nome}! Nosso histórico de conversa foi limpo com sucesso. Como posso te ajudar agora?"
        }
        
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}"
    }
    
    prompt = f"""Você é o Agente Escavador, o assistente virtual inteligente da J&J Contabilidade que controla o sistema de automação e-CAC e Consulta de Notas Fiscais XML.
O usuário atual que está interagindo com você é o '{usuario_nome}' com o papel de '{usuario_role}'.
Sua tarefa é analisar a mensagem do usuário, deduzir sua intenção operacional e gerar uma resposta em linguagem natural que seja extremamente humana, amigável, natural e adequada ao contexto.
Você receberá o histórico de interações recentes logo abaixo (se houver). Use esse histórico para manter o contexto das intenções operacionais informadas anteriormente.

As intenções suportadas são:
1. "iniciar_varredura" (Iniciar varredura comum do dia do e-CAC, ignorando quem já deu sucesso. Restrito a administradores e operadores)
2. "iniciar_varredura_total" (Forçar escavação completa de todos os clientes do início do e-CAC. Restrito a administradores)
3. "interromper_varredura" (Interromper ou parar a execução ativa do robô do e-CAC. Restrito a administradores)
4. "iniciar_nota_fiscal_xml" (Iniciar varredura de Notas Fiscais XML no portal nacional. Se o usuário pedir para buscar ou fazer varredura de notas fiscais, seja do início/todas ou de um cliente específico/único, defina esta intenção. Se for para um cliente específico, preencha o parâmetro 'empresa' com o nome ou CNPJ do cliente, senão deixe nulo. Restrito a administradores e operadores)
5. "interromper_nota_fiscal_xml" (Interromper a varredura ativa de Notas Fiscais XML. Restrito a administradores)
6. "obter_status_ecac" (Consultar status atual, progresso e estatísticas do robô e-CAC. Permitido a todos)
7. "obter_status_nfe" (Consultar status atual, progresso e estatísticas do robô de Notas Fiscais XML. Permitido a todos)
8. "obter_status" (Consultar status geral de ambos os robôs: e-CAC e NF-e XML. Permitido a todos)
9. "listar_clientes_ok" (Consultar lista de clientes com sucesso hoje. Permitido a todos)
10. "listar_clientes_pendentes_erro" (Consultar lista de clientes com falhas ou pendentes hoje. Permitido a todos)
11. "baixar_documento" (Baixar ou obter a certidão/relatório do e-CAC ou notas fiscais XML já baixadas de um cliente específico. Requer o parâmetro 'empresa')
12. "baixar_consolidado_ecac" (Obter a planilha Excel consolidada principal de pendências do e-CAC. Não requer parâmetro 'empresa')
13. "baixar_consolidado_nfe" (Obter a planilha Excel consolidada principal de Notas Fiscais XML. Não requer parâmetro 'empresa')
14. "adicionar_cliente" (Adicionar um novo cliente/empresa ao sistema. Requer o nome completo em 'empresa' e o CNPJ/CPF em 'cnpj'. Restrito a administradores e operadores)
15. "conversa_casual" (Outro tipo de mensagem, saudações ou dúvidas gerais)

REGRAS CRÍTICAS DE DIFERENCIAÇÃO DE STATUS:
- Se o usuário perguntar pelo status ou progresso especificamente de "notas fiscais", "nfe", "xml" ou "notas" (ex: "como está o robô de notas?", "status xml", "status das notas", "status nfe"), você DEVE usar a intenção "obter_status_nfe". A resposta humana deve mencionar que você vai verificar as notas fiscais xml.
- Se o usuário perguntar pelo status ou progresso especificamente de "ecac", "e-cac", "varredura", "pendências" ou "robô e-cac" (ex: "como está a varredura?", "status ecac", "como está o robô do ecac?"), você DEVE usar a intenção "obter_status_ecac". A resposta humana deve mencionar que você vai verificar o e-CAC.
- Se o usuário pedir um status geral, de ambos, ou apenas disser "status" / "como estão os robôs" sem especificar qual deles quer (ex: "status", "me passe o status atual", "como estão as coisas?"), você DEVE usar a intenção "obter_status". A resposta humana deve mencionar que você vai consultar o status geral de ambos os sistemas.

Retorne estritamente um JSON no seguinte formato (sem formatação markdown ou blocos de código):
{{
  "intencao": "uma das intenções acima",
  "empresa": "nome ou cnpj da empresa se a intenção for baixar_documento, ou o nome completo se for adicionar_cliente, senão nulo",
  "cnpj": "o CNPJ ou CPF do cliente (apenas números) se a intenção for adicionar_cliente, senão nulo",
  "resposta_humana": "uma resposta humana, amigável e profissional em português para o {usuario_nome}, confirmando o que você vai fazer ou respondendo de forma natural e empática"
}}
"""
    
    history = carregar_historico_chat(sender_clean)
    messages_payload = [{"role": "system", "content": prompt}]
    for msg in history:
        messages_payload.append(msg)
    messages_payload.append({"role": "user", "content": texto_mensagem})
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": messages_payload,
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            res_val = json.loads(content)
            
            # Failsafe: Correção heurística de segurança para a intenção de status ou inicialização
            intencao = res_val.get("intencao")
            t_msg = texto_mensagem.lower()
            has_nfe = any(w in t_msg for w in ["xml", "nota", "nfe", "notas", "nota fiscal"])
            has_ecac = any(w in t_msg for w in ["ecac", "e-cac", "varredura", "pendencia", "pendencias"])
            
            if intencao in ["obter_status_ecac", "obter_status_nfe", "obter_status"]:
                if has_nfe and not has_ecac:
                    res_val["intencao"] = "obter_status_nfe"
                elif has_ecac and not has_nfe:
                    res_val["intencao"] = "obter_status_ecac"
                elif has_nfe and has_ecac:
                    res_val["intencao"] = "obter_status"
            elif intencao in ["iniciar_varredura", "iniciar_varredura_total", "iniciar_nota_fiscal_xml"]:
                if has_nfe and not has_ecac:
                    res_val["intencao"] = "iniciar_nota_fiscal_xml"
                elif has_ecac and not has_nfe:
                    if any(w in t_msg for w in ["todos", "completo", "forçar", "forcar", "do inicio", "do início", "todo"]):
                        res_val["intencao"] = "iniciar_varredura_total"
                    else:
                        res_val["intencao"] = "iniciar_varredura"
            
            # Atualiza histórico se for uma resposta válida do modelo
            if sender_clean:
                history.append({"role": "user", "content": texto_mensagem})
                resp_humana = res_val.get("resposta_humana") or f"(Ação executada: {res_val.get('intencao')})"
                history.append({"role": "assistant", "content": resp_humana})
                salvar_historico_chat(sender_clean, history)
                
            return res_val
        else:
            log(f"Erro OpenAI API: {response.text}", "ERROR")
            return interpretar_mensagem_heuristica(texto_mensagem)
    except Exception as e:
        log(f"Erro de conexão com OpenAI: {e}", "ERROR")
        return interpretar_mensagem_heuristica(texto_mensagem)


def interpretar_mensagem_heuristica(texto):
    t = texto.strip().lower()
    
    # Checar se solicita planilha consolidada
    if any(w in t for w in ["planilha", "consolidado", "excel", "painel"]):
        if any(w in t for w in ["ecac", "e-cac"]):
            return {"intencao": "baixar_consolidado_ecac", "empresa": None, "cnpj": None, "resposta_humana": None}
        elif any(w in t for w in ["xml", "nfe", "nota", "notas"]):
            return {"intencao": "baixar_consolidado_nfe", "empresa": None, "cnpj": None, "resposta_humana": None}
    
    # Palavras de início e parada
    iniciar_words = ["iniciar", "começar", "comecar", "rodar", "executar", "escavar"]
    parar_words = ["parar", "interromper", "para", "cancela", "cancelar", "derrubar", "matar"]
    
    has_iniciar = any(w in t for w in iniciar_words)
    has_parar = any(w in t for w in parar_words)
    
    # Heurística para Nota Fiscal XML
    is_xml_related = any(w in t for w in ["xml", "nota", "nfe", "notas", "nota fiscal"])
    
    if is_xml_related and has_parar:
        return {"intencao": "interromper_nota_fiscal_xml", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif has_parar:
        return {"intencao": "interromper_varredura", "empresa": None, "cnpj": None, "resposta_humana": None}
        
    elif "status" in t or "como esta" in t or "como está" in t or "progresso" in t or "log" in t or "relatorio" in t or "relatório" in t:
        if any(w in t for w in ["xml", "nfe", "nota", "notas"]):
            return {"intencao": "obter_status_nfe", "empresa": None, "cnpj": None, "resposta_humana": None}
        elif any(w in t for w in ["ecac", "e-cac", "varredura", "pendencia", "pendencias"]):
            return {"intencao": "obter_status_ecac", "empresa": None, "cnpj": None, "resposta_humana": None}
        else:
            return {"intencao": "obter_status", "empresa": None, "cnpj": None, "resposta_humana": None}
        
    elif is_xml_related and has_iniciar:
        empresa = None
        palavras = texto.split()
        para_idx = -1
        for idx, w in enumerate(palavras):
            if w in ["de", "do", "da", "para", "cliente"]:
                para_idx = idx
                break
        if para_idx != -1 and para_idx < len(palavras) - 1:
            empresa = " ".join(palavras[para_idx + 1:])
        return {"intencao": "iniciar_nota_fiscal_xml", "empresa": empresa, "cnpj": None, "resposta_humana": None}
        
    elif has_iniciar:
        has_todos = any(w in t for w in ["todos", "completo", "forçar", "forcar", "do inicio", "do início"])
        if has_todos:
            return {"intencao": "iniciar_varredura_total", "empresa": None, "cnpj": None, "resposta_humana": None}
        # Para iniciar varredura comum do e-CAC, requer explicitamente contexto de varredura ou e-cac ou robô
        # para evitar disparos com frases casuais como "como iniciar?"
        elif any(w in t for w in ["varredura", "ecac", "e-cac", "robô", "robo", "processo"]):
            return {"intencao": "iniciar_varredura", "empresa": None, "cnpj": None, "resposta_humana": None}
            
    elif "inadimplente" in t or "falha" in t or "erro" in t or "pendente" in t:
        return {"intencao": "listar_clientes_pendentes_erro", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "ok" in t or "sucesso" in t or "regular" in t:
        return {"intencao": "listar_clientes_ok", "empresa": None, "cnpj": None, "resposta_humana": None}
    elif "adicionar" in t or "cadastrar" in t or "novo cliente" in t or "inserir" in t:
        numeros = "".join(filter(str.isdigit, texto))
        cnpj = numeros if len(numeros) in [11, 14] else None
        palavras = [p for p in texto.split() if not p.isdigit()]
        empresa = None
        if len(palavras) > 2:
            empresa = " ".join(palavras[2:]) if "novo" in palavras else " ".join(palavras[1:])
        return {"intencao": "adicionar_cliente", "empresa": empresa, "cnpj": cnpj, "resposta_humana": None}
    elif "cnd" in t or "certidao" in t or "documento" in t or "relatorio" in t or "manda" in t or "envia" in t:
        palavras = texto.split()
        empresa = None
        if len(palavras) > 1:
            empresa = " ".join(palavras[1:])
        return {"intencao": "baixar_documento", "empresa": empresa, "cnpj": None, "resposta_humana": None}
        
    return {
        "intencao": "conversa_casual", 
        "empresa": None, 
        "cnpj": None,
        "resposta_humana": "Olá! Sou o Agente Escavador da J&J Contabilidade. Consigo entender comandos como 'Iniciar varredura', 'Como está o status?', 'Lista de erros', 'Lista de sucessos', 'Parar automação' ou 'Me mande a certidão de [Nome da Empresa]'."
    }

def processar_mensagem_recebida(payload, config, rodando_atualmente, iniciar_callback, parar_callback, iniciar_xml_callback=None, parar_xml_callback=None, processo_xml_ativo=False):
    # Ignorar mensagens enviadas por mim (para evitar loops ou acionamentos acidentais)
    from_me = payload.get("fromMe")
    if from_me is True or str(from_me).lower() == "true":
        log("Ignorando webhook de mensagem enviada pela própria conta (fromMe = True).", "INFO")
        return False
        
    # Ignorar mensagens de grupo
    is_group = payload.get("isGroup")
    if is_group is True or str(is_group).lower() == "true":
        log("Ignorando webhook de mensagem recebida em grupo.", "INFO")
        return False

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
    audio_obj = payload.get("audio")
    
    if not texto_mensagem and not audio_obj:
        return False
        
    # Processar áudio se recebido
    if audio_obj and audio_obj.get("data"):
        log("Processando dados de áudio recebidos...", "AUDIO")
        openai_key = config.get("openai_api_key", "").strip()
        if not openai_key:
            log("Erro: OpenAI API Key ausente para transcrição de áudio.", "ERROR")
            enviar_mensagem_whatsapp(
                "🤖 Recebi seu áudio, mas a transcrição de voz está indisponível no momento porque a chave de API da OpenAI não foi configurada no sistema.",
                config,
                destinatario=sender_clean
            )
            return False
            
        temp_audio_path = None
        try:
            # Criar diretório temp
            os.makedirs("temp", exist_ok=True)
            
            # Identificar extensão a partir do mimetype
            mimetype = audio_obj.get("mimetype", "audio/ogg")
            ext = ".ogg"
            if "mp3" in mimetype or "mpeg" in mimetype:
                ext = ".mp3"
            elif "wav" in mimetype:
                ext = ".wav"
                
            temp_filename = f"temp_voice_{sender_clean}_{int(time.time())}{ext}"
            temp_audio_path = os.path.join("temp", temp_filename)
            
            # Gravar dados decodificados
            import base64
            audio_bytes = base64.b64decode(audio_obj.get("data"))
            with open(temp_audio_path, "wb") as f_audio:
                f_audio.write(audio_bytes)
                
            log(f"Arquivo de áudio temporário gravado em: {temp_audio_path}", "AUDIO")
            
            # Enviar para a API OpenAI Whisper
            url_whisper = "https://api.openai.com/v1/audio/transcriptions"
            headers_whisper = {
                "Authorization": f"Bearer {openai_key}"
            }
            
            # Enviar arquivo via multipart/form-data
            with open(temp_audio_path, "rb") as f_file:
                files = {
                    "file": (temp_filename, f_file, mimetype)
                }
                data = {
                    "model": "whisper-1",
                    "language": "pt"
                }
                
                log("Chamando API Whisper da OpenAI para transcrição...", "AUDIO")
                resp = requests.post(url_whisper, headers=headers_whisper, files=files, data=data, timeout=30)
                
            if resp.status_code == 200:
                transcricao = resp.json().get("text", "").strip()
                if transcricao:
                    log(f"Áudio transcrito com sucesso: '{transcricao}'", "AUDIO")
                    texto_mensagem = transcricao
                    enviar_mensagem_whatsapp(
                        f"🎙️ *[Comando de Voz Compreendido]:*\n\"{transcricao}\"",
                        config,
                        destinatario=sender_clean
                    )
                else:
                    log("Aviso: Transcrição retornou vazia.", "WARNING")
                    enviar_mensagem_whatsapp(
                        "🤖 Não consegui detectar nenhuma fala clara no áudio enviado.",
                        config,
                        destinatario=sender_clean
                    )
                    return False
            else:
                log(f"Erro na API Whisper. Status: {resp.status_code}, Resposta: {resp.text}", "ERROR")
                enviar_mensagem_whatsapp(
                    "🤖 Ocorreu uma falha ao tentar transcrever o seu áudio. Por favor, tente enviar por texto.",
                    config,
                    destinatario=sender_clean
                )
                return False
                
        except Exception as e_audio:
            log(f"Erro ao processar áudio no agente: {e_audio}", "ERROR")
            enviar_mensagem_whatsapp(
                f"❌ Erro interno ao processar áudio: {e_audio}",
                config,
                destinatario=sender_clean
            )
            return False
        finally:
            # Excluir arquivo temporário
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                    log(f"Arquivo temporário de áudio removido: {temp_audio_path}", "AUDIO")
                except Exception as e_rm:
                    log(f"Erro ao remover arquivo temporário {temp_audio_path}: {e_rm}", "WARNING")
        
    log(f"Mensagem recebida de {usuario_nome} ({usuario_role}): '{texto_mensagem}'")
    
    res = interpretar_mensagem_com_gpt(texto_mensagem, config, usuario_nome, usuario_role, sender_clean=sender_clean)
    intencao = res.get("intencao")
    empresa = res.get("empresa")
    cnpj = res.get("cnpj")
    resposta_humana = res.get("resposta_humana")
    
    # Higienização de termos operacionais capturados erroneamente no campo 'empresa'
    if empresa and intencao in ["iniciar_nota_fiscal_xml", "iniciar_varredura", "iniciar_varredura_total"]:
        empresa_lower = empresa.strip().lower()
        termos_operacionais = [
            "todos", "todas", "todos os clientes", "todas as empresas", 
            "inicio", "início", "do inicio", "do início", "todos do inicio", 
            "todos do início", "inicio nota fiscal", "início nota fiscal",
            "nota fiscal", "nota", "notas", "xml", "nfe", "completo", "completa", "tudo"
        ]
        if empresa_lower in termos_operacionais:
            log(f"Filtro de empresa '{empresa}' identificado como termo operacional. Limpando filtro para execução geral.", "AGENTE")
            empresa = None
            resposta_humana = None
            
    log(f"Intenção detectada: '{intencao}' (Empresa: '{empresa}', CNPJ: '{cnpj}')")
    
    # Restrições de papel
    restrito_admin = ["interromper_varredura", "iniciar_varredura_total", "interromper_nota_fiscal_xml"]
    restrito_admin_operador = ["iniciar_varredura", "adicionar_cliente", "iniciar_nota_fiscal_xml", "baixar_consolidado_ecac", "baixar_consolidado_nfe"]
    
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
                enviar_mensagem_whatsapp("🤖 O robô e-CAC já está executando uma varredura no momento.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 *Entendido!* Estou iniciando a varredura inteligente do e-CAC agora em segundo plano. Vou te notificar do andamento.", config, destinatario=sender_clean)
            iniciar_callback(forcar_todos=False)
            
    elif intencao == "iniciar_varredura_total":
        if rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 O robô e-CAC já está executando uma varredura. Interrompa a atual se quiser reiniciar do zero.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 *Entendido!* Estou iniciando a varredura completa (forçando todos) do e-CAC agora em segundo plano. Isso pode levar mais tempo.", config, destinatario=sender_clean)
            iniciar_callback(forcar_todos=True)
            
    elif intencao == "interromper_varredura":
        if not rodando_atualmente:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 Nenhuma varredura do e-CAC ativa para interromper no momento.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🔴 *Parada Forçada:* Estou parando a automação e-CAC e encerrando os navegadores do e-CAC...", config, destinatario=sender_clean)
            parar_callback()
            enviar_mensagem_whatsapp("✅ Automação e-CAC interrompida com sucesso!", config, destinatario=sender_clean)
 
    elif intencao == "iniciar_nota_fiscal_xml":
        if processo_xml_ativo:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 A consulta de Notas Fiscais XML já está rodando no momento.", config, destinatario=sender_clean)
        else:
            t_msg_lower = texto_mensagem.lower()
            quer_forcar = any(w in t_msg_lower for w in ["todos", "completo", "forçar", "forcar", "do inicio", "do início", "todo"])
            tipo_busca = "completa (do início)" if quer_forcar else "padrão"
            
            if empresa:
                if not resposta_humana:
                    enviar_mensagem_whatsapp(f"🤖 *Entendido!* Estou iniciando a consulta {tipo_busca} de Notas Fiscais XML exclusivamente para o cliente *{empresa}* em segundo plano. Assim que as notas forem baixadas, eu as enviarei aqui.", config, destinatario=sender_clean)
                if iniciar_xml_callback:
                    iniciar_xml_callback(forcar_todos=quer_forcar, destinatario=sender_clean, cliente_filtro=empresa)
            else:
                if not resposta_humana:
                    enviar_mensagem_whatsapp(f"🤖 *Entendido!* Estou iniciando a consulta {tipo_busca} de Notas Fiscais XML para todos os clientes em segundo plano. Se houver CAPTCHAs, te avisarei aqui.", config, destinatario=sender_clean)
                if iniciar_xml_callback:
                    iniciar_xml_callback(forcar_todos=quer_forcar, destinatario=sender_clean)
            
    elif intencao == "interromper_nota_fiscal_xml":
        if not processo_xml_ativo:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🤖 Nenhuma consulta de Notas Fiscais XML ativa para interromper no momento.", config, destinatario=sender_clean)
        else:
            if not resposta_humana:
                enviar_mensagem_whatsapp("🔴 *Parada Forçada:* Estou interrompendo o processo de Notas Fiscais XML...", config, destinatario=sender_clean)
            if parar_xml_callback:
                parar_xml_callback()
            enviar_mensagem_whatsapp("✅ Processo de Notas Fiscais XML interrompido com sucesso!", config, destinatario=sender_clean)
            
    elif intencao == "obter_status_ecac":
        resumo = obter_status_resumo(config, rodando_atualmente)
        enviar_mensagem_whatsapp(resumo, config, destinatario=sender_clean)
        
    elif intencao == "obter_status_nfe":
        resumo = obter_status_resumo_nfe(config, processo_xml_ativo)
        enviar_mensagem_whatsapp(resumo, config, destinatario=sender_clean)
        
    elif intencao == "obter_status":
        resumo_ecac = obter_status_resumo(config, rodando_atualmente)
        resumo_nfe = obter_status_resumo_nfe(config, processo_xml_ativo)
        combined_resumo = f"{resumo_ecac}\n\n{resumo_nfe}"
        enviar_mensagem_whatsapp(combined_resumo, config, destinatario=sender_clean)
        
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
            
            # Verificar se a mensagem original menciona nota fiscal / xml
            msg_texto_lower = texto_mensagem.lower()
            quer_xml = any(w in msg_texto_lower for w in ["xml", "nota", "notas", "nfe", "nota fiscal"])
            
            msg_resposta = localizar_e_enviar_documento(empresa, config, destinatario=sender_clean, apenas_xml=quer_xml)
            enviar_mensagem_whatsapp(msg_resposta, config, destinatario=sender_clean)
            
    elif intencao == "baixar_consolidado_ecac":
        if not resposta_humana:
            enviar_mensagem_whatsapp("🔍 Atualizando e gerando a planilha consolidada e-CAC em tempo real...", config, destinatario=sender_clean)
        try:
            from rebuild_utils import rebuild_ecac_consolidated_sheet
            sucesso_rebuild = rebuild_ecac_consolidated_sheet(config)
            if sucesso_rebuild:
                desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
                caminho_excel = os.path.join(desktop_dir, "Painel_Consolidado_Pendencias_eCAC.xlsx")
                if os.path.exists(caminho_excel):
                    enviar_documento_whatsapp(caminho_excel, "Painel_Consolidado_Pendencias_eCAC.xlsx", config, destinatario=sender_clean)
                    enviar_mensagem_whatsapp("✅ Planilha consolidada e-CAC enviada com sucesso!", config, destinatario=sender_clean)
                else:
                    enviar_mensagem_whatsapp("❌ O arquivo consolidado e-CAC não foi gerado na Área de Trabalho.", config, destinatario=sender_clean)
            else:
                enviar_mensagem_whatsapp("❌ Falha ao reconstruir a planilha consolidada e-CAC.", config, destinatario=sender_clean)
        except Exception as e_rebuild:
            enviar_mensagem_whatsapp(f"❌ Erro ao processar o consolidado e-CAC: {e_rebuild}", config, destinatario=sender_clean)
            
    elif intencao == "baixar_consolidado_nfe":
        if not resposta_humana:
            enviar_mensagem_whatsapp("🔍 Atualizando e gerando a planilha consolidada de Notas Fiscais XML em tempo real...", config, destinatario=sender_clean)
        try:
            from rebuild_utils import rebuild_xml_consolidated_sheet
            sucesso_rebuild = rebuild_xml_consolidated_sheet(config)
            if sucesso_rebuild:
                desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
                caminho_excel = os.path.join(desktop_dir, "nota_fiscal_xml.xlsx")
                if not os.path.exists(caminho_excel):
                    caminho_excel = "nota_fiscal_xml.xlsx"
                    
                if os.path.exists(caminho_excel):
                    enviar_documento_whatsapp(caminho_excel, "nota_fiscal_xml.xlsx", config, destinatario=sender_clean)
                    enviar_mensagem_whatsapp("✅ Planilha consolidada de Notas Fiscais XML enviada com sucesso!", config, destinatario=sender_clean)
                else:
                    enviar_mensagem_whatsapp("❌ O arquivo consolidado NF-e XML não foi localizado.", config, destinatario=sender_clean)
            else:
                enviar_mensagem_whatsapp("❌ Falha ao reconstruir a planilha consolidada NF-e XML.", config, destinatario=sender_clean)
        except Exception as e_rebuild:
            enviar_mensagem_whatsapp(f"❌ Erro ao processar o consolidado NF-e XML: {e_rebuild}", config, destinatario=sender_clean)
            
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
