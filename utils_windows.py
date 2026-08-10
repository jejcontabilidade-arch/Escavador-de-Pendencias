import time
import ctypes
import datetime

def log_utils(msg, level="SYSTEM"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def dialogo_certificado_aberto():
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    
    aberto = [False]
    
    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            title = buff.value
            title_lower = title.lower()
            
            # Blacklist para evitar planilhas, códigos e editores abertos do usuário
            blacklist = ["- excel", "- word", "- notepad", "visual studio", "code", ".py", ".xlsx", ".xls", "cmd.exe", "powershell", "escavador"]
            if any(b in title_lower for b in blacklist):
                return True
                
            termos_cert = ["selecione um certificado", "selecione o certificado", "confirmar certificado", 
                           "select a certificate", "confirm certificate", "segurança do windows", 
                           "windows security", "credenciais de segurança", "security credentials", 
                           "pin do certificado", "insira o pin", "controle de acesso"]
            if any(t in title_lower for t in termos_cert) or (any(x in title_lower for x in ["certificado", "segurança"]) and not any(b in title_lower for b in blacklist)):
                aberto[0] = True
                return False
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    return aberto[0]

def focar_janela_certificado(keywords_browser):
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
            
            # Blacklist para evitar planilhas, códigos e editores abertos do usuário
            blacklist = ["- excel", "- word", "- notepad", "visual studio", "code", ".py", ".xlsx", ".xls", "cmd.exe", "powershell", "escavador"]
            if any(b in title_lower for b in blacklist):
                return True
                
            termos_cert = ["selecione um certificado", "selecione o certificado", "confirmar certificado", 
                           "select a certificate", "confirm certificate", "segurança do windows", 
                           "windows security", "credenciais de segurança", "security credentials", 
                           "pin do certificado", "insira o pin", "controle de acesso"]
            
            # 1. Diálogos de certificado ou segurança
            if any(t in title_lower for t in termos_cert) or (any(x in title_lower for x in ["certificado", "segurança"]) and not any(b in title_lower for b in blacklist)):
                found_hwnds.append((hwnd, title, 2))
            # 2. Janela do navegador da nossa automação
            elif any(x in title_lower for x in keywords_browser):
                found_hwnds.append((hwnd, title, 1))
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if not found_hwnds:
        log_utils("[AUTO-LOGIN] Nenhuma janela de certificado ou navegador encontrada para focar.", "WARNING")
        return False
        
    found_hwnds.sort(key=lambda x: x[2], reverse=True)
    target_hwnd, title, priority = found_hwnds[0]
    
    log_utils(f"[AUTO-LOGIN] Janela alvo encontrada (Prioridade {priority}): '{title}'", "SYSTEM")
    try:
        current_active = ctypes.windll.user32.GetForegroundWindow()
        if current_active != target_hwnd:
            # Simula toque no ALT para destravar SetForegroundWindow
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            ShowWindow(target_hwnd, 9) # SW_RESTORE
            SetForegroundWindow(target_hwnd)
            time.sleep(0.5)
        else:
            log_utils("[AUTO-LOGIN] Janela alvo já está ativa. Ignorando refocus.", "SYSTEM")
        return True
    except Exception as e:
        log_utils(f"[AUTO-LOGIN] Erro ao focar janela: {e}", "WARNING")
        return False

def press_enter(browser_keywords, first_char=None):
    focar_janela_certificado(browser_keywords)
    if first_char:
        char_upper = first_char.upper()
        if len(char_upper) == 1 and (char_upper.isalnum() or char_upper == " "):
            vk_code = ord(char_upper)
            log_utils(f"Enviando tecla '{char_upper}' (VK: {hex(vk_code)}) para focar no certificado...", "SYSTEM")
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0) # Key Down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0) # Key Up
            time.sleep(0.5)
            
    log_utils("Enviando comando ENTER para o Windows...", "SYSTEM")
    VK_RETURN = 0x0D
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0) # Key Down
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 2, 0) # Key Up
    log_utils("ENTER enviado.", "SYSTEM")

def executar_confirmacao_certificado_em_loop(config, log_prefix, browser_keywords):
    first_char = config.get("cert_first_char", "J")
    log_utils(f"{log_prefix} Iniciando rotina de confirmacao de certificado SSL (Letra: '{first_char}')...", "SYSTEM")
    
    # Aguarda 3.5 segundos para a janela do Chrome iniciar o redirecionamento e abrir o diálogo
    time.sleep(3.5)
    
    # Realiza 3 tentativas espaçadas de focar e dar ENTER
    for attempt in range(1, 4):
        log_utils(f"{log_prefix} Tentativa {attempt}/3 de confirmacao...", "SYSTEM")
        press_enter(browser_keywords, first_char if attempt == 1 else None)
        time.sleep(1.5)
        
    log_utils(f"{log_prefix} Rotina de confirmacao concluida.", "SUCCESS")

def clean_filename(name):
    return "".join(c if c.isalnum() or c in " _-ÇçÁáÉéÍíÓóÚúÃãÕõÂâÊêÔôÀàÜü" else "_" for c in name).strip()

def format_cnpj(cnpj):
    c = "".join(filter(str.isdigit, str(cnpj)))
    if 11 < len(c) <= 14:
        c = c.zfill(14)
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    elif 0 < len(c) <= 11:
        c = c.zfill(11)
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return cnpj
