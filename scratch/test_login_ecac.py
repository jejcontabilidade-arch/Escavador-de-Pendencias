import sys
import os
import time
import json
import ctypes
import threading
from playwright.sync_api import sync_playwright

# Configura encoding UTF-8 para stdout do Python no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def log(msg, level="INFO"):
    print(f"[{level}] {msg}")

def list_all_windows():
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    GetClassName = ctypes.windll.user32.GetClassNameW

    print("\n=== LISTA DE JANELAS VISÍVEIS NO WINDOWS ===")
    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            title = buff.value
            
            class_buff = ctypes.create_unicode_buffer(256)
            GetClassName(hwnd, class_buff, 256)
            class_name = class_buff.value
            
            print(f"  HWND: {hwnd} | Class: {class_name} | Title: {repr(title)}")
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    print("============================================\n")

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
            
            blacklist = ["- excel", "- word", "- notepad", "visual studio", "code", ".py", ".xlsx", ".xls", "cmd.exe", "powershell", "escavador"]
            if any(b in title_lower for b in blacklist):
                return True
                
            termos_cert = ["selecione um certificado", "selecione o certificado", "confirmar certificado", 
                           "select a certificate", "confirm certificate", "segurança do windows", 
                           "windows security", "credenciais de segurança", "security credentials", 
                           "pin do certificado", "insira o pin", "controle de acesso"]
            
            if any(t in title_lower for t in termos_cert) or (any(x in title_lower for x in ["certificado", "segurança"]) and not any(b in title_lower for b in blacklist)):
                found_hwnds.append((hwnd, title, 2))
            elif any(x in title_lower for x in keywords_browser):
                found_hwnds.append((hwnd, title, 1))
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if not found_hwnds:
        log("Nenhuma janela de certificado ou navegador encontrada para focar.", "WARNING")
        return False
        
    found_hwnds.sort(key=lambda x: x[2], reverse=True)
    target_hwnd, title, priority = found_hwnds[0]
    
    log(f"Janela alvo encontrada (Prioridade {priority}): {repr(title)}")
    try:
        current_active = ctypes.windll.user32.GetForegroundWindow()
        if current_active != target_hwnd:
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            ShowWindow(target_hwnd, 9)
            SetForegroundWindow(target_hwnd)
            time.sleep(0.5)
        else:
            log("Janela alvo já está ativa. Ignorando refocus.")
        return True
    except Exception as e:
        log(f"Erro ao focar janela: {e}", "WARNING")
        return False

def press_enter(keywords, first_char=None):
    focar_janela_certificado(keywords)
    if first_char:
        char_upper = first_char.upper()
        if len(char_upper) == 1 and (char_upper.isalnum() or char_upper == " "):
            vk_code = ord(char_upper)
            log(f"Enviando tecla '{char_upper}' (VK: {hex(vk_code)}) para focar no certificado...")
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
            time.sleep(0.5)
            
    log("Enviando comando ENTER para o Windows...")
    VK_RETURN = 0x0D
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 2, 0)
    log("ENTER enviado.")

def test_login_ecac():
    log("=== INICIANDO TESTE DE LOGIN E-CAC COM CERTIFICADO ===", "INFO")
    
    # Carregar configurações
    config = {}
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            
    cert_first_char = config.get("cert_first_char", "J")
    log(f"Tecla do certificado configurada: '{cert_first_char}'")
    
    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "temp", "chrome_profile_chrome")
        os.makedirs(user_data_dir, exist_ok=True)
        
        # Iniciar navegador visível
        log("Iniciando navegador Chrome visível...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=False,
            no_viewport=True
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        # Acessa e-CAC
        log("Navegando para o portal do e-CAC...")
        page.goto("https://cav.receita.fazenda.gov.br/ecac/", timeout=30000)
        page.wait_for_load_state("load")
        
        # Dispara thread de confirmação em loop com logs verbosos IMEDIATAMENTE antes de começar o login
        def run_confirm():
            log("[THREAD] Iniciando loop de monitoramento de diálogo do certificado...", "SYSTEM")
            
            # Print de diagnóstico inicial das janelas abertas
            list_all_windows()
            
            # Espera até 20 segundos pelo diálogo
            dialogo_surgiu = False
            for i in range(40): # 40 * 0.5s = 20s
                if dialogo_certificado_aberto():
                    dialogo_surgiu = True
                    break
                time.sleep(0.5)
                
            if not dialogo_surgiu:
                log("[THREAD] Timeout: Diálogo de certificado não foi detectado como janela ativa no SO.", "WARNING")
                log("[THREAD] Listando todas as janelas do SO para depurar...", "WARNING")
                list_all_windows()
                return
                
            log("[THREAD] Diálogo de certificado detectado! Listando janelas ativas no momento do surgimento:", "SYSTEM")
            list_all_windows()
            
            # Tentativas de envio de teclado
            keywords_browser = ["e-cac", "cav.receita", "receita federal", "chrome", "edge"]
            for attempt in range(1, 6):
                if not dialogo_certificado_aberto():
                    log("[THREAD] O diálogo do certificado sumiu! Confirmado com sucesso.", "SUCCESS")
                    break
                    
                log(f"[THREAD] Tentativa {attempt}/5 de confirmação...")
                
                # Exibe qual janela está com o foco atual no Windows
                active_hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(active_hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(active_hwnd, buff, length + 1)
                log(f"[THREAD] Janela ativa no SO antes do foco: HWND {active_hwnd} | Title: {repr(buff.value)}")
                
                # Executa
                press_enter(keywords_browser, cert_first_char if attempt == 1 else None)
                
                time.sleep(1.5)
                
            if dialogo_certificado_aberto():
                log("[THREAD] O diálogo continua aberto após 5 tentativas de confirmação.", "ERROR")
                
        t = threading.Thread(target=run_confirm, daemon=True)
        t.start()

        # Clica no botão de login Gov.br
        log("Aguardando botão 'Acesso Gov BR'...")
        page.wait_for_selector('input[alt="Acesso Gov BR"]', timeout=10000)
        log("Clicando no botão de login do Gov.br...")
        page.click('input[alt="Acesso Gov BR"]')
        
        # Aguarda concorrentemente o botão do certificado digital ou o painel logado
        log("Aguardando redirecionamento de login ou painel logado...")
        try:
            page.wait_for_selector('button#login-certificate, #login-certificate, text=Alterar perfil de acesso', timeout=15000)
        except Exception as e_wait:
            log(f"Aviso na espera de redirecionamento (pode ter logado direto): {e_wait}")
        
        # Se o botão do certificado digital estiver visível, clica nele
        try:
            btn_cert = page.locator('button#login-certificate, #login-certificate').first
            if btn_cert.is_visible(timeout=3000):
                log("Clicando no botão 'Seu certificado digital' no navegador...")
                btn_cert.click()
        except Exception:
            log("Botão 'Seu certificado digital' não visível ou já redirecionado.")
        
        # Aguarda sucesso no login
        log("Aguardando alteração de página para o perfil do e-CAC (timeout de 25s)...")
        try:
            page.wait_for_selector("text=Alterar perfil de acesso", timeout=25000)
            log("LOGIN EFETUADO COM SUCESSO NO TESTE DO e-CAC!", "SUCCESS")
        except Exception as err:
            log(f"O login não concluiu: {err}", "ERROR")
            
            # Salvar screenshot de erro
            os.makedirs("temp", exist_ok=True)
            screenshot_path = os.path.join("temp", "screenshot_erro_login_ecac.png")
            page.screenshot(path=screenshot_path)
            log(f"Screenshot da tela salva em: {screenshot_path}", "INFO")
            
        time.sleep(3)
        context.close()

if __name__ == "__main__":
    test_login_ecac()
