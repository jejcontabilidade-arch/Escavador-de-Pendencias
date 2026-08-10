import os
import csv
import re
import json
from database_manager import DatabaseManager

def load_config():
    config_path = "config.json"
    private_config_path = "config_private.json"
    config = {
        "caminho_certificados_servidor": r"\\Srvjej\contabilidade 2023\8 - CERTIFICADOS",
        "caminho_certificados_local": r"C:\Certificados_Escavador",
        "senha_padrao_pfx": "123456"
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except:
            pass
    if os.path.exists(private_config_path):
        try:
            with open(private_config_path, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except:
            pass
    return config

def buscar_pfx_recursivo(caminho_dir, cnpj_limpo):
    if not os.path.exists(caminho_dir):
        return None, None
    for root, dirs, files in os.walk(caminho_dir):
        for f in files:
            if cnpj_limpo in f and (f.lower().endswith(".pfx") or f.lower().endswith(".p12")):
                return os.path.join(root, f), f
    return None, None

def migrar():
    print("=== INICIANDO MIGRAÇÃO DE CLIENTES DO CSV PARA O BANCO DE DADOS ===")
    config = load_config()
    db = DatabaseManager()
    
    clientes_csv = config.get("clientes_file", "clientes.csv")
    if not os.path.exists(clientes_csv):
        print(f"[ERRO] Arquivo CSV '{clientes_csv}' não localizado. Abortando migração.")
        return
        
    # Mapear diretórios de certificados para busca
    pastas_busca = []
    if os.path.exists(config["caminho_certificados_servidor"]):
        pastas_busca.append(config["caminho_certificados_servidor"])
    if os.path.exists(config["caminho_certificados_local"]):
        pastas_busca.append(config["caminho_certificados_local"])
    
    path_interno = os.path.abspath("certificados")
    if os.path.exists(path_interno):
        pastas_busca.append(path_interno)
        
    print(f"Diretórios de busca de certificados configurados: {pastas_busca}")
    
    count_importados = 0
    count_pfx_vinculados = 0
    
    with open(clientes_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cnpj = row.get("cnpj", "").strip()
            nome = row.get("nome", "").strip()
            ativo_str = row.get("ativo", "True").strip().lower()
            ativo = 1 if ativo_str in ["true", "1", "yes", "ativo", "sim", "s"] else 0
            
            cnpj_clean = "".join(filter(str.isdigit, cnpj)).zfill(14)
            if not cnpj_clean:
                continue
                
            # Buscar certificado PFX
            caminho_pfx = None
            senha = None
            
            for pasta in pastas_busca:
                pfx_path, pfx_filename = buscar_pfx_recursivo(pasta, cnpj_clean)
                if pfx_path:
                    caminho_pfx = os.path.abspath(pfx_path)
                    
                    # Tentar extrair senha do nome
                    senha = config.get("senha_padrao_pfx", "123456")
                    match_senha = re.search(r'senha\s*([a-zA-Z0-9@#$_-]+)', pfx_filename, re.IGNORECASE)
                    if match_senha:
                        senha = match_senha.group(1)
                    break
            
            # Salvar no banco SQL
            db.salvar_cliente(
                cnpj=cnpj_clean,
                nome=nome,
                ativo=ativo,
                pfx_path=caminho_pfx,
                senha=senha,
                data_validade=None # Será obtido dinamicamente na execução ou carregamento
            )
            
            count_importados += 1
            if caminho_pfx:
                count_pfx_vinculados += 1
                
    print("=" * 70)
    print(f"[MIGRAÇÃO CONCLUÍDA]")
    print(f"Total de Clientes Importados no Banco: {count_importados}")
    print(f"Clientes Vinculados a Certificados (.pfx): {count_pfx_vinculados}")
    print("=" * 70)

if __name__ == "__main__":
    migrar()
