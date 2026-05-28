import csv
import os
import json
import re
import datetime

# Importações das funções do sistema
from executar import gerar_consolidado_excel, load_clients
from consultar_nota_fiscal_xml import gerar_excel_resumo, clean_filename, compilar_resultados_fiscais, obter_dados_certificado

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
        
        # Identificar dados do certificado ativo
        cnpj_cert, nome_cert, _ = obter_dados_certificado()
        
        # Compilar os dados fiscais a partir do disco
        resultados = compilar_resultados_fiscais(cnpj_cert_ativo=cnpj_cert)
        
        # Gerar a planilha Excel resumo formatada
        gerar_excel_resumo(resultados)
        
        print("[REBUILD] Planilha NF-e XML consolidada reconstruída com sucesso.")
        return True
    except Exception as e:
        print(f"[REBUILD] Erro ao reconstruir planilha NF-e XML: {e}")
        return False
