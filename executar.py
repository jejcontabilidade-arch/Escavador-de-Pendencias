import os
import sys
import csv
import time
import json
import ctypes
import datetime
from playwright.sync_api import sync_playwright, TimeoutError
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Configuração de Logs
def log(msg, level="INFO"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")
    
    # Salvar em arquivo de log
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    with open(os.path.join(log_dir, f"execucao_{today}.log"), "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {msg}\n")

# Enviar o caractere inicial (se fornecido) e depois a tecla ENTER para o Windows
def press_enter(first_char=None):
    if first_char:
        char_upper = first_char.upper()
        # Apenas converte se for uma letra de A-Z ou número de 0-9
        if len(char_upper) == 1 and (char_upper.isalnum() or char_upper == " "):
            vk_code = ord(char_upper)
            log(f"Enviando tecla '{char_upper}' (VK: {hex(vk_code)}) para focar no certificado...", "SYSTEM")
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0) # Key Down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0) # Key Up
            time.sleep(0.5) # Pequeno atraso para a seleção atualizar na tela
            
    log("Enviando comando ENTER para o Windows...", "SYSTEM")
    VK_RETURN = 0x0D
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0) # Key Down
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 2, 0) # Key Up
    log("ENTER enviado.", "SYSTEM")

# Função auxiliar para fechar modais jQuery UI e Caixa Postal que cobrem a tela
def fechar_modais_e_overlays(page):
    try:
        # 1. Tentar fechar pelo botão (X) do dialog jQuery UI
        btn_close = page.locator(".ui-dialog-titlebar-close, button:has-text('Close'), button[title='Close']").first
        if btn_close.is_visible():
            log("[MODAL-CLEANUP] Botão de fechar (X) detectado. Clicando...", "INFO")
            btn_close.click(timeout=1500)
            time.sleep(0.5)
    except Exception:
        pass

    try:
        # 2. Enviar a tecla ESCAPE para fechar diálogos ativos
        page.keyboard.press("Escape")
    except Exception:
        pass

    try:
        # 3. Remover fisicamente qualquer overlay/dialog do DOM para garantir 100% de passagem e evitar cliques interceptados
        overlays = page.locator(".ui-widget-overlay, .ui-dialog, .ui-widget-shadow")
        if overlays.first.is_visible():
            log("[MODAL-CLEANUP] Removendo modais/overlays remanescentes do DOM...", "WARNING")
            page.evaluate("""
                document.querySelectorAll('.ui-widget-overlay, .ui-dialog, .ui-widget-shadow, .ui-dialog-buttonpane').forEach(el => {
                    el.style.display = 'none';
                    el.remove();
                });
            """)
            time.sleep(0.3)
    except Exception as e:
        log(f"[MODAL-CLEANUP] Falha ao limpar DOM via JS: {e}", "WARNING")

# Função auxiliar para checar e tratar a Caixa Postal bloqueante (lendo mensagens importantes para unblock)
def checar_e_tratar_caixa_postal(page, client_dir, config):
    try:
        # Detectar se o modal de aviso bloqueante está presente
        btn_caixa = None
        for selector in [
            "button:has-text('Ir para a Caixa Postal')",
            "input[value='Ir para a Caixa Postal']",
            "text=Ir para a Caixa Postal"
        ]:
            try:
                loc = page.locator(selector).first
                if loc.is_visible(timeout=1000):
                    btn_caixa = loc
                    break
            except Exception:
                continue
        
        if btn_caixa:
            log("[ALERTA CRÍTICO] Caixa Postal bloqueante detectada! O e-CAC exige a leitura de mensagens importantes para unblock.", "WARNING")
            
            # Clicar em "Ir para a Caixa Postal"
            btn_caixa.click()
            page.wait_for_load_state("load")
            page.wait_for_timeout(2000)
            
            # Buscar e abrir a mensagem com indicativo de alerta (!) ou não lida
            mensagem_aberta = False
            for sel in [
                "tr:has-text('!') a",
                "tr.nao-lida a",
                "td.assunto a",
                "a:has-text('ALERTA')",
                "a:has-text('risco')",
                "a[href*='Mensagem']",
                "//tr[contains(., '!')]//a"
            ]:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        log(f"[CAIXA-POSTAL] Abrindo mensagem importante: '{loc.inner_text().strip()}'", "ACTION")
                        loc.click()
                        mensagem_aberta = True
                        break
                except Exception:
                    continue
            
            if mensagem_aberta:
                page.wait_for_timeout(2000)
                
                # Extrair assunto e conteúdo da mensagem
                assunto = ""
                conteudo = ""
                try:
                    assunto = page.locator("h1, h2, .titulo-mensagem, td.assunto").first.inner_text().strip()
                except Exception:
                    assunto = "Alerta Importante e-CAC"
                    
                try:
                    conteudo = page.locator("body").inner_text().strip()
                except Exception:
                    conteudo = "Não foi possível extrair o corpo completo da mensagem."
                
                log(f"[CAIXA-POSTAL] Alerta de Caixa Postal extraído: '{assunto[:60]}...'", "SUCCESS")
                
                # Gravar arquivo de alerta TXT e JSON para estruturação fácil no Excel
                alerta_path = os.path.join(client_dir, "ALERTA_CAIXA_POSTAL.txt")
                with open(alerta_path, "w", encoding="utf-8") as f:
                    f.write("============================================================\n")
                    f.write(" MENSAGEM IMPORTANTE / ALERTA DE EXCLUSÃO CAPTURADO NO e-CAC\n")
                    f.write("============================================================\n")
                    f.write(f"Data Captura : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                    f.write(f"Assunto      : {assunto}\n")
                    f.write(f"Conteúdo     :\n\n{conteudo}\n")
                
                alerta_json_path = os.path.join(client_dir, "ALERTA_CAIXA_POSTAL.json")
                with open(alerta_json_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "assunto": assunto,
                        "conteudo": conteudo,
                        "data_captura": datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                    }, f, indent=4, ensure_ascii=False)
                
                log(f"[CAIXA-POSTAL] Alerta salvo com sucesso em TXT e JSON: {client_dir}", "SUCCESS")
                
                # Retornar para a Home do e-CAC para resetar e continuar o fluxo sem o modal bloqueante!
                log("[CAIXA-POSTAL] Retornando para a página inicial do e-CAC para prosseguir...", "ACTION")
                page.goto(config["portal_url"])
                page.wait_for_selector("text=Alterar perfil de acesso", timeout=10000)
                
            else:
                log("[CAIXA-POSTAL] Caixa Postal aberta, mas não foi possível localizar a mensagem unread correspondente.", "WARNING")
                
    except Exception as e:
        log(f"Aviso ao tentar tratar Caixa Postal bloqueante: {e}. Prosseguindo com o fluxo...", "WARNING")

# Função auxiliar para garantir que a sessão com o e-CAC está ativa e realizar login se necessário
def verificar_e_reestabelecer_sessao(page, config):
    log("Verificando se a sessão com o e-CAC está ativa...", "INFO")
    try:
        # Acessa a URL principal
        page.goto(config["portal_url"])
        fechar_modais_e_overlays(page)
        
        # Tenta esperar pelo elemento do painel autenticado
        page.wait_for_selector("text=Alterar perfil de acesso", timeout=8000)
        log("Sessão e-CAC validada e ativa.", "SUCCESS")
        return True
    except Exception:
        log("Sessão expirada ou deslogada. Tentando reestabelecer login automaticamente...", "WARNING")
        
        try:
            # Se não estiver no e-CAC, vai para a página inicial
            if "cav.receita.fazenda.gov.br" not in page.url:
                page.goto("https://cav.receita.fazenda.gov.br/ecac/")
            
            # Se o botão de login do Gov.br estiver visível, clica nele
            btn_gov = page.locator('input[alt="Acesso Gov BR"]').first
            if btn_gov.is_visible(timeout=5000):
                log("Botão 'Acesso Gov BR' detectado. Clicando...", "ACTION")
                btn_gov.click()
                page.wait_for_timeout(2000)
                
            # Aguarda o botão do certificado
            page.wait_for_selector('button#login-certificate, #login-certificate', timeout=15000)
            
            # Dispara a thread para dar ENTER
            import threading
            def auto_confirm_dialog():
                time.sleep(3.5)
                log("[AUTO-LOGIN-RETRY] Janela de seleção do Windows deve estar aberta. Simulando ENTER...", "SYSTEM")
                press_enter()
                time.sleep(1.2)
                press_enter()
                
            threading.Thread(target=auto_confirm_dialog, daemon=True).start()
            
            log("Clicando no botão 'Seu certificado digital'...", "ACTION")
            page.click('button#login-certificate')
            
            # Aguarda o painel
            page.wait_for_selector("text=Alterar perfil de acesso", timeout=45000)
            log("Login restabelecido com sucesso na sessão ativa!", "SUCCESS")
            
            # Salvar o estado da sessão atualizado em state.json
            try:
                page.context.storage_state(path="state.json")
                log("Sessão salva com sucesso em 'state.json'.", "SUCCESS")
            except Exception as e:
                log(f"Erro ao salvar estado da sessão: {e}", "WARNING")
                
            return True
        except Exception as e:
            log(f"Falha ao tentar reestabelecer login automaticamente: {e}. Solicitando intervenção manual se necessário...", "ERROR")
            if not config["headless"]:
                log("Aguardando login manual na tela (limite de 120 segundos)...", "IMPORTANT")
                try:
                    page.wait_for_selector("text=Alterar perfil de acesso", timeout=120000)
                    log("Login manual detectado com sucesso!", "SUCCESS")
                    try:
                        page.context.storage_state(path="state.json")
                    except Exception:
                        pass
                    return True
                except Exception:
                    pass
            return False

# Carregar arquivo de configuração
def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "headless": False,
        "timeout_ms": 30000,
        "relatorios_dir": "relatorios",
        "clientes_file": "clientes.csv",
        "portal_url": "https://cav.receita.fazenda.gov.br/eCAC/Default.aspx#",
        "download_timeout_ms": 60000
    }

# Carregar lista de clientes
def load_clients(filepath):
    clients = []
    if not os.path.exists(filepath):
        log(f"Arquivo de clientes não encontrado: {filepath}", "ERROR")
        return clients
        
    try:
        # Detectar e abrir com suporte a UTF-8-BOM (comum em exports do Excel no Windows)
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            
            # Normalizar os nomes das colunas (remover espaços e colocar em minúsculas)
            raw_headers = reader.fieldnames if reader.fieldnames else []
            headers = [h.strip().lower() if h else "" for h in raw_headers]
            
            # Mapeamento inteligente e flexível de colunas
            col_cnpj = next((h for h in headers if h in ["cnpj", "c.n.p.j.", "cnpj_cliente", "documento"]), "cnpj")
            col_nome = next((h for h in headers if h in ["nome", "nome_cliente", "razao_social", "razao social", "cliente", "nome cliente"]), "nome")
            col_ativo = next((h for h in headers if h in ["ativo", "active", "status", "habilitado"]), "ativo")
            
            log(f"Colunas mapeadas do CSV: CNPJ -> '{col_cnpj}', Nome -> '{col_nome}', Ativo -> '{col_ativo}'", "INFO")
            
            for row in reader:
                raw_cnpj = ""
                raw_nome = ""
                raw_ativo = "True"
                
                # Buscar valores contornando possíveis diferenças de caixa e espaços no CSV
                for k, v in row.items():
                    if not k:
                        continue
                    k_lower = k.strip().lower()
                    if k_lower == col_cnpj:
                        raw_cnpj = v
                    elif k_lower == col_nome:
                        raw_nome = v
                    elif k_lower == col_ativo:
                        raw_ativo = v
                
                # Higienização dos dados extraídos
                cnpj = "".join(filter(str.isdigit, raw_cnpj or ""))
                nome = (raw_nome or "").strip()
                ativo = (raw_ativo or "True").strip().lower() in ["true", "1", "yes", "ativo", "sim", "s"]
                
                # Fallback de segurança para evitar colapsar caminhos se o nome estiver em branco
                if cnpj and not nome:
                    nome = f"Cliente_{cnpj}"
                    
                if cnpj:
                    clients.append({"cnpj": cnpj, "nome": nome, "ativo": ativo})
                    
        log(f"Carregados com sucesso {len(clients)} clientes a partir de '{filepath}'.", "SUCCESS")
    except Exception as e:
        log(f"Erro crítico ao ler o arquivo de clientes '{filepath}': {e}", "ERROR")
        
    return clients


# Salvar status do processamento do cliente
def save_client_status(relatorios_dir, cnpj, nome, status, details=""):
    today = datetime.date.today().strftime("%Y-%m-%d")
    month = datetime.date.today().strftime("%Y-%m")
    # Limpar nome para criar pasta segura, mantendo letras acentuadas, cedilhas e espaços
    nome_limpo = "".join(c if c.isalnum() or c in " _-ÇçÁáÉéÍíÓóÚúÃãÕõÂâÊêÔôÀàÜü" else "_" for c in nome).strip()
    client_dir = os.path.join(relatorios_dir, nome_limpo, month)
    os.makedirs(client_dir, exist_ok=True)
    
    status_data = {
        "cnpj": cnpj,
        "nome": nome,
        "data_consulta": today,
        "hora_consulta": datetime.datetime.now().strftime("%H:%M:%S"),
        "status": status,
        "detalhes": details
    }
    
    with open(os.path.join(client_dir, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=4, ensure_ascii=False)
        
    return client_dir

def format_cnpj(cnpj):
    if len(cnpj) == 14:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    elif len(cnpj) == 11:
        return f"{cnpj[:3]}.{cnpj[3:6]}.{cnpj[6:9]}-{cnpj[9:]}"
    return cnpj

def clean_filename(name):
    return "".join(c if c.isalnum() or c in " _-ÇçÁáÉéÍíÓóÚúÃãÕõÂâÊêÔôÀàÜü" else "_" for c in name).strip()

def gerar_consolidado_excel(clientes, relatorios_dir, output_path):
    log(f"Iniciando a geração do Painel Excel Consolidado: {output_path}", "INFO")
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        month_str = datetime.date.today().strftime("%Y-%m")
        rows_data = []
        
        for c in clientes:
            cnpj_raw = c["cnpj"]
            nome_raw = c["nome"]
            ativo = c["ativo"]
            
            if not ativo:
                rows_data.append({
                    "cnpj": format_cnpj(cnpj_raw),
                    "nome": nome_raw,
                    "status": "Inativo",
                    "detalhes": "Ignorado",
                    "data_hora": "-",
                    "observacao": "Cliente inativo no cadastro"
                })
                continue
                
            nome_limpo = clean_filename(nome_raw)
            status_path = os.path.join(relatorios_dir, nome_limpo, month_str, "status.json")
            
            status = "Pendente"
            detalhes = "Não Consultado"
            data_hora = "-"
            observacao = "Aguardando processamento"
            
            if os.path.exists(status_path):
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        status = data.get("status", "Pendente")
                        detalhes = data.get("detalhes", "Não Consultado")
                        data_hora = f"{data.get('data_consulta', today_str)} {data.get('hora_consulta', '')}".strip()
                        if status == "Erro":
                            observacao = detalhes
                            detalhes = "Falha no Processamento"
                        elif status == "Sucesso":
                            if "Certidão" in detalhes:
                                observacao = "CND emitida com sucesso (Sem Pendências)"
                            elif "Sem Pendências" in detalhes:
                                observacao = "Regular na Receita Federal (Informativo Gravado)"
                            elif "Relatório" in detalhes:
                                observacao = "Pendências tributárias ativas (Relatório PDF baixado)"
                            else:
                                observacao = "Concluído com sucesso"
                except Exception as e:
                    observacao = f"Erro ao ler status: {e}"
                    
            # Verifica se há alertas de Caixa Postal capturados para este cliente
            alerta_file = os.path.join(relatorios_dir, nome_limpo, month_str, "ALERTA_CAIXA_POSTAL.txt")
            alerta_json = os.path.join(relatorios_dir, nome_limpo, month_str, "ALERTA_CAIXA_POSTAL.json")
            alerta_texto = "-"
            
            if os.path.exists(alerta_json):
                try:
                    with open(alerta_json, "r", encoding="utf-8") as f_json:
                        alerta_data = json.load(f_json)
                        alerta_texto = f"ASSUNTO: {alerta_data.get('assunto')}\n\nMENSAGEM:\n{alerta_data.get('conteudo')}"
                except Exception:
                    alerta_texto = "Erro ao carregar mensagem."
            elif os.path.exists(alerta_file):
                alerta_texto = "Alerta capturado (Veja o arquivo ALERTA_CAIXA_POSTAL.txt)"
                
            if os.path.exists(alerta_file):
                observacao = f"[ATENÇÃO] Alerta de Caixa Postal capturado! | {observacao}"
                
            rows_data.append({
                "cnpj": format_cnpj(cnpj_raw),
                "nome": nome_raw,
                "status": status,
                "detalhes": detalhes,
                "data_hora": data_hora,
                "alerta_caixa_postal": alerta_texto,
                "observacao": observacao
            })
            
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Painel de Controle e-CAC"
        ws.views.sheetView[0].showGridLines = True
        
        # Design system styles (Navy & Premium accents)
        navy_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        white_font_16 = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
        gray_font_11 = Font(name="Calibri", size=11, bold=True, color="595959")
        gray_font_10 = Font(name="Calibri", size=10, italic=True, color="595959")
        
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        
        white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        zebra_fill = PatternFill(start_color="FAFAFA", end_color="FAFAFA", fill_type="solid")
        
        green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        green_font = Font(name="Calibri", size=10, bold=True, color="006100")
        
        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        red_font = Font(name="Calibri", size=10, bold=True, color="9C0006")
        
        yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        yellow_font = Font(name="Calibri", size=10, bold=True, color="9C6500")
        
        gray_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        gray_font = Font(name="Calibri", size=10, color="595959")
        
        thin_border_side = Side(border_style="thin", color="D3D3D3")
        data_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
        
        # Helper function to apply styles to merged cell ranges
        def style_range(ws, cell_range, font=None, fill=None, alignment=None, border=None):
            for row in ws[cell_range]:
                for cell in row:
                    if font is not None: cell.font = font
                    if fill is not None: cell.fill = fill
                    if alignment is not None: cell.alignment = alignment
                    if border is not None: cell.border = border
 
        # Merge columns for titles and style them perfectly without cutouts (7 columns now!)
        ws.merge_cells("A1:G1")
        ws["A1"] = "J&J CONTABILIDADE — PAINEL DE CONTROLE DE PENDÊNCIAS FISCAIS (e-CAC)"
        style_range(ws, "A1:G1", font=white_font_16, fill=navy_fill, alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[1].height = 40
        
        ws.merge_cells("A2:G2")
        ws["A2"] = "Varredura de Débitos Federais e Situação Fiscal via Procuração Digital"
        style_range(ws, "A2:G2", font=gray_font_11, alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[2].height = 22
        
        ws.merge_cells("A3:G3")
        hoje_fmt = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M")
        ws["A3"] = f"Relatório emitido em {hoje_fmt} | Escavador de Pendências Automatizado v1.0"
        style_range(ws, "A3:G3", font=gray_font_10, alignment=Alignment(horizontal="center", vertical="center"))
        ws.row_dimensions[3].height = 20
        
        ws.row_dimensions[4].height = 15
        
        headers = [
            "CNPJ",
            "Razão Social",
            "Status da Consulta",
            "Resultado / Documento",
            "Data/Hora Varredura",
            "Alerta Caixa Postal (e-CAC)",
            "Observações / Detalhes do Processamento"
        ]
        
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=5, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center" if col_idx not in [2, 6, 7] else "left", vertical="center", wrap_text=True)
            cell.border = data_border
            
        ws.row_dimensions[5].height = 28
        
        current_row = 6
        for idx, r in enumerate(rows_data):
            ws.cell(row=current_row, column=1, value=r["cnpj"]).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=current_row, column=2, value=r["nome"]).alignment = Alignment(horizontal="left", vertical="center")
            
            status_cell = ws.cell(row=current_row, column=3, value=r["status"])
            status_cell.alignment = Alignment(horizontal="center", vertical="center")
            
            detalhe_cell = ws.cell(row=current_row, column=4, value=r["detalhes"])
            detalhe_cell.alignment = Alignment(horizontal="center", vertical="center")
            
            ws.cell(row=current_row, column=5, value=r["data_hora"]).alignment = Alignment(horizontal="center", vertical="center")
            
            # Coluna 6: Texto completo do Alerta da Caixa Postal
            alerta_cell = ws.cell(row=current_row, column=6, value=r["alerta_caixa_postal"])
            alerta_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            
            # Coluna 7: Observações e Detalhes
            ws.cell(row=current_row, column=7, value=r["observacao"]).alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
            
            row_fill = zebra_fill if idx % 2 == 1 else white_fill
            
            for col_idx in range(1, 8):
                cell = ws.cell(row=current_row, column=col_idx)
                cell.border = data_border
                cell.fill = row_fill
                if col_idx not in [3, 4]:
                    cell.font = Font(name="Calibri", size=10)
                    
            st = r["status"]
            dt = r["detalhes"]
            
            if st == "Sucesso":
                if "Certidão" in dt or "Sem Pendências" in dt:
                    status_cell.fill = green_fill
                    status_cell.font = green_font
                    detalhe_cell.fill = green_fill
                    detalhe_cell.font = green_font
                elif "Relatório" in dt:
                    status_cell.fill = red_fill
                    status_cell.font = red_font
                    detalhe_cell.fill = red_fill
                    detalhe_cell.font = red_font
            elif st == "Erro":
                status_cell.fill = yellow_fill
                status_cell.font = yellow_font
                detalhe_cell.fill = yellow_fill
                detalhe_cell.font = yellow_font
            else:
                status_cell.fill = gray_fill
                status_cell.font = gray_font
                detalhe_cell.fill = gray_fill
                detalhe_cell.font = gray_font
                
            ws.row_dimensions[current_row].height = 22
            current_row += 1
            
        ws.row_dimensions[current_row].height = 15
        current_row += 1
        
        totais_row = current_row
        ws.cell(row=totais_row, column=1, value="TOTAIS").alignment = Alignment(horizontal="right", vertical="center")
        ws.cell(row=totais_row, column=2, value=f"=COUNTA(B6:B{totais_row-2})").alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=totais_row, column=3, value=f'=COUNTIF(C6:C{totais_row-2}, "Sucesso")').alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=totais_row, column=4, value=f'=COUNTIF(D6:D{totais_row-2}, "*Certidão*") + COUNTIF(D6:D{totais_row-2}, "*Sem Pendências*")').alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=totais_row, column=5, value=f'=COUNTIF(D6:D{totais_row-2}, "*Relatório*")').alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=totais_row, column=6, value="").alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=totais_row, column=7, value=f'=COUNTIF(C6:C{totais_row-2}, "Erro")').alignment = Alignment(horizontal="left", vertical="center")
        
        # Professional borders for accounting totals (Double bottom line)
        double_bottom = Side(border_style="double", color="FFFFFF")
        thin_top = Side(border_style="thin", color="FFFFFF")
        thin_side = Side(border_style="thin", color="D3D3D3")
        totals_border = Border(left=thin_side, right=thin_side, top=thin_top, bottom=double_bottom)
        
        for col_idx in range(1, 8):
            cell = ws.cell(row=totais_row, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = totals_border
            if col_idx == 1:
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in [3, 4, 5]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            
        ws.row_dimensions[totais_row].height = 26
        
        col_widths = {
            "A": 22, 
            "B": 48, 
            "C": 20, 
            "D": 38, 
            "E": 22, 
            "F": 65, # Coluna larga para o texto da Caixa Postal
            "G": 55  # Observações
        }
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width
            
        wb.save(output_path)
        log(f"Painel Excel Consolidado gerado com sucesso: {output_path}", "SUCCESS")
    except Exception as e:
        log(f"Falha crítica ao gerar arquivo consolidado Excel: {e}", "ERROR")

def alterar_perfil(page, cnpj, procurador_cnpj):
    is_cpf = (len(cnpj) == 11)
    doc_tipo = "CPF" if is_cpf else "CNPJ"
    log(f"Alterando perfil de acesso para o {doc_tipo}: {cnpj}...", "ACTION")
    
    # 0. Limpar modais de aviso/mensagem (como aviso de caixa postal)
    fechar_modais_e_overlays(page)

    # 1. Clicar no botão "Alterar perfil de acesso"
    alterar_perfil_btn = None
    for selector in ["text=Alterar perfil de acesso", "#alterarPerfil", "a:has-text('Alterar')", ".btn-alterar-perfil"]:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=3000)
            alterar_perfil_btn = loc
            break
        except Exception:
            continue
            
    if not alterar_perfil_btn:
        raise Exception("Não foi possível localizar o botão 'Alterar perfil de acesso' no cabeçalho.")
        
    try:
        alterar_perfil_btn.click(timeout=5000)
    except Exception as click_err:
        log(f"Erro ao clicar no botão de perfil: {click_err}. Tentando limpar overlays de recuperação...", "WARNING")
        fechar_modais_e_overlays(page)
        # Tenta localizar e clicar novamente
        alterar_perfil_btn = page.locator("text=Alterar perfil de acesso").first
        alterar_perfil_btn.click(timeout=5000)
    
    # Aguarda o modal de alteração de perfil estar 100% visível na tela
    log("Aguardando exibição do modal de alteração de perfil...", "ACTION")
    modal_carregado = False
    for sel in ["text=Procurador de pessoa jurídica", "text=Procurador de Pessoa Jurídica", "text=Titular", "text=Procurador de pessoa física"]:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=4000)
            modal_carregado = True
            log(f"Modal carregado com sucesso (elemento '{sel}' visível)", "SUCCESS")
            break
        except Exception:
            continue
            
    if not modal_carregado:
        log("Aviso: Tempo limite excedido ao aguardar visibilidade do modal. Tentando prosseguir diretamente.", "WARNING")
        
    # Se o CNPJ/CPF de destino for o próprio procurador, mudamos para o perfil Titular usando o botão dedicado
    if procurador_cnpj and cnpj == procurador_cnpj:
        log("Mudando de volta para o perfil Titular...", "ACTION")
        try:
            btn_titular = None
            for selector in [
                "input[value='Titular']",
                "button:has-text('Titular')",
                "text=Titular",
                "text=titular",
                "//input[@value='Titular']",
                "//button[contains(text(), 'Titular')]"
            ]:
                try:
                    loc = page.locator(selector).first
                    if loc.is_visible():
                        btn_titular = loc
                        break
                except Exception:
                    continue
                    
            if not btn_titular:
                raise Exception("Botão 'Titular' não localizado na tela.")
                
            btn_titular.click(timeout=5000)
            log("Botão 'Titular' clicado com sucesso para retornar ao perfil original.", "SUCCESS")
            page.wait_for_timeout(2000)
            return
        except Exception as e:
            raise Exception(f"Não foi possível reverter para o perfil Titular: {e}")
            
    # 2. Localizar o campo de entrada (CPF ou CNPJ) de Procurador e seu respectivo botão Alterar
    input_doc = None
    btn_alterar = None
    
    # Determinar labels e índice de fallback com base no tipo de documento
    labels_busca = ["Procurador de pessoa física", "Procurador de Pessoa Física"] if is_cpf else ["Procurador de pessoa jurídica", "Procurador de Pessoa Jurídica"]
    idx_fallback = 0 if is_cpf else 1
    
    # Método 1: Busca baseada em relação ao texto da label (Ultra-resiliente e preciso)
    for text_val in labels_busca:
        try:
            # Encontra o primeiro input de texto após a label correspondente
            inp_xpath = f"xpath=(//*[contains(text(), '{text_val}')]/following::input)[1]"
            # Encontra o primeiro botão de Alterar após a label correspondente
            btn_xpath = f"xpath=(//*[contains(text(), '{text_val}')]/following::input[@value='Alterar' or @type='submit' or contains(@value, 'Alterar')])[1]"
            
            inp = page.locator(inp_xpath).first
            btn = page.locator(btn_xpath).first
            
            inp.wait_for(state="visible", timeout=3000)
            btn.wait_for(state="visible", timeout=3000)
            
            input_doc = inp
            btn_alterar = btn
            log(f"Campos do perfil {doc_tipo} localizados com sucesso via XPath baseado em label: '{text_val}'", "INFO")
            break
        except Exception:
            continue
            
    # Método 2: Fallback por índice global (O primeiro input para CPF e o segundo input para CNPJ)
    if not input_doc or not btn_alterar:
        log(f"Busca por label falhou ou campos não ficaram visíveis. Usando fallback de índice global para {doc_tipo}...", "WARNING")
        try:
            inputs = page.locator("input[type='text'], input:not([type])")
            buttons = page.locator("input[value='Alterar'], input[type='submit'], button:has-text('Alterar')")
            
            if inputs.count() > idx_fallback and buttons.count() > idx_fallback:
                input_doc = inputs.nth(idx_fallback)
                btn_alterar = buttons.nth(idx_fallback)
                log(f"Campos do perfil {doc_tipo} localizados via fallback de índice global (índice {idx_fallback}).", "SUCCESS")
        except Exception as e:
            log(f"Falha ao executar fallback de índice global: {e}", "ERROR")
            
    if not input_doc or not btn_alterar:
        raise Exception(f"Não foi possível localizar o campo de texto do {doc_tipo} ou o botão 'Alterar' correspondente no modal.")
        
    # 3. Preencher o CPF/CNPJ no campo correto
    try:
        input_doc.clear()
        input_doc.fill(cnpj)
        log(f"Campo de {doc_tipo} de Procurador preenchido com: {cnpj}", "ACTION")
    except Exception as e:
        raise Exception(f"Falha ao preencher o campo de {doc_tipo} do procurador: {e}")
        
    # 4. Clicar no respectivo botão Alterar da linha
    try:
        btn_alterar.click(timeout=5000)
        log(f"Botão 'Alterar' correspondente ao perfil {doc_tipo} clicado com sucesso.", "ACTION")
    except Exception as e:
        raise Exception(f"Falha ao clicar no botão 'Alterar' do perfil {doc_tipo}: {e}")
        
    # 5. Validar se o perfil foi realmente alterado de forma dinâmica
    log("Aguardando atualização do cabeçalho com o novo perfil...", "ACTION")
    
    cnpj_sem_formatacao = cnpj.replace(".", "").replace("/", "").replace("-", "")
    sucesso = False
    
    # Fazemos uma verificação em loop a cada segundo por até 10 segundos
    for i in range(10):
        # Verifica se o CNPJ agora aparece no corpo/cabeçalho da página (indicando sucesso)
        header_text = page.locator("body").inner_text()
        header_text_limpo = header_text.replace(".", "").replace("/", "").replace("-", "")
        
        if cnpj_sem_formatacao in header_text_limpo:
            sucesso = True
            break
            
        # Também verifica se há alguma mensagem de erro do e-CAC explícita na tela durante a espera
        for erro_selector in ["text='Procuração inexistente'", "text='inexistente'", "text='expirada'", "text='Erro'", ".mensagem-erro", "#erro"]:
            try:
                loc = page.locator(erro_selector)
                if loc.first.is_visible():
                    erro_msg = loc.first.inner_text().strip()
                    raise Exception(f"Erro do e-CAC: {erro_msg}")
            except Exception as e:
                if "Erro do e-CAC" in str(e):
                    raise e
                    
        page.wait_for_timeout(1000)
        
    if sucesso:
        log(f"Perfil alterado com sucesso para o cliente: {cnpj}", "SUCCESS")
        return True
    else:
        # Se falhou e esgotou os 10 segundos, extrai o texto visível para relatar a causa exata
        page_text = page.locator("body").inner_text()
        for palavra_chave in ["não cadastrada", "expirada", "inexistente", "erro", "restrição", "inválido", "restricao", "procuração"]:
            if palavra_chave in page_text.lower():
                raise Exception(f"A alteração de perfil falhou. Mensagem do e-CAC: '{page_text.strip()[:180]}...'")
                
        raise Exception("A alteração de perfil foi concluída, mas o CNPJ correspondente não foi identificado no cabeçalho.")

def baixar_certidao_regularidade_fiscal(page, context, client_dir, cnpj, config):
    log("Iniciando emissão da Certidão de Regularidade Fiscal no e-CAC...", "ACTION")
    
    # 1. Voltar para a aba principal do e-CAC e clicar em "Certidões e Situação Fiscal"
    aba_clicada = False
    for selector in [
        "text=Certidões e Situação Fiscal",
        "#btn198",
        "//span[contains(text(), 'Certidões e Situação Fiscal')]",
        "//a[contains(text(), 'Certidões e Situação Fiscal')]"
    ]:
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=3000):
                loc.click()
                aba_clicada = True
                break
        except Exception:
            continue
            
    page.wait_for_timeout(1500)
    
    # 2. Localizar e clicar no link de Emissão de Certidão
    link_clicado = False
    new_page = None
    
    for selector in [
        "text=Certidão de Débitos Relativos a Créditos Tributários Federais e à Dívida Ativa da União",
        "text=Emitir Certidão de Regularidade Fiscal",
        "text=Certidão de Regularidade Fiscal",
        "a[href*='certidao']",
        "a[href*='Certidao']",
        "//a[contains(text(), 'Créditos Tributários Federais')]"
    ]:
        try:
            loc = page.locator(selector).first
            if loc.is_visible(timeout=3000):
                # Esperar a abertura da nova aba ao clicar
                with context.expect_page() as new_page_info:
                    loc.click()
                new_page = new_page_info.value
                link_clicado = True
                log(f"Link de certidão localizado e clicado: '{selector}'", "INFO")
                break
        except Exception:
            continue
            
    if not link_clicado or not new_page:
        log("Aviso: Link direto no e-CAC para Emissão de Certidão não localizado. Tentando emitir pela página pública da Receita...", "WARNING")
        try:
            new_page = context.new_page()
            new_page.goto("https://solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/PJ/Emitir", timeout=30000)
        except Exception as fallback_err:
            log(f"Falha ao carregar página de fallback pública: {fallback_err}", "ERROR")
            raise Exception("Não foi possível acessar a área de emissão de Certidão.")
        
    new_page.wait_for_load_state("load")
    
    # 3. Na página de emissão da certidão, preencher o CNPJ e emitir
    log("Aguardando carregamento da página de emissão de certidão...", "ACTION")
    try:
        # Se for a página pública de emissão da PJ, ela terá um campo para CNPJ
        input_cnpj = new_page.locator("input#cnpj, input[name*='cnpj'], input[name*='CNPJ']").first
        if input_cnpj.is_visible(timeout=3000):
            input_cnpj.clear()
            input_cnpj.fill(cnpj)
            log("CNPJ preenchido no formulário de emissão de certidão.", "ACTION")
            
            # Clicar no botão de Emitir do formulário
            btn_emitir = new_page.locator("input[value='Emitir'], button:has-text('Emitir'), input[type='submit']").first
            btn_emitir.click()
            new_page.wait_for_load_state("load")
            
        # Localizar botão de download / imprimir
        log("Localizando botão de download da certidão PDF...", "ACTION")
        botao_download = None
        for selector in [
            "text='Imprimir'",
            "text='Download'",
            "text='PDF'",
            "button:has-text('Imprimir')",
            "button:has-text('Gerar')",
            "button:has-text('Emitir')",
            "a:has-text('Imprimir')",
            "//input[@value='Imprimir']",
            "//input[@value='Gerar']"
        ]:
            try:
                loc = new_page.locator(selector).first
                if loc.is_visible(timeout=3000):
                    botao_download = loc
                    break
            except Exception:
                continue
                
        if not botao_download:
            raise Exception("Botão de download da certidão não localizado na página de emissão.")
            
        with new_page.expect_download(timeout=config["download_timeout_ms"]) as download_info:
            botao_download.click()
        download = download_info.value
        
        hoje_limpo = datetime.date.today().strftime("%Y%m%d")
        pdf_filename = f"CertidaoRegularidadeFiscal-{cnpj}-{hoje_limpo}.pdf"
        pdf_path = os.path.join(client_dir, pdf_filename)
        
        download.save_as(pdf_path)
        log(f"Certidão de regularidade fiscal baixada com sucesso: {pdf_path}", "SUCCESS")
        new_page.close()
        return f"Certidão Baixada: {pdf_filename}"
        
    except Exception as e:
        try:
            new_page.close()
        except Exception:
            pass
        log(f"Falha ao baixar a Certidão: {e}. Salvando informativo TXT como fallback.", "WARNING")
        # Fallback caso dê timeout ou erro de rede
        cnd_path = os.path.join(client_dir, f"Sem_Pendencias_Fiscais_Regular-{cnpj}.txt")
        with open(cnd_path, "w", encoding="utf-8") as f:
            f.write(f"Consulta realizada em {datetime.date.today().strftime('%d/%m/%Y')} às {datetime.datetime.now().strftime('%H:%M:%S')}\n")
            f.write("Status: Regular - Nenhuma pendência fiscal encontrada na Receita Federal (Emissão manual recomendada).")
        return "Sem Pendências (Informativo Gravado)"

def baixar_relatorio_situacao_fiscal(page, context, client_dir, cnpj, config, ja_possui_relatorio=False):
    log("Navegando para o serviço de Consulta de Situação Fiscal...", "ACTION")
    
    # 1. Clicar na aba "Certidões e Situação Fiscal" no painel principal do e-CAC
    aba_clicada = False
    for selector in [
        "text=Certidões e Situação Fiscal",
        "#btn198", # ID comum do botão de certidões no e-CAC
        "//span[contains(text(), 'Certidões e Situação Fiscal')]",
        "//a[contains(text(), 'Certidões e Situação Fiscal')]"
    ]:
        try:
            # Click direto utilizando o auto-waiting nativo do Playwright de até 4s
            page.click(selector, timeout=4000)
            aba_clicada = True
            break
        except Exception:
            continue
            
    if not aba_clicada:
        raise Exception("Não foi possível acessar o menu 'Certidões e Situação Fiscal'.")
        
    page.wait_for_timeout(1000)
    
    # 2. Localizar e clicar em "Consulta Pendências - Situação Fiscal" (abre em nova aba)
    link_clicado = False
    new_page = None
    
    for selector in [
        "a:has-text('Consulta Pendências - Situação Fiscal')",
        "text=Consulta Pendências - Situação Fiscal",
        "a[href*='servico/pendencias']",
        "//a[contains(text(), 'Consulta Pendências')]"
    ]:
        try:
            # Esperar a abertura da nova aba ao clicar (definimos timeout de 10s)
            with context.expect_page(timeout=10000) as new_page_info:
                # Usamos dispatch_event('click') para simular o clique a nível de evento DOM
                # Isso evita que o cursor físico dispare o hover do tooltip que cobre o link
                page.locator(selector).first.dispatch_event("click")
            new_page = new_page_info.value
            link_clicado = True
            break
        except Exception as click_err:
            log(f"Falha ao clicar com dispatch_event no seletor '{selector}': {click_err}. Tentando clique físico...", "WARNING")
            try:
                with context.expect_page(timeout=10000) as new_page_info:
                    page.locator(selector).first.click(timeout=4000)
                new_page = new_page_info.value
                link_clicado = True
                break
            except Exception:
                continue
            
    if not link_clicado or not new_page:
        raise Exception("Não foi possível clicar em 'Consulta Pendências - Situação Fiscal' ou a nova aba não abriu.")
        
    log("Nova aba de Consulta de Situação Fiscal detectada.", "ACTION")
    new_page.wait_for_load_state("load")
    
    # 2.5 Verificar se a nova página redirecionou para uma tela de login/autenticação intermediária (Gov.br)
    # Isso costuma ocorrer quando mudamos de domínio de cav.receita.fazenda.gov.br para servicos.receitafederal.gov.br
    try:
        btn_gov = None
        for sel in ["text=Entrar com GovBR", "text=Entrar com o GovBR", "text=Entrar com o gov.br", "button:has-text('Entrar com')", "a:has-text('Entrar com')"]:
            try:
                loc = new_page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    btn_gov = loc
                    break
            except Exception:
                continue
        if btn_gov:
            log("Tela de autenticação intermediária do Gov.br detectada no novo domínio. Clicando em 'Entrar com GovBR'...", "WARNING")
            btn_gov.click()
            # Aguarda a nova página carregar após o redirecionamento de login
            new_page.wait_for_load_state("load")
            new_page.wait_for_timeout(3000)
    except Exception as e:
        log(f"Sem tela de login intermediária do Gov.br ou falha ao clicar: {e}. Prosseguindo...", "INFO")
        
    # 2.7 Trocar Representação diretamente no Novo Portal (se necessário)
    try:
        avatar_trigger = new_page.locator("#avatar-dropdown-trigger, .br-sign-in").first
        if avatar_trigger.is_visible(timeout=4000):
            header_text = avatar_trigger.inner_text()
            cnpj_limpo = "".join(filter(str.isdigit, cnpj))
            header_cnpj_limpo = "".join(filter(str.isdigit, header_text))
            
            # Se o CNPJ ativo no cabeçalho do novo portal for diferente do CNPJ procurado, fazemos a troca
            if cnpj_limpo not in header_cnpj_limpo:
                log(f"[NOVO-PORTAL] CNPJ ativo no novo portal é diferente do alvo ({cnpj}). Iniciando troca...", "INFO")
                
                # Clicar com time de 2 segundos no trigger do avatar
                avatar_trigger.click()
                new_page.wait_for_timeout(2000)
                
                # Escrever o CNPJ ou CPF do cliente no input
                log(f"[NOVO-PORTAL] Preenchendo CNPJ de representação: {cnpj}...", "ACTION")
                cnpj_input = new_page.locator("#input-representar-cpfcnpj, input[name='representar-cpfcnpj']").first
                cnpj_input.clear()
                cnpj_input.fill(cnpj)
                
                # Aguardar 1 segundo
                new_page.wait_for_timeout(1000)
                
                # Clicar no dropdown de perfil de representação
                log("[NOVO-PORTAL] Clicando no dropdown de perfil de representação...", "ACTION")
                select_profile = new_page.locator("ng-select, .ng-select-container, .ng-placeholder").first
                select_profile.click()
                new_page.wait_for_timeout(500)
                
                # Selecionar "PROCURADOR"
                opcao_procurador = new_page.locator(".ng-option:has-text('PROCURADOR'), .ng-option:has-text('Procurador'), text='PROCURADOR'").first
                opcao_procurador.click()
                new_page.wait_for_timeout(500)
                
                # Clicar no botão Representar
                log("[NOVO-PORTAL] Clicando no botão Representar...", "ACTION")
                btn_representar = new_page.locator("button:has-text('Representar'), .btn:has-text('Representar'), [role='button']:has-text('Representar')").first
                btn_representar.click()
                
                # Aguardar 2 segundos
                new_page.wait_for_timeout(2000)
                
                # Clicar no centro da página (body) para conferir/remover dropdown e prosseguir
                new_page.click("body")
                new_page.wait_for_timeout(1000)
                log(f"[NOVO-PORTAL] Representação alterada com sucesso para o CNPJ: {cnpj}", "SUCCESS")
            else:
                log(f"[NOVO-PORTAL] Representação ativa no novo portal já corresponde ao CNPJ {cnpj}.", "SUCCESS")
    except Exception as rep_err:
        log(f"[NOVO-PORTAL] Aviso ao gerenciar representação diretamente no novo portal: {rep_err}. Prosseguindo com o fluxo existente...", "WARNING")

    # 3. Aguardar o carregamento dos dados da situação fiscal
    # Esta página costuma fazer consultas lentas em APIs internas. Vamos aguardar pacientemente.
    log("Aguardando carregamento da situação fiscal do cliente na Receita Federal (isso pode levar alguns segundos)...", "ACTION")
    
    # Espera até 10 segundos no total com polling ativo para avançar IMEDIATAMENTE quando a página carregar
    selectors = [
        "text=Gerar Relatório",
        "text=Baixar Relatório",
        "text=Baixar Certidão",
        "text=não foram encontradas",
        "text=regularidade",
        "text=Sem pendência",
        "button:has-text('Relatório')"
    ]
    
    carregado = False
    for _ in range(10): # 10 segundos no máximo
        for sel in selectors:
            try:
                if new_page.locator(sel).first.is_visible():
                    carregado = True
                    break
            except Exception:
                continue
        if carregado:
            break
        new_page.wait_for_timeout(1000)

    if carregado:
        log("Carregamento da situação fiscal concluído!", "SUCCESS")
    else:
        log("Aviso: Tempo limite de carregamento de 10 segundos atingido. Verificando elementos presentes na página...", "WARNING")
        
    # 4. Analisar se o cliente tem pendências ou se está regular
    page_text = new_page.locator("body").inner_text()
    hoje_limpo = datetime.date.today().strftime("%Y%m%d")
    
    # Verificação se o status é "Sem pendência"
    if "não foram encontradas" in page_text.lower() or "sem pendência" in page_text.lower() or "regularidade" in page_text.lower():
        log("Mensagem de ausência de pendências detectada ('Sem pendência' / 'Regularidade')!", "SUCCESS")
        log("Buscando botão de download da CERTIDÃO (CND)...", "ACTION")
        
        botao_cnd = None
        for selector in [
            "app-botao-emitir-certidao button",
            "button.secondary.btn-acao:has-text('Baixar Certidão')",
            "button.btn-acao:has-text('Baixar Certidão')",
            "text=Baixar Certidão",
            "button:has-text('Baixar Certidão')",
            "a:has-text('Baixar Certidão')",
            "//button[contains(., 'Certidão')]",
            "//a[contains(., 'Certidão')]"
        ]:
            try:
                loc = new_page.locator(selector).first
                if loc.is_visible(timeout=3000):
                    botao_cnd = loc
                    break
            except Exception:
                continue
                
        if botao_cnd:
            log("Botão 'Baixar Certidão' localizado. Iniciando download do PDF da CND...", "ACTION")
            try:
                with new_page.expect_download(timeout=config["download_timeout_ms"]) as download_info:
                    botao_cnd.click()
                download = download_info.value
                
                pdf_filename = f"CertidaoRegularidadeFiscal-{cnpj}-{hoje_limpo}.pdf"
                pdf_path = os.path.join(client_dir, pdf_filename)
                download.save_as(pdf_path)
                log(f"Certidão de regularidade fiscal baixada com sucesso: {pdf_path}", "SUCCESS")
                new_page.close()
                return "Certidão Baixada"
            except Exception as e:
                log(f"Falha ao clicar no botão 'Baixar Certidão': {e}. Tentando fallback...", "WARNING")
                
        # Se não localizou o botão ou falhou o download na página de pendências, tenta emitir pela aba tradicional do e-CAC
        log("Tentando emitir CND via menu tradicional do e-CAC como fallback...", "INFO")
        new_page.close()
        resultado_fallback = baixar_certidao_regularidade_fiscal(page, context, client_dir, cnpj, config)
        return resultado_fallback
        
    else:
        # COM PENDÊNCIAS - Baixar o Relatório PDF ou ignorar se já existe no mês
        if ja_possui_relatorio:
            log("A situação fiscal continua com pendências e o relatório do mês corrente já existe na pasta. Ignorando novo download redundante.", "INFO")
            new_page.close()
            return "Relatório Existente (Pendências mantidas)"
            
        log("Pendências fiscais ativas detectadas. Buscando botão de download do RELATÓRIO...", "ACTION")
        
        botao_relatorio = None
        for selector in [
            "text=Baixar Relatório",
            "text='Gerar Relatório'",
            "text='Baixar Relatório'",
            "button:has-text('Baixar Relatório')",
            "button:has-text('Gerar Relatório')",
            "button:has-text('Relatório')",
            "button:has-text('PDF')",
            "a:has-text('Gerar Relatório')",
            "//button[contains(., 'Relatório')]",
            "//button[contains(., 'Gerar')]"
        ]:
            try:
                loc = new_page.locator(selector).first
                if loc.is_visible(timeout=3000):
                    botao_relatorio = loc
                    break
            except Exception:
                continue
                
        if not botao_relatorio:
            raise Exception("Botão 'Baixar Relatório' / 'Gerar Relatório' não localizado na página de pendências.")
            
        log("Botão de relatório localizado. Iniciando download do PDF do Relatório...", "ACTION")
        try:
            with new_page.expect_download(timeout=config["download_timeout_ms"]) as download_info:
                botao_relatorio.click()
            download = download_info.value
            
            pdf_filename = f"RelatorioSituacaoFiscal-{cnpj}-{hoje_limpo}.pdf"
            pdf_path = os.path.join(client_dir, pdf_filename)
            
            download.save_as(pdf_path)
            log(f"Relatório fiscal baixado e salvo com sucesso: {pdf_path}", "SUCCESS")
            new_page.close()
            return "Relatório Baixado"
        except Exception as e:
            new_page.close()
            raise Exception(f"Falha ao realizar download do PDF do Relatório: {e}")

def realizar_login_manual(config):
    log("=" * 60, "LOGIN")
    log(" INICIANDO MODO DE AUTENTICAÇÃO E-CAC (100% AUTOMATIZADO)", "LOGIN")
    log("=" * 60, "LOGIN")
    log("Um navegador Google Chrome visível será aberto e tentará o login automaticamente...", "INFO")
    
    state_file = "state.json"
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            log(f"Não foi possível iniciar o Chrome nativo ({e}). Usando Chromium padrão do Playwright...", "WARNING")
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            permissions=["geolocation"],
            geolocation={"latitude": -15.793889, "longitude": -47.882778}
        )
        page = context.new_page()
        
        # Acessa e-CAC
        page.goto("https://cav.receita.fazenda.gov.br/ecac/")
        
        # 1. Aguarda 2 segundos após carregar a página e clica automaticamente no botão de login do Gov.br
        try:
            log("Página carregada. Aguardando exatamente 2 segundos para iniciar...", "INFO")
            page.wait_for_timeout(2000)
            
            log("Buscando o botão de login 'Acesso Gov BR'...", "INFO")
            page.wait_for_selector('input[alt="Acesso Gov BR"]', timeout=10000)
            log("Clicando no botão de login do Gov.br...", "ACTION")
            page.click('input[alt="Acesso Gov BR"]')
            
            # 2. Aguarda redirecionamento para o Gov.br SSO e o botão "Seu certificado digital"
            log("Aguardando redirecionamento para o portal Gov.br...", "INFO")
            page.wait_for_selector('button#login-certificate, #login-certificate', timeout=15000)
            log("Botão 'Seu certificado digital' (#login-certificate) detectado!", "SUCCESS")
            
            # 3. Disparar thread em background para simular o ENTER no diálogo do Windows
            import threading
            def auto_confirm_dialog():
                time.sleep(3.5)
                log("[AUTO-LOGIN] Janela de seleção do Windows deve estar aberta. Simulando ENTER...", "SYSTEM")
                press_enter()
                # Envia um segundo ENTER por segurança após 1.2 segundos caso o foco tenha demorado
                time.sleep(1.2)
                press_enter()
                
            threading.Thread(target=auto_confirm_dialog, daemon=True).start()
            
            log("Clicando no botão 'Seu certificado digital' e aguardando confirmação do Windows...", "ACTION")
            page.click('button#login-certificate')
            
        except Exception as auto_err:
            log(f"Aviso no fluxo automático: {auto_err}", "WARNING")
            log("Fluxo automático falhou ou parou. Por favor, conclua o login manualmente na tela se necessário.", "IMPORTANT")
            
        try:
            # Aguarda o elemento do cabeçalho do e-CAC aparecer (máximo 5 minutos)
            # Isso serve tanto para o fluxo 100% automático quanto para o manual em caso de fallback!
            page.wait_for_selector("text=Alterar perfil de acesso", timeout=300000)
            log("Conexão e login detectados com sucesso no e-CAC!", "SUCCESS")
            
            # Salvar o estado da sessão em state.json
            context.storage_state(path=state_file)
            log(f"Sessão gravada com sucesso em '{state_file}'!", "SUCCESS")
            browser.close()
            return True
        except Exception as e:
            log(f"Tempo limite de 5 minutos excedido ou erro no login: {e}", "ERROR")
            browser.close()
            return False

def enviar_whatsapp(mensagem, config):
    if not config.get("whatsapp_enabled"):
        log("Notificação via WhatsApp desabilitada nas configurações.", "INFO")
        return False
        
    instance = config.get("whatsapp_zapi_instance")
    token = config.get("whatsapp_zapi_token")
    number = config.get("whatsapp_number")
    client_token = config.get("whatsapp_zapi_client_token")
    
    if not instance or not token or not number:
        log("Erro: Configurações de WhatsApp (Instância, Token ou Número) incompletas.", "ERROR")
        return False
        
    # Higienizar número: apenas dígitos
    number_clean = "".join(filter(str.isdigit, number))
    # Garantir código do país
    if not number_clean.startswith("55") and len(number_clean) in [10, 11]:
        number_clean = "55" + number_clean
        
    url = f"https://api.z-api.io/instances/{instance}/token/{token}/send-text"
    headers = {
        "Content-Type": "application/json"
    }
    if client_token:
        headers["Client-Token"] = client_token
        
    payload = {
        "phone": number_clean,
        "message": mensagem
    }
    
    log(f"Enviando notificação WhatsApp via Z-API para {number_clean}...", "INFO")
    try:
        import requests
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code in [200, 201]:
            log("Notificação WhatsApp enviada com sucesso!", "SUCCESS")
            return True
        else:
            log(f"Falha ao enviar WhatsApp. Status: {response.status_code}, Resposta: {response.text}", "ERROR")
            return False
    except Exception as e:
        log(f"Erro ao enviar requisição para Z-API: {e}", "ERROR")
        return False

def main():
    config = load_config()
    clientes = load_clients(config["clientes_file"])
    
    if not clientes:
        log("Nenhum cliente ativo para processamento. Finalizando robô.", "WARNING")
        return
        
    state_file = "state.json"
    
    while True:
        # Se o usuário passou --login na linha de comando, ou se o arquivo state.json não existe, força o login manual
        forçar_login = "--login" in sys.argv
        if forçar_login or not os.path.exists(state_file):
            if not os.path.exists(state_file):
                log("Sessão ativa não encontrada ('state.json'). Precisamos logar uma vez para salvar o acesso.", "INFO")
            else:
                log("Forçando renovação da sessão ativa conforme solicitado...", "INFO")
                
            sucesso = realizar_login_manual(config)
            if not sucesso:
                log("Falha ao salvar a sessão autenticada. A execução da varredura foi cancelada.", "ERROR")
                return
                
        # Identificar procurador pelo arquivo .pfx (usamos para evitar re-troca de perfil se for o próprio)
        import glob
        import re
        pfx_files = glob.glob("*.pfx")
        procurador_cnpj = ""
        if pfx_files:
            filename = os.path.basename(pfx_files[0])
            # Extrair CNPJ usando regex para buscar qualquer sequência de 14 dígitos consecutivos
            match = re.search(r"\d{14}", filename)
            if match:
                procurador_cnpj = match.group(0)
        log(f"CNPJ do Procurador detectado: {procurador_cnpj or 'Não identificado'}", "INFO")
        
        log(f"Iniciando rotina de processamento para {len([c for c in clientes if c['ativo']])} clientes ativos...", "INFO")
        
        success_count = 0
        failure_count = 0
        skipped_count = 0
        
        need_restart = False
        
        with sync_playwright() as p:
            log("Iniciando navegador Google Chrome para executar a varredura automática...", "SYSTEM")
            
            try:
                browser = p.chromium.launch(
                    headless=config["headless"],
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"]
                )
            except Exception as e:
                log(f"Não foi possível iniciar o Chrome nativo ({e}). Usando Chromium padrão...", "WARNING")
                browser = p.chromium.launch(
                    headless=config["headless"],
                    args=["--disable-blink-features=AutomationControlled"]
                )
                
            # Carregamos a sessão salva anteriormente!
            log(f"Carregando sessão autenticada a partir de '{state_file}'...", "INFO")
            try:
                context = browser.new_context(
                    storage_state=state_file,
                    viewport={"width": 1280, "height": 800},
                    permissions=["geolocation"],
                    geolocation={"latitude": -15.793889, "longitude": -47.882778}
                )
            except Exception as e:
                log(f"Erro ao carregar o arquivo de sessão '{state_file}': {e}. Removendo o arquivo para recriá-lo.", "WARNING")
                if os.path.exists(state_file):
                    os.remove(state_file)
                browser.close()
                need_restart = True
                
            if not need_restart:
                page = context.new_page()
                
                # Acessar diretamente a página inicial do e-CAC (já autenticado!)
                log("Acessando portal e-CAC (reutilizando sessão ativa)...", "ACTION")
                try:
                    page.goto("https://cav.receita.fazenda.gov.br/ecac/")
                    
                    # Validar se a sessão ainda está ativa
                    # Espera até 10 segundos para ver se o painel carrega diretamente.
                    # Se a sessão expirou, o e-CAC redirecionará para a tela de login.
                    page.wait_for_selector("text=Alterar perfil de acesso", timeout=10000)
                    log("Sessão autenticada validada e ativa com sucesso!", "SUCCESS")
                except Exception:
                    log("A sessão salva expirou ou foi invalidada pela Receita Federal. Precisamos renovar o login.", "WARNING")
                    if os.path.exists(state_file):
                        os.remove(state_file)
                    browser.close()
                    need_restart = True
                    
            if not need_restart:
                # 2. Iterar sobre a lista de clientes
                for cliente in clientes:
                    cnpj = cliente["cnpj"]
                    nome = cliente["nome"]
                    ativo = cliente["ativo"]
                    
                    if not ativo:
                        log(f"Cliente {nome} ({cnpj}) está inativo no CSV. Ignorando.", "INFO")
                        skipped_count += 1
                        continue
                        
                    # Verificar se o cliente já foi processado com sucesso hoje ou se já possui regularidade no mês
                    today_str = datetime.date.today().strftime("%Y-%m-%d")
                    month_str = datetime.date.today().strftime("%Y-%m")
                    nome_limpo = clean_filename(nome)
                    
                    client_dir = os.path.join(config["relatorios_dir"], nome_limpo, month_str)
                    status_path = os.path.join(client_dir, "status.json")
                    
                    forcar_todos = "--forcar-todos" in sys.argv
                    
                    # 1. Verificar se já existem arquivos de regularidade (Certidão ou Informativo Regular) na pasta mensal
                    cnd_pdfs = glob.glob(os.path.join(client_dir, "CertidaoRegularidadeFiscal-*.pdf"))
                    cnd_txts = glob.glob(os.path.join(client_dir, "Sem_Pendencias_Fiscais_Regular-*.txt"))
                    
                    if not forcar_todos and (cnd_pdfs or cnd_txts):
                        log(f"Cliente {nome} ({cnpj}) já possui Certidão/Regularidade ativa na pasta do mês ({month_str}). Pulando consulta no e-CAC.", "SUCCESS")
                        detalhes_status = "Certidão Baixada" if cnd_pdfs else "Sem Pendências (Informativo Gravado)"
                        save_client_status(config["relatorios_dir"], cnpj, nome, "Sucesso", detalhes_status)
                        success_count += 1
                        continue
                        
                    # 2. Verificar se o cliente já foi consultado com SUCESSO hoje de fato
                    ja_processado_hoje = False
                    if not forcar_todos and os.path.exists(status_path):
                        try:
                            with open(status_path, "r", encoding="utf-8") as f:
                                status_data = json.load(f)
                                if status_data.get("status") == "Sucesso" and status_data.get("data_consulta") == today_str:
                                    ja_processado_hoje = True
                        except Exception:
                            pass
                            
                    if ja_processado_hoje:
                        log(f"Cliente {nome} ({cnpj}) já foi consultado com SUCESSO hoje. Pulando...", "SUCCESS")
                        success_count += 1
                        continue
                        
                    # 3. Verificar se já existe relatório de pendência na pasta do mês
                    relatorio_pdfs = glob.glob(os.path.join(client_dir, "RelatorioSituacaoFiscal-*.pdf"))
                    tem_relatorio_existente = len(relatorio_pdfs) > 0
                    
                    log(f"Processando Cliente: {nome} ({cnpj})...", "INFO")
                    if tem_relatorio_existente:
                        log(f"Identificado relatório de pendências pré-existente na pasta do mês ({month_str}). Caso continue irregular, o download será pulado.", "INFO")
                    
                    # Criar diretório para salvar o relatório do cliente (já inicializa como pendente)
                    client_dir = save_client_status(config["relatorios_dir"], cnpj, nome, "Pendente", "Iniciado")
                    
                    max_tentativas = 3
                    sucesso_cliente = False
                    erro_final = None
                    
                    for tentativa in range(1, max_tentativas + 1):
                        try:
                            if tentativa > 1:
                                log(f"[TENTATIVA {tentativa}/{max_tentativas}] Reiniciando fluxo para o cliente {nome}...", "WARNING")
                                # 0. Garantir que a sessão/login esteja ativa e renovada
                                verificar_e_reestabelecer_sessao(page, config)
                                
                            # 0.5. Limpar modais iniciais ou remanescentes e tratar Caixa Postal bloqueante
                            fechar_modais_e_overlays(page)
                            checar_e_tratar_caixa_postal(page, client_dir, config)
                            
                            # 1. Verificar qual é o perfil atualmente ativo na tela do e-CAC
                            header_text = page.locator("body").inner_text()
                            header_text_limpo = header_text.replace(".", "").replace("/", "").replace("-", "").replace(" ", "").replace("\n", "").replace("\r", "")
                            
                            cnpj_sem_formatacao = cnpj.replace(".", "").replace("/", "").replace("-", "")
                            
                            # Caso A: O cliente que queremos consultar é o próprio procurador (JEJ)
                            if procurador_cnpj and cnpj == procurador_cnpj:
                                if "Procuradorde" in header_text_limpo:
                                    log(f"Perfil atual não é Titular. Solicitando alteração de perfil para voltar ao Titular ({nome})...", "INFO")
                                    alterar_perfil(page, cnpj, procurador_cnpj)
                                    checar_e_tratar_caixa_postal(page, client_dir, config)
                                else:
                                    log(f"Já estamos no perfil Titular do procurador ({nome}). Consultando diretamente.", "INFO")
                                    
                            # Caso B: O cliente que queremos consultar é uma empresa representada (Tome & Lopes)
                            else:
                                if cnpj_sem_formatacao in header_text_limpo:
                                    log(f"O perfil ativo no e-CAC já corresponde a {nome} ({cnpj}). Pulando alteração de perfil.", "SUCCESS")
                                else:
                                    log(f"Perfil atual diferente de {nome}. Alterando perfil para o CNPJ: {cnpj}...", "INFO")
                                    alterar_perfil(page, cnpj, procurador_cnpj)
                                    checar_e_tratar_caixa_postal(page, client_dir, config)
                                
                            # Acessar Situação Fiscal e baixar relatório
                            resultado = baixar_relatorio_situacao_fiscal(page, context, client_dir, cnpj, config, ja_possui_relatorio=tem_relatorio_existente)
                            
                            # Salvar metadados de sucesso
                            save_client_status(config["relatorios_dir"], cnpj, nome, "Sucesso", resultado)
                            success_count += 1
                            sucesso_cliente = True
                            break
                            
                        except Exception as e:
                            log(f"[ERRO - TENTATIVA {tentativa}/{max_tentativas}] Erro ao processar cliente {nome} ({cnpj}): {e}", "WARNING")
                            erro_final = e
                            
                            # Capturar screenshot do erro para diagnóstico visual na pasta do cliente
                            try:
                                screenshot_path = os.path.join(client_dir, f"erro_tentativa_{tentativa}.png")
                                page.screenshot(path=screenshot_path)
                                log(f"Screenshot do erro capturado e salvo em: {screenshot_path}", "INFO")
                            except Exception as snap_err:
                                log(f"Não foi possível capturar screenshot do erro: {snap_err}", "WARNING")
                                
                            # Fechar abas extras se acumularam
                            try:
                                if len(context.pages) > 1:
                                    for p_extra in context.pages[1:]:
                                        p_extra.close()
                            except Exception:
                                pass
                                
                        finally:
                            # Voltar a página do e-CAC para o painel principal após cada tentativa
                            try:
                                log("Retornando para a página inicial do e-CAC...", "ACTION")
                                page.goto(config["portal_url"])
                                fechar_modais_e_overlays(page)
                                page.wait_for_selector("text=Alterar perfil de acesso", timeout=10000)
                            except Exception as nav_err:
                                log(f"Erro ao retornar para a página inicial: {nav_err}. Forçando reload de emergência...", "WARNING")
                                try:
                                    page.reload()
                                    page.wait_for_selector("text=Alterar perfil de acesso", timeout=15000)
                                except Exception as reload_err:
                                    log(f"Falha crítica de recuperação ao tentar recarregar a página: {reload_err}", "ERROR")
                                    
                    if not sucesso_cliente:
                        log(f"[FALHA FINAL] Não foi possível processar o cliente {nome} ({cnpj}) após {max_tentativas} tentativas.", "ERROR")
                        # Salvar log de erro definitivo
                        try:
                            save_client_status(config["relatorios_dir"], cnpj, nome, "Erro", str(erro_final))
                        except Exception as save_err:
                            log(f"Não foi possível salvar status de erro para o cliente: {save_err}", "WARNING")
                        failure_count += 1
                            
                browser.close()
                
        if need_restart:
            # Evita loops infinitos de login manual se o argumento --login estiver na linha de comando
            if "--login" in sys.argv:
                sys.argv.remove("--login")
            log("Sessão limpa e resetada. Reiniciando fluxo de login manual...", "INFO")
            continue
        else:
            break
            
    # Gerar Painel Excel Consolidado J&J Contabilidade
    hoje_limpo = datetime.date.today().strftime("%Y%m%d")
    output_excel = os.path.join(
        config.get("relatorios_dir", "relatorios"), 
        f"Painel_Consolidado_Pendencias_eCAC_{hoje_limpo}.xlsx"
    )
    gerar_consolidado_excel(clientes, config.get("relatorios_dir", "relatorios"), output_excel)
    
    # Adicionalmente salvamos uma cópia direto no Desktop do usuário para fácil acesso!
    try:
        desktop_dir = r"C:\Users\jejco\Desktop"
        # 1. Arquivo de uso diário fixo (reutilizável)
        desktop_excel_fixed = os.path.join(desktop_dir, "Painel_Consolidado_Pendencias_eCAC.xlsx")
        gerar_consolidado_excel(clientes, config.get("relatorios_dir", "relatorios"), desktop_excel_fixed)
        log(f"Painel Excel Consolidado principal atualizado no Desktop: {desktop_excel_fixed}", "SUCCESS")
        
        # 2. Cópia histórica com data
        desktop_excel_dated = os.path.join(desktop_dir, f"Painel_Consolidado_Pendencias_eCAC_{hoje_limpo}.xlsx")
        gerar_consolidado_excel(clientes, config.get("relatorios_dir", "relatorios"), desktop_excel_dated)
    except Exception as d_err:
        log(f"Aviso: Não foi possível salvar cópia no Desktop: {d_err}", "WARNING")
        
    # Relatório final
    log("=" * 60, "SUMMARY")
    log(" ROTINA DE EXECUÇÃO CONCLUÍDA", "SUMMARY")
    log(f" - Clientes com Sucesso: {success_count}", "SUMMARY")
    log(f" - Clientes com Falha: {failure_count}", "SUMMARY")
    log(f" - Clientes Ignorados: {skipped_count}", "SUMMARY")
    log("=" * 60, "SUMMARY")

    # Enviar notificação via WhatsApp (Z-API) se estiver ativo
    if config.get("whatsapp_enabled"):
        try:
            hoje_fmt = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M")
            mensagem = (
                f"📢 *Escavador de Pendências e-CAC*\n"
                f"📅 Varredura concluída em {hoje_fmt}\n\n"
                f"✅ *Sucesso:* {success_count} empresas\n"
                f"❌ *Falha:* {failure_count} empresas\n"
                f"➖ *Ignorado:* {skipped_count} empresas\n\n"
            )
            
            # Detalhar pendências encontradas (relatórios baixados de hoje)
            detalhes_pendencias = []
            detalhes_erros = []
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            month_str = datetime.date.today().strftime("%Y-%m")
            
            for cliente in clientes:
                cnpj = cliente["cnpj"]
                nome = cliente["nome"]
                ativo = cliente["ativo"]
                if not ativo:
                    continue
                
                nome_limpo = clean_filename(nome)
                status_path = os.path.join(config["relatorios_dir"], nome_limpo, month_str, "status.json")
                if os.path.exists(status_path):
                    with open(status_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("data_consulta") == today_str:
                            status = data.get("status")
                            detalhes = data.get("detalhes")
                            if status == "Sucesso" and "Relatório" in detalhes:
                                detalhes_pendencias.append(nome)
                            elif status == "Erro":
                                detalhes_erros.append(f"{nome} ({detalhes})")
            
            if detalhes_pendencias:
                mensagem += "⚠️ *Empresas com Pendências (Relatório PDF Baixado):*\n"
                for p in detalhes_pendencias:
                    mensagem += f" - {p}\n"
                mensagem += "\n"
                
            if detalhes_erros:
                mensagem += "🚨 *Empresas com Falha no Acesso:*\n"
                for e in detalhes_erros:
                    mensagem += f" - {e}\n"
                mensagem += "\n"
                
            mensagem += "📂 *O Painel de Controle Consolidado atualizado está disponível no seu Desktop!*"
            enviar_whatsapp(mensagem, config)
        except Exception as wa_err:
            log(f"Erro ao compilar e enviar notificação do WhatsApp: {wa_err}", "ERROR")

if __name__ == "__main__":
    main()
