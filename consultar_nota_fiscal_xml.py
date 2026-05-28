import os
import sys
import csv
import time
import json
import datetime
import requests
import re
import shutil
from playwright.sync_api import sync_playwright, TimeoutError
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Função de log
def log(msg, level="INFO"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_str = str(msg)
    
    encoding = sys.stdout.encoding or 'utf-8'
    try:
        msg_encoded = msg_str.encode(encoding, errors='replace').decode(encoding)
        print(f"[{timestamp}] [{level}] {msg_encoded}")
    except Exception:
        try:
            print(f"[{timestamp}] [{level}] {msg_str.encode('ascii', errors='replace').decode('ascii')}")
        except Exception:
            pass
            
    log_dir = "logs"
    try:
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        with open(os.path.join(log_dir, f"nota_fiscal_xml_{today}.log"), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {msg_str}\n")
    except Exception:
        pass

def focar_janela_certificado(keywords_browser):
    import ctypes
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
    ShowWindow = ctypes.windll.user32.ShowWindow
    
    found_hwnds = []
    
    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            title = buff.value
            title_lower = title.lower()
            
            # 1. Diálogos de certificado ou segurança
            if any(x in title_lower for x in ["certificado", "confirmar", "selecione", "segurança", "credential"]):
                found_hwnds.append((hwnd, title, 2))
            # 2. Janela do navegador da nossa automação
            elif any(x in title_lower for x in keywords_browser):
                found_hwnds.append((hwnd, title, 1))
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if not found_hwnds:
        log("[AUTO-LOGIN] Nenhuma janela de certificado ou navegador encontrada para focar.", "WARNING")
        return False
        
    found_hwnds.sort(key=lambda x: x[2], reverse=True)
    target_hwnd, title, priority = found_hwnds[0]
    
    log(f"[AUTO-LOGIN] Focando na janela encontrada (Prioridade {priority}): '{title}'", "SYSTEM")
    try:
        # Simula toque no ALT para destravar SetForegroundWindow
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
        ShowWindow(target_hwnd, 9) # SW_RESTORE
        SetForegroundWindow(target_hwnd)
        time.sleep(0.5)
        return True
    except Exception as e:
        log(f"[AUTO-LOGIN] Erro ao focar janela: {e}", "WARNING")
        return False

def press_enter(first_char=None):
    import ctypes
    focar_janela_certificado(["nota fiscal", "nfe.fazenda", "chrome", "edge"])
    if first_char:
        char_upper = first_char.upper()
        if len(char_upper) == 1 and (char_upper.isalnum() or char_upper == " "):
            vk_code = ord(char_upper)
            log(f"Enviando tecla '{char_upper}' (VK: {hex(vk_code)}) para focar no certificado...", "SYSTEM")
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0) # Key Down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0) # Key Up
            time.sleep(0.5)
            
    log("Enviando comando ENTER para o Windows...", "SYSTEM")
    VK_RETURN = 0x0D
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0) # Key Down
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 2, 0) # Key Up
    log("ENTER enviado.", "SYSTEM")


# Função para carregar as configurações locais
def load_config():
    config_path = "config.json"
    private_config_path = "config_private.json"
    config = {
        "headless": False,
        "timeout_ms": 30000,
        "relatorios_dir": "relatorios",
        "clientes_file": "clientes.csv",
        "portal_url": "https://www.nfe.fazenda.gov.br/portal/principal.aspx",
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

# Função para enviar mensagens via WhatsApp
def enviar_whatsapp(mensagem, config, destinatario=None):
    if not config.get("whatsapp_enabled"):
        log("Notificação via WhatsApp desabilitada nas configurações.", "INFO")
        return False
        
    number = destinatario or config.get("whatsapp_number")
    if not number:
        log("Erro: Número de telefone do WhatsApp não configurado.", "ERROR")
        return False
        
    def worker():
        url = "http://127.0.0.1:3000/api/send-message"
        payload = {
            "to": number,
            "message": mensagem
        }
        log(f"Enviando notificação WhatsApp para {number} via gateway local em segundo plano...", "INFO")
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code in [200, 201]:
                log("Notificação via WhatsApp enviada com sucesso!", "SUCCESS")
            else:
                log(f"Falha ao enviar WhatsApp. Status: {response.status_code}, Resposta: {response.text}", "ERROR")
        except Exception as e:
            log(f"Erro ao enviar requisição HTTP do WhatsApp: {e}", "ERROR")

    import threading
    threading.Thread(target=worker, daemon=True).start()
    return True

# Limpar o nome da empresa para diretórios seguros
def clean_filename(name):
    return "".join(c if c.isalnum() or c in " _-ÇçÁáÉéÍíÓóÚúÃãÕõÂâÊêÔôÀàÜü" else "_" for c in name).strip()

# Formatar CNPJ
def format_cnpj(cnpj):
    c = "".join(filter(str.isdigit, cnpj))
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    elif len(c) == 11:
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return cnpj

# Salvar status do processamento do cliente
def save_client_status_nota_fiscal_xml(cnpj, nome, status, details=""):
    today = datetime.date.today().strftime("%Y-%m-%d")
    nome_limpo = clean_filename(nome)
    cnpj_limpo = "".join(filter(str.isdigit, cnpj))
    
    client_dir = os.path.join("documentos de nota fiscal xml", f"{cnpj_limpo}_{nome_limpo}")
    os.makedirs(client_dir, exist_ok=True)
    
    status_path = os.path.join(client_dir, "status_nota_fiscal_xml.json")
    contador_falhas = 0
    
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("data_consulta") == today:
                    contador_falhas = data.get("contador_falhas_hoje", 0)
        except Exception:
            pass
            
    if status == "Erro":
        contador_falhas += 1
    elif status == "Sucesso":
        contador_falhas = 0
        
    status_data = {
        "cnpj": cnpj,
        "nome": nome,
        "data_consulta": today,
        "hora_consulta": datetime.datetime.now().strftime("%H:%M:%S"),
        "status": status,
        "detalhes": details,
        "contador_falhas_hoje": contador_falhas
    }
    
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=4, ensure_ascii=False)
    return client_dir

# Salvar estado global em tempo real
def salvar_estado_global(rodando, empresa_atual, total, processados, sucessos, falhas):
    os.makedirs("temp", exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    state_data = {
        "rodando": rodando,
        "empresa_atual": empresa_atual,
        "total_clientes": total,
        "processados": processados,
        "sucessos": sucessos,
        "falhas": falhas,
        "data_consulta": today
    }
    try:
        with open("temp/state_nota_fiscal_xml.json", "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log(f"Erro ao salvar state_nota_fiscal_xml.json: {e}", "WARNING")

# Aguardar resolução do CAPTCHA na tela
def esperar_captcha(page, client_name, cnpj, step_name, config, destinatario=None):
    log(f"Aguardando resolução do CAPTCHA na tela para o cliente {client_name} (CNPJ: {cnpj}). Etapa: {step_name}", "INFO")
    
    # Enviar notificação pelo WhatsApp
    msg_whatsapp = (
        f"🤖 *Alerta de CAPTCHA! (Nota Fiscal XML)*\n\n"
        f"A automação precisa que você resolva o CAPTCHA na tela do servidor.\n"
        f"🏢 *Cliente:* {client_name}\n"
        f"📇 *CNPJ/CPF:* {format_cnpj(cnpj)}\n"
        f"📍 *Etapa:* {step_name}\n\n"
        f"Por favor, acesse o servidor e resolva o CAPTCHA para continuar."
    )
    enviar_whatsapp(msg_whatsapp, config, destinatario)
    
    # Tentar clicar automaticamente no checkbox "Sou humano" do hCaptcha para agilizar a resolução
    try:
        log("Tentando localizar e clicar no checkbox do hCaptcha automaticamente...", "INFO")
        iframe = page.frame_locator('iframe[title*="hCaptcha"], iframe[title*="hcaptcha"], iframe[src*="hcaptcha"]')
        checkbox = iframe.locator('#checkbox, #anchor, .check, div[role="checkbox"]').first
        checkbox.wait_for(state="visible", timeout=5000)
        checkbox.click()
        log("Checkbox do hCaptcha clicado automaticamente.", "SUCCESS")
    except Exception as e_click:
        log(f"Aviso ao tentar clicar no checkbox do hCaptcha (pode já estar clicado ou não visível): {e_click}", "WARNING")
        
    limite_tempo = 300  # 5 minutos
    inicio = time.time()
    
    while time.time() - inicio < limite_tempo:
        # Verificar se o token de hCaptcha ou reCAPTCHA foi preenchido
        try:
            h_token = page.locator('textarea[name="h-captcha-response"]').first.input_value()
            if h_token and len(h_token.strip()) > 0:
                log("Token hCaptcha preenchido pelo usuário.", "SUCCESS")
                return True
        except Exception:
            pass
            
        try:
            g_token = page.locator('textarea[name="g-recaptcha-response"]').first.input_value()
            if g_token and len(g_token.strip()) > 0:
                log("Token reCAPTCHA preenchido pelo usuário.", "SUCCESS")
                return True
        except Exception:
            pass
            
        # Também checa se a página mudou sozinha devido à submissão manual do usuário
        try:
            if step_name == "Manifestação":
                # Verifica se sumiu o input de CNPJ
                has_cnpj_input = False
                for sel in ['input[name*="txtCNPJ"]', 'input[name*="CNPJ"]', 'input#txtCNPJ']:
                    try:
                        if page.locator(sel).first.is_visible():
                            has_cnpj_input = True
                            break
                    except Exception:
                        pass
                if not has_cnpj_input:
                    log("Página mudou. Captcha submetido.", "SUCCESS")
                    return True
            elif step_name == "Consulta NFe":
                if not page.locator('input[name="ctl00$ContentPlaceHolder1$txtChaveAcessoResumo"]').is_visible():
                    log("Página mudou. Captcha submetido.", "SUCCESS")
                    return True
        except Exception:
            pass
            
        time.sleep(1)
        
    log("Timeout de 5 minutos aguardando resolução do CAPTCHA.", "WARNING")
    return False

# Gerar planilha Excel bonita
def gerar_excel_resumo(resultados):
    excel_path = "nota_fiscal_xml.xlsx"
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "nota_fiscal_xml.xlsx")
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Nota Fiscal XML"
    
    ws.views.sheetView[0].showGridLines = True
    
    # Cabeçalho
    headers = ["CNPJ/CPF", "Razão Social / Nome", "Chave de Acesso", "Status de Download", "Data/Hora Consulta"]
    ws.append(headers)
    
    # Estilização
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    fill_header = PatternFill(start_color="8E44AD", end_color="8E44AD", fill_type="solid") # Tema roxo
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center")
    
    border_side = Side(border_style="thin", color="D3D3D3")
    border_cell = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
    
    for col_idx in range(1, 6):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = border_cell
        
    font_data = Font(name="Segoe UI", size=10)
    for idx, r in enumerate(resultados, start=2):
        cnpj, nome, chave, status, dt = r
        ws.append([format_cnpj(cnpj), nome, chave, status, dt])
        
        fill_status = PatternFill(fill_type=None)
        if status == "Baixado":
            fill_status = PatternFill(start_color="D4EFDF", end_color="D4EFDF", fill_type="solid") # Verde
        elif status == "Não Possui Manifestação" or status == "Sem Registros":
            fill_status = PatternFill(start_color="FCF3CF", end_color="FCF3CF", fill_type="solid") # Amarelo claro
        elif "Erro" in status:
            fill_status = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid") # Vermelho claro
            
        for col_idx in range(1, 6):
            cell = ws.cell(row=idx, column=col_idx)
            cell.font = font_data
            cell.border = border_cell
            if col_idx == 4:
                cell.fill = fill_status
                cell.alignment = align_center
            elif col_idx in [1, 3, 5]:
                cell.alignment = align_center
            else:
                cell.alignment = align_left
                
    # Largura das colunas
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 45
    ws.column_dimensions['C'].width = 48
    ws.column_dimensions['D'].width = 25
    ws.column_dimensions['E'].width = 22
    
    ws.row_dimensions[1].height = 28
    
    # Salvar
    try:
        wb.save(excel_path)
        log(f"Planilha local {excel_path} salva com sucesso.", "SUCCESS")
        try:
            shutil.copy(excel_path, desktop_path)
            log(f"Cópia da planilha salva no Desktop em: {desktop_path}", "SUCCESS")
        except Exception as e_desktop:
            log(f"Aviso ao salvar cópia no Desktop: {e_desktop}", "WARNING")
    except Exception as e:
        log(f"Erro ao salvar planilha excel: {e}", "ERROR")

def main():
    config = load_config()
    
    # Identificar primeira letra do certificado digital pelo arquivo .pfx
    import glob
    import re
    pfx_files = glob.glob("*.pfx")
    cert_first_char = "J"
    if pfx_files:
        filename = os.path.basename(pfx_files[0])
        clean_name = re.sub(r"^\d+_", "", filename)
        if clean_name:
            cert_first_char = clean_name[0].upper()
    log(f"Caractere inicial do certificado detectado para NF-e: '{cert_first_char}'", "INFO")
    
    # Parse de argumentos
    forcar_todos = "--forcar-todos" in sys.argv
    destinatario = None
    if "--destinatario" in sys.argv:
        try:
            idx = sys.argv.index("--destinatario")
            destinatario = sys.argv[idx + 1]
        except Exception:
            pass
            
    log(f"Iniciando processo de Consulta de Nota Fiscal XML. Forçar todos: {forcar_todos}", "SYSTEM")
    
    # Carregar clientes
    clientes_file = config.get("clientes_file", "clientes.csv")
    if not os.path.exists(clientes_file):
        log("Arquivo clientes.csv não encontrado. Abortando.", "ERROR")
        return
        
    clientes_ativos = []
    with open(clientes_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ativo = row.get("ativo", "True").strip().lower() in ["true", "1", "yes", "ativo", "sim", "s"]
            if ativo:
                clientes_ativos.append(row)
                
    total_clientes = len(clientes_ativos)
    log(f"Total de clientes ativos encontrados: {total_clientes}", "INFO")
    
    if total_clientes == 0:
        log("Nenhum cliente ativo para processar.", "WARNING")
        salvar_estado_global(False, "Nenhum cliente ativo", 0, 0, 0, 0)
        return
        
    today = datetime.date.today().strftime("%Y-%m-%d")
    clientes_para_processar = []
    sucessos = 0
    falhas = 0
    
    resultados_excel_hoje = []
    
    # Ler histórico do excel existente
    if os.path.exists("nota_fiscal_xml.xlsx"):
        try:
            wb_temp = openpyxl.load_workbook("nota_fiscal_xml.xlsx")
            ws_temp = wb_temp.active
            for row in list(ws_temp.iter_rows(values_only=True))[1:]:
                dt_row = str(row[4] or "")
                if dt_row.startswith(today):
                    continue
                resultados_excel_hoje.append(list(row))
        except Exception as e_excel:
            log(f"Aviso ao carregar dados anteriores do Excel: {e_excel}", "WARNING")
            
    for c in clientes_ativos:
        cnpj_limpo = "".join(filter(str.isdigit, c["cnpj"]))
        nome_limpo = clean_filename(c["nome"])
        status_path = os.path.join("documentos de nota fiscal xml", f"{cnpj_limpo}_{nome_limpo}", "status_nota_fiscal_xml.json")
        
        ja_processado_hoje = False
        if os.path.exists(status_path) and not forcar_todos:
            try:
                with open(status_path, "r", encoding="utf-8") as f_st:
                    st_data = json.load(f_st)
                    if st_data.get("data_consulta") == today:
                        if st_data.get("status") == "Sucesso":
                            ja_processado_hoje = True
                            sucessos += 1
                            det = st_data.get("detalhes", "")
                            hora = st_data.get("hora_consulta", "00:00:00")
                            dt_completa = f"{today} {hora}"
                            if "chaves" in det:
                                client_dir = os.path.join("documentos de nota fiscal xml", f"{cnpj_limpo}_{nome_limpo}")
                                files_found = [f for f in os.listdir(client_dir) if f.endswith((".xml", ".pdf"))]
                                if files_found:
                                    for f in files_found:
                                        match_key = re.search(r'\b\d{44}\b', f)
                                        k = match_key.group(0) if match_key else "N/A"
                                        resultados_excel_hoje.append([c["cnpj"], c["nome"], k, "Baixado", dt_completa])
                                else:
                                    resultados_excel_hoje.append([c["cnpj"], c["nome"], "N/A", "Baixado", dt_completa])
                            else:
                                resultados_excel_hoje.append([c["cnpj"], c["nome"], "N/A", "Sem Registros", dt_completa])
                        elif st_data.get("status") == "Erro":
                            falhas += 1
            except Exception:
                pass
                
        if not ja_processado_hoje:
            clientes_para_processar.append(c)
            
    processados = total_clientes - len(clientes_para_processar)
    log(f"Clientes já processados hoje: {processados}. Restantes: {len(clientes_para_processar)}", "INFO")
    
    if len(clientes_para_processar) == 0:
        log("Todos os clientes já foram processados hoje com sucesso.", "SUCCESS")
        salvar_estado_global(False, "Varredura Concluída", total_clientes, processados, sucessos, falhas)
        gerar_excel_resumo(resultados_excel_hoje)
        return
        
    salvar_estado_global(True, "Inicializando Navegador...", total_clientes, processados, sucessos, falhas)
    
    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "temp", "chrome_profile_nota_fiscal_xml")
        os.makedirs(user_data_dir, exist_ok=True)
        
        lock_file = os.path.join(user_data_dir, "SingletonLock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
                
        log("Abrindo Google Chrome nativo em modo visível...", "SYSTEM")
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-session-crashed-bubble",
                    "--disable-features=BubbleSessionCrashedBubble"
                ],
                no_viewport=True
            )
        except Exception as e_launch:
            log(f"Erro crítico ao abrir navegador: {e_launch}", "ERROR")
            salvar_estado_global(False, f"Erro ao iniciar Chrome: {e_launch}", total_clientes, processados, sucessos, falhas)
            return
            
        page = context.new_page()
        page.set_default_timeout(30000)
        
        cert_confirmado = False
        
        for idx, client in enumerate(clientes_para_processar):
            cnpj = client["cnpj"]
            nome = client["nome"]
            cnpj_clean = "".join(filter(str.isdigit, cnpj))
            nome_limpo = clean_filename(nome)
            
            # Salva cópia do status antigo caso precise restaurar
            status_path = os.path.join("documentos de nota fiscal xml", f"{cnpj_clean}_{nome_limpo}", "status_nota_fiscal_xml.json")
            old_status = None
            if os.path.exists(status_path):
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        old_status = json.load(f)
                except Exception:
                    pass
                    
            # Verificar se já possui arquivos XML baixados na pasta do cliente
            caminho_pasta = os.path.join("documentos de nota fiscal xml", f"{cnpj_clean}_{nome_limpo}")
            xmls_existentes = []
            if os.path.exists(caminho_pasta):
                try:
                    xmls_existentes = [f for f in os.listdir(caminho_pasta) if f.endswith(".xml")]
                except Exception:
                    pass
            possui_xml_existente = len(xmls_existentes) > 0
            
            log(f"--- Processando Cliente {idx+1}/{len(clientes_para_processar)}: {nome} (CNPJ: {cnpj}) ---", "INFO")
            salvar_estado_global(True, nome, total_clientes, processados, sucessos, falhas)
            
            client_dir = save_client_status_nota_fiscal_xml(cnpj, nome, "Pendente", "Iniciado")
            
            try:
                # 1. Navegar para a página inicial
                log("Acessando portal da NF-e...", "INFO")
                page.goto("https://www.nfe.fazenda.gov.br/portal/principal.aspx")
                page.wait_for_load_state("networkidle")
                
                # Disparar thread de confirmação do certificado se ainda não confirmado nesta sessão
                if not cert_confirmado:
                    import threading
                    def auto_confirm_dialog():
                        time.sleep(4.0)
                        log("[AUTO-LOGIN-NFE] Janela de seleção de certificado do Windows deve estar aberta. Simulando ENTER...", "SYSTEM")
                        press_enter(cert_first_char)
                        time.sleep(1.2)
                        press_enter()
                        
                    threading.Thread(target=auto_confirm_dialog, daemon=True).start()
                
                # 2. Clicar em Manifestação Destinatário
                log("Navegando para 'Manifestação Destinatário'...", "INFO")
                link_selector = 'a[href*="manifestacao"], a:has-text("Manifestação Destinatário"), a:has-text("Manifestacao Destinatario")'
                page.locator(link_selector).first.click()
                page.wait_for_load_state("networkidle")
                
                # Marcar como confirmado após passar da navegação de manifestação sem dar erro
                cert_confirmado = True
                
                # 3. Escolher a opção "Não tenho a Chave de Acesso"
                try:
                    rbt_sem_chave = page.locator('input#ctl00_ContentPlaceHolder1_rbtSemChave, input[value="rbtSemChave"]').first
                    if rbt_sem_chave.is_visible(timeout=5000):
                        log("Clicando diretamente no radio button 'Não tenho a Chave de Acesso'...", "INFO")
                        rbt_sem_chave.click()
                    else:
                        opcao_nao_tenho = page.locator('label:has-text("Não tenho a Chave de Acesso"), label:has-text("Nao tenho a Chave"), text="Não tenho a Chave de Acesso"').first
                        opcao_nao_tenho.wait_for(state="visible", timeout=5000)
                        log("Selecionando opção 'Não tenho a Chave de Acesso' via label...", "INFO")
                        opcao_nao_tenho.click()
                    time.sleep(1.5)
                except Exception as e_opt:
                    log(f"Aviso ao selecionar opção 'Não tenho a Chave': {e_opt}", "WARNING")
                
                 # 4. Preencher CNPJ
                log("Verificando campos de CNPJ do cliente...", "INFO")
                cnpj_base_loc = page.locator('input#ctl00_ContentPlaceHolder1_iptCNPJBase, input[name*="iptCNPJBase"]')
                cnpj_fim_loc = page.locator('input#ctl00_ContentPlaceHolder1_iptCNPJ, input[name="ctl00$ContentPlaceHolder1$iptCNPJ"]')
                
                is_readonly = False
                cnpj_preenchido = ""
                
                if cnpj_base_loc.is_visible(timeout=5000):
                    is_readonly = (
                        cnpj_base_loc.is_disabled() or 
                        cnpj_base_loc.get_attribute("readonly") == "readonly" or 
                        cnpj_base_loc.get_attribute("disabled") == "disabled" or
                        "aspNetDisabled" in (cnpj_base_loc.get_attribute("class") or "")
                    )
                    val_base = cnpj_base_loc.input_value() or ""
                    val_fim = cnpj_fim_loc.input_value() or ""
                    cnpj_preenchido = "".join(filter(str.isdigit, val_base + val_fim))
                    
                if is_readonly:
                    log(f"Campos de CNPJ estão bloqueados/somente-leitura. CNPJ preenchido no portal: '{cnpj_preenchido}'", "INFO")
                    if cnpj_preenchido == cnpj_clean:
                        log("O CNPJ preenchido corresponde ao cliente atual. Prosseguindo sem preencher...", "SUCCESS")
                    else:
                        msg_erro = f"Certificado ativo no portal ({cnpj_preenchido}) é diferente do cliente ({cnpj_clean}) e o campo está bloqueado."
                        log(f"[AVISO] {msg_erro}", "WARNING")
                        raise Exception(msg_erro)
                else:
                    log("Campos de CNPJ editáveis. Preenchendo CNPJ do cliente...", "INFO")
                    cnpj_inputs = page.locator('input[name*="CNPJ"], input[name*="Cnpj"], input[id*="CNPJ"]').all()
                    if len(cnpj_inputs) == 1:
                        cnpj_inputs[0].fill(cnpj_clean)
                    elif len(cnpj_inputs) >= 2:
                        cnpj_inputs[0].fill(cnpj_clean[:8])
                        cnpj_inputs[1].fill(cnpj_clean[8:])
                    else:
                        raise Exception("Campos de CNPJ não localizados na tela.")
                    
                # 5. Aguardar o CAPTCHA
                captcha_ok = esperar_captcha(page, nome, cnpj, "Manifestação", config, destinatario)
                if not captcha_ok:
                    raise Exception("Timeout ou falha na resolução do CAPTCHA")
                    
                # 6. Clicar em Pesquisar
                log("Clicando em Pesquisar...", "INFO")
                btn_pesquisar_selector = 'input[value="Pesquisar"], input[name*="Pesquisar"], input[name*="btnPesquisar"], button:has-text("Pesquisar"), input[name*="btnConsultar"]'
                page.locator(btn_pesquisar_selector).first.click()
                page.wait_for_load_state("networkidle")
                
                # 7. Verificar se não existem registros
                time.sleep(2.5)
                conteudo_html = page.content()
                conteudo_visivel = page.locator("body").inner_text()
                
                if "Não existe registro para os dados informados" in conteudo_visivel:
                    log("Nenhum registro de manifestação encontrado para este cliente.", "INFO")
                    save_client_status_nota_fiscal_xml(cnpj, nome, "Sucesso", "Sem Registros")
                    sucessos += 1
                    processados += 1
                    
                    hora_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    resultados_excel_hoje.append([cnpj, nome, "N/A", "Sem Registros", hora_atual])
                    
                    salvar_estado_global(True, nome, total_clientes, processados, sucessos, falhas)
                    gerar_excel_resumo(resultados_excel_hoje)
                    continue
                    
                # 8. Copiar chaves de acesso (44 dígitos) buscando em todo o HTML
                chaves = list(dict.fromkeys(re.findall(r'\b\d{44}\b', conteudo_html)))
                
                if not chaves:
                    log("Aviso: Chave de acesso não localizada na página. Verifique manualmente.", "WARNING")
                    msg_erro = "Chave de acesso não localizada na página."
                    if "Erro" in conteudo_visivel:
                        msg_erro = "Erro reportado pelo portal na consulta."
                    raise Exception(msg_erro)
                    
                log(f"Localizada(s) {len(chaves)} chave(s) de manifestação na tela. Iniciando downloads...", "SUCCESS")
                
                chaves_baixadas = 0
                for chave in chaves:
                    log(f"Baixando NF-e para a Chave: {chave}", "INFO")
                    
                    # Voltar para a página inicial
                    page.goto("https://www.nfe.fazenda.gov.br/portal/principal.aspx")
                    page.wait_for_load_state("networkidle")
                    
                    # Clicar em Consultar NF-e
                    page.locator('a[href*="tipoConsulta=resumo"]').first.click()
                    page.wait_for_load_state("networkidle")
                    
                    # Preencher chave de acesso
                    input_chave_selector = 'input[name="ctl00$ContentPlaceHolder1$txtChaveAcessoResumo"]'
                    page.wait_for_selector(input_chave_selector)
                    page.locator(input_chave_selector).fill(chave)
                    
                    # Aguardar CAPTCHA
                    captcha_nfe_ok = esperar_captcha(page, nome, cnpj, "Consulta NFe", config, destinatario)
                    if not captcha_nfe_ok:
                        log(f"Falha de captcha na chave {chave}. Pulando esta chave.", "ERROR")
                        resultados_excel_hoje.append([cnpj, nome, chave, "Erro no Captcha", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                        continue
                        
                    # Clicar continuar
                    log("Clicando em Continuar para carregar a nota...", "INFO")
                    page.locator('input[name="ctl00$ContentPlaceHolder1$btnConsultarHCaptcha"]').first.click()
                    page.wait_for_load_state("networkidle")
                    
                    # Baixar documento
                    try:
                        seletor_download = "input#ctl00_ContentPlaceHolder1_btnDownload, input#btnDownload, a#btnDownload, #btnDownload, input[value*='Download'], button:has-text('Download')"
                        page.wait_for_selector(seletor_download, timeout=15000)
                        
                        log("Botão de Download localizado. Clicando...", "INFO")
                        with page.expect_download(timeout=45000) as download_info:
                            page.locator(seletor_download).first.click()
                            
                        download = download_info.value
                        nome_arquivo = download.suggested_filename
                        
                        pasta_destino = os.path.join("documentos de nota fiscal xml", f"{cnpj_clean}_{clean_filename(nome)}")
                        os.makedirs(pasta_destino, exist_ok=True)
                        
                        caminho_salvar = os.path.join(pasta_destino, nome_arquivo)
                        download.save_as(caminho_salvar)
                        
                        log(f"Nota salva com sucesso em: {caminho_salvar}", "SUCCESS")
                        chaves_baixadas += 1
                        
                        hora_atual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        resultados_excel_hoje.append([cnpj, nome, chave, "Baixado", hora_atual])
                        
                    except Exception as e_dl:
                        log(f"Falha ao realizar download da chave {chave}: {e_dl}", "ERROR")
                        resultados_excel_hoje.append([cnpj, nome, chave, "Erro no Download", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                        
                if chaves_baixadas > 0:
                    save_client_status_nota_fiscal_xml(cnpj, nome, "Sucesso", f"Baixados {chaves_baixadas} chaves")
                    sucessos += 1
                else:
                    forcar_todos = "--forcar-todos" in sys.argv
                    if not forcar_todos and possui_xml_existente:
                        log(f"[RECOVERY] Nenhuma chave nova baixada para {nome} ({cnpj}), mas mantendo os XMLs existentes e ignorando a falha.", "SUCCESS")
                        status_restaurado = "Sucesso"
                        detalhes_restaurados = "Preservado (Erro no download das novas chaves)"
                        if old_status and old_status.get("status") == "Sucesso":
                            detalhes_restaurados = old_status.get("detalhes", detalhes_restaurados)
                        save_client_status_nota_fiscal_xml(cnpj, nome, status_restaurado, detalhes_restaurados)
                        sucessos += 1
                    else:
                        save_client_status_nota_fiscal_xml(cnpj, nome, "Erro", "Chaves encontradas, mas nenhuma baixada")
                        falhas += 1
                    
                processados += 1
                
            except Exception as err_cliente:
                forcar_todos = "--forcar-todos" in sys.argv
                if not forcar_todos and possui_xml_existente:
                    log(f"[RECOVERY] Falha ao processar {nome} ({cnpj}), mas mantendo os XMLs existentes e ignorando o erro de consulta.", "SUCCESS")
                    status_restaurado = "Sucesso"
                    detalhes_restaurados = "Preservado (Erro na nova consulta)"
                    if old_status and old_status.get("status") == "Sucesso":
                        detalhes_restaurados = old_status.get("detalhes", detalhes_restaurados)
                    save_client_status_nota_fiscal_xml(cnpj, nome, status_restaurado, detalhes_restaurados)
                    sucessos += 1
                else:
                    log(f"Erro no processamento do cliente {nome}: {err_cliente}", "ERROR")
                    save_client_status_nota_fiscal_xml(cnpj, nome, "Erro", str(err_cliente))
                    falhas += 1
                
                processados += 1
                
                resultados_excel_hoje.append([cnpj, nome, "N/A", f"Erro: {str(err_cliente)[:50]}", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                
            salvar_estado_global(True, nome, total_clientes, processados, sucessos, falhas)
            gerar_excel_resumo(resultados_excel_hoje)
            
            # Atraso de 5 segundos para acompanhamento visual do processo na tela
            log("Aguardando 5 segundos antes de prosseguir para o próximo cliente...", "INFO")
            time.sleep(5)
            
        context.close()
        log("Varredura de Nota Fiscal XML finalizada com sucesso.", "SUCCESS")
        salvar_estado_global(False, "Varredura Concluída", total_clientes, processados, sucessos, falhas)

if __name__ == "__main__":
    main()
