import csv
import os
import json
import re
import datetime

# Importações das funções do sistema
from executar import gerar_consolidado_excel, load_clients
from consultar_nota_fiscal_xml import gerar_excel_resumo, clean_filename

def rebuild_ecac_consolidated_sheet(config):
    try:
        print("[REBUILD] Iniciando reconstrução da planilha e-CAC...")
        clientes_file = config.get("clientes_file", "clientes.csv")
        clientes = load_clients(clientes_file)
        
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        desktop_excel_fixed = os.path.join(desktop_dir, "Painel_Consolidado_Pendencias_eCAC.xlsx")
        
        gerar_consolidado_excel(clientes, config.get("relatorios_dir", "relatorios"), desktop_excel_fixed)
        print(f"[REBUILD] Planilha e-CAC consolidada reconstruída no Desktop: {desktop_excel_fixed}")
        return True
    except Exception as e:
        print(f"[REBUILD] Erro ao reconstruir planilha e-CAC: {e}")
        return False

def rebuild_xml_consolidated_sheet(config):
    try:
        print("[REBUILD] Iniciando reconstrução da planilha NF-e XML...")
        clientes_file = config.get("clientes_file", "clientes.csv")
        if not os.path.exists(clientes_file):
            print(f"[REBUILD] Erro: clientes.csv não encontrado no caminho {clientes_file}")
            return False
            
        clientes_ativos = []
        with open(clientes_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normaliza colunas
                ativo_val = row.get("ativo", "True").strip().lower() in ["true", "1", "yes", "ativo", "sim", "s"]
                if ativo_val:
                    clientes_ativos.append(row)
                    
        resultados = []
        today = datetime.date.today().strftime("%Y-%m-%d")
        
        for c in clientes_ativos:
            cnpj = c.get("cnpj", "")
            nome = c.get("nome", "")
            cnpj_limpo = "".join(filter(str.isdigit, cnpj))
            nome_limpo = clean_filename(nome)
            
            client_dir = os.path.join("documentos de nota fiscal xml", f"{cnpj_limpo}_{nome_limpo}")
            status_path = os.path.join(client_dir, "status_nota_fiscal_xml.json")
            
            status = "Pendente"
            detalhes = "Não Consultado"
            hora_atual = "-"
            dt_completa = f"{today} 00:00:00"
            
            if os.path.exists(status_path):
                try:
                    with open(status_path, "r", encoding="utf-8") as f_st:
                        st_data = json.load(f_st)
                        status = st_data.get("status", "Pendente")
                        detalhes = st_data.get("detalhes", "Não Consultado")
                        hora = st_data.get("hora_consulta", "00:00:00")
                        data_consulta = st_data.get("data_consulta", today)
                        dt_completa = f"{data_consulta} {hora}"
                        
                        if status == "Sucesso":
                            if "chaves" in detalhes or "Baixados" in detalhes:
                                if os.path.exists(client_dir):
                                    files_found = [f for f in os.listdir(client_dir) if f.endswith((".xml", ".pdf"))]
                                    if files_found:
                                        for f in files_found:
                                            match_key = re.search(r'\b\d{44}\b', f)
                                            k = match_key.group(0) if match_key else "N/A"
                                            resultados.append([cnpj, nome, k, "Baixado", dt_completa])
                                    else:
                                        resultados.append([cnpj, nome, "N/A", "Baixado", dt_completa])
                                else:
                                    resultados.append([cnpj, nome, "N/A", "Baixado", dt_completa])
                            else:
                                resultados.append([cnpj, nome, "N/A", "Sem Registros", dt_completa])
                        elif status == "Erro":
                            resultados.append([cnpj, nome, "N/A", f"Erro: {detalhes[:50]}", dt_completa])
                        else:
                            resultados.append([cnpj, nome, "N/A", "Pendente", dt_completa])
                except Exception as e_st:
                    print(f"[REBUILD] Erro ao ler status para {nome}: {e_st}")
                    resultados.append([cnpj, nome, "N/A", "Erro na leitura de status", dt_completa])
            else:
                resultados.append([cnpj, nome, "N/A", "Pendente", dt_completa])
                
        gerar_excel_resumo(resultados)
        print("[REBUILD] Planilha NF-e XML consolidada reconstruída.")
        return True
    except Exception as e:
        print(f"[REBUILD] Erro ao reconstruir planilha NF-e XML: {e}")
        return False
