import os
import sys
import re
import shutil
import datetime
import requests
import json
import xml.etree.ElementTree as ET
from database_manager import DatabaseManager

def log(msg, level="NFE_API"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def clean_filename(name):
    if not name:
        return ""
    # Remove caracteres inválidos para nomes de diretórios no Windows
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def extrair_mes_ano_emissao(xml_content_str):
    try:
        # Tenta extrair a data de emissão usando regex rápido (dhEmi ou dEmi)
        match = re.search(r"<(?:dhEmi|dEmi)>([^<]+)</(?:dhEmi|dEmi)>", xml_content_str)
        if match:
            date_str = match.group(1) # ex: 2026-06-01T12:00:00-03:00 ou 2026-06-01
            parts = date_str.split("T")[0].split("-")
            if len(parts) >= 2:
                # Retorna no formato MM_AAAA (ex: 06_2026)
                return f"{parts[1]}_{parts[0]}"
    except Exception:
        pass
    # Fallback para o mês e ano atual
    return datetime.date.today().strftime("%m_%Y")

def xml_para_dicionario(elemento):
    ret = {}
    tag_clean = elemento.tag.split("}")[-1] # Remove namespace se houver
    
    if len(elemento) == 0:
        return {tag_clean: elemento.text}
        
    for child in elemento:
        child_dict = xml_para_dicionario(child)
        child_tag = list(child_dict.keys())[0]
        child_val = child_dict[child_tag]
        
        if child_tag in ret:
            if not isinstance(ret[child_tag], list):
                ret[child_tag] = [ret[child_tag]]
            ret[child_tag].append(child_val)
        else:
            ret[child_tag] = child_val
            
    return {tag_clean: ret}

def converter_xml_nfe_para_json(caminho_xml, caminho_json):
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        dict_data = xml_para_dicionario(root)
        with open(caminho_json, "w", encoding="utf-8") as f:
            json.dump(dict_data, f, indent=4, ensure_ascii=False)
        return dict_data
    except Exception as e:
        log(f"Erro ao converter XML para JSON: {e}", "WARNING")
        return None

def extrair_dados_fiscais_nfe(caminho_json):
    try:
        with open(caminho_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Tenta navegar na estrutura comum do JSON da NF-e
        # A raiz pode ser nfeProc ou NFe
        nfe_data = data.get("nfeProc", {}).get("NFe", {}) if "nfeProc" in data else data.get("NFe", {})
        if not nfe_data:
            nfe_data = data.get("nfeProc", {})
            
        inf_nfe = nfe_data.get("infNFe", {})
        if not inf_nfe:
            return None
            
        ide = inf_nfe.get("ide", {})
        emit = inf_nfe.get("emit", {})
        dest = inf_nfe.get("dest", {})
        total = inf_nfe.get("total", {}).get("ICMSTot", {})
        
        # Chave de acesso (geralmente no atributo Id do infNFe)
        attrs = inf_nfe.get("@attributes", {})
        if not attrs:
            # Em alguns parses, os atributos ficam na chave direto ou com infNFeId
            attrs = inf_nfe
        chave = re.sub(r"\D", "", attrs.get("Id", "")) if isinstance(attrs, dict) else ""
        if not chave and "Id" in inf_nfe:
            chave = re.sub(r"\D", "", str(inf_nfe["Id"]))
            
        def converter_float(val):
            if val is None:
                return 0.0
            try:
                return float(str(val))
            except ValueError:
                return 0.0
                
        return {
            "chave_acesso": chave,
            "numero_nf": ide.get("nNF"),
            "serie": ide.get("serie"),
            "data_emissao": ide.get("dhEmi") or ide.get("dEmi"),
            "cnpj_emitente": emit.get("CNPJ") or emit.get("CPF"),
            "nome_emitente": emit.get("xNome"),
            "cnpj_destinatario": dest.get("CNPJ") or dest.get("CPF"),
            "nome_destinatario": dest.get("xNome"),
            "valor_produtos": converter_float(total.get("vProd")),
            "valor_nota": converter_float(total.get("vNF")),
            "pis": converter_float(total.get("vPIS")),
            "cofins": converter_float(total.get("vCOFINS")),
            "icms": converter_float(total.get("vICMS"))
        }
    except Exception as e:
        log(f"Erro ao extrair dados fiscais do JSON: {e}", "WARNING")
        return None

def enviar_documento_whatsapp_local(caminho_arquivo, nome_arquivo, config, destinatario):
    if not config.get("whatsapp_enabled") or not destinatario:
        return
    import base64
    try:
        with open(caminho_arquivo, "rb") as f:
            base64_content = base64.b64encode(f.read()).decode("utf-8")
        
        ext = os.path.splitext(nome_arquivo)[1].lower()
        mime = "application/xml" if ext == ".xml" else "application/octet-stream"
        document_payload = f"data:{mime};base64,{base64_content}"
        
        url = "http://127.0.0.1:3000/api/send-document"
        payload = {
            "to": destinatario,
            "document": document_payload,
            "fileName": nome_arquivo
        }
        requests.post(url, json=payload, timeout=20)
    except Exception as e:
        log(f"Erro ao enviar XML por whatsapp para {destinatario}: {e}", "WARNING")

def baixar_notas_api(cnpj_cliente, config, destinatario=None):
    cnpj_limpo = "".join(filter(str.isdigit, str(cnpj_cliente))).zfill(14)
    
    token = config.get("focusnfe_token")
    if not token:
        log("API FocusNFe não configurada (focusnfe_token ausente). Pulando e ativando Playwright.", "INFO")
        return False
        
    ambiente = config.get("focusnfe_env", "homologacao").lower()
    base_url = "https://api.focusnfe.com.br" if ambiente == "producao" else "https://homologacao.focusnfe.com.br"
    
    log(f"Iniciando chamada de API FocusNFe ({ambiente.upper()}) para CNPJ: {cnpj_limpo}...", "ACTION")
    
    # Endpoint da FocusNFe para consultar notas destinadas (recebidas)
    url_consulta = f"{base_url}/v2/nfes_recebidas?cnpj={cnpj_limpo}"
    
    try:
        # Autenticação HTTP Basic com token (sem senha)
        response = requests.get(url_consulta, auth=(token, ""), timeout=30)
        
        if response.status_code == 401:
            log("Erro de Autenticação (401) na API FocusNFe. Verifique seu token.", "ERROR")
            return False
        elif response.status_code != 200:
            log(f"API retornou erro {response.status_code}: {response.text}", "WARNING")
            return False
            
        dados = response.json()
        # Se for uma lista de notas recebidas
        notas = dados if isinstance(dados, list) else dados.get("nfes_recebidas", [])
        
        if not notas:
            log(f"Nenhuma nota fiscal destinada localizada via API FocusNFe para o CNPJ {cnpj_limpo}.", "SUCCESS")
            return True
            
        log(f"Localizadas {len(notas)} nota(s) via API para {cnpj_limpo}. Baixando XMLs ausentes...", "INFO")
        
        db = DatabaseManager()
        sucessos = 0
        
        for nota in notas:
            chave = nota.get("chave")
            if not chave:
                continue
                
            # Verifica se já temos indexado no banco de dados para evitar re-download
            nota_existente = db.obter_nota_fiscal(chave)
            if nota_existente and nota_existente.get("caminho_xml") and os.path.exists(nota_existente["caminho_xml"]):
                continue
                
            # Endpoint para download de XML
            url_download = f"{base_url}/v2/nfes_recebidas/{chave}.xml"
            res_dl = requests.get(url_download, auth=(token, ""), timeout=20)
            
            if res_dl.status_code == 200:
                xml_content = res_dl.text
                nome_arquivo = f"{chave}.xml"
                
                # Salva temporário
                os.makedirs("temp", exist_ok=True)
                temp_xml_path = os.path.join("temp", nome_arquivo)
                with open(temp_xml_path, "w", encoding="utf-8") as f_xml:
                    f_xml.write(xml_content)
                    
                # Identifica mês/ano e cria diretório padrão do sistema
                mes_ano = extrair_mes_ano_emissao(xml_content)
                
                # Obter nome do cliente do banco para nomear a pasta destino
                cliente_db = db.obter_cliente(cnpj_limpo)
                nome_cliente = cliente_db["nome"] if cliente_db else f"Cliente_{cnpj_limpo}"
                nome_limpo = clean_filename(nome_cliente)
                
                pasta_destino = os.path.join("documentos de nota fiscal xml", f"XML_{mes_ano}_{cnpj_limpo}_{nome_limpo}")
                os.makedirs(pasta_destino, exist_ok=True)
                
                caminho_salvar = os.path.join(pasta_destino, nome_arquivo)
                shutil.move(temp_xml_path, caminho_salvar)
                
                # Converte para JSON e extrai metadados
                caminho_json = os.path.join(pasta_destino, f"{chave}.json")
                converter_xml_nfe_para_json(caminho_salvar, caminho_json)
                
                dados_nfe = extrair_dados_fiscais_nfe(caminho_json)
                if dados_nfe:
                    # Indexa no banco de dados
                    db.salvar_nota_fiscal(
                        chave_acesso=dados_nfe["chave_acesso"] or chave,
                        numero_nf=dados_nfe["numero_nf"],
                        serie=dados_nfe["serie"],
                        data_emissao=dados_nfe["data_emissao"],
                        cnpj_emitente=dados_nfe["cnpj_emitente"],
                        nome_emitente=dados_nfe["nome_emitente"],
                        cnpj_destinatario=dados_nfe["cnpj_destinatario"] or cnpj_limpo,
                        nome_destinatario=dados_nfe["nome_destinatario"] or nome_cliente,
                        valor_produtos=dados_nfe["valor_produtos"],
                        valor_nota=dados_nfe["valor_nota"],
                        pis=dados_nfe["pis"],
                        cofins=dados_nfe["cofins"],
                        icms=dados_nfe["icms"],
                        caminho_xml=caminho_salvar
                    )
                    
                # Envia via whatsapp se solicitado
                if destinatario:
                    enviar_documento_whatsapp_local(caminho_salvar, nome_arquivo, config, destinatario)
                    
                sucessos += 1
                log(f"Nota fiscal {chave} baixada com sucesso da API e indexada no banco.", "SUCCESS")
                
        log(f"Processamento de API concluído para {cnpj_limpo}. Novas notas baixadas: {sucessos}.", "SUCCESS")
        return True
    except Exception as e:
        log(f"Erro ao conectar com API FocusNFe: {e}. Acionando fallback Playwright...", "WARNING")
        return False
