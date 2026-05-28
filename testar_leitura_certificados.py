import os
import re
import sys
from cryptography.hazmat.primitives.serialization import pkcs12

# Configurar encoding UTF-8 para stdout do Python no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def log(msg, level="INFO"):
    print(f"[{level}] {msg}")

def testar_todos():
    log("=== TESTE DE LEITURA E VALIDAÇÃO DOS CERTIFICADOS INCLUÍDOS ===", "SYSTEM")
    
    folder = os.path.abspath(os.path.join("certificados", "CONDOMINIO"))
    if not os.path.exists(folder):
        log(f"Pasta de condomínios não encontrada em: '{folder}'", "ERROR")
        return
        
    files = [f for f in os.listdir(folder) if f.lower().endswith(".pfx") or f.lower().endswith(".p12")]
    total_files = len(files)
    
    sucessos = []
    falhas = []
    
    for idx, f in enumerate(files, start=1):
        caminho_completo = os.path.join(folder, f)
        
        # Extrair senha do nome do arquivo
        senha_padrao = "123456"
        senha_encontrada = senha_padrao
        
        match_senha = re.search(r'senha\s*([a-zA-Z0-9@#$_-]+)', f, re.IGNORECASE)
        if match_senha:
            senha_encontrada = match_senha.group(1)
            
        try:
            with open(caminho_completo, "rb") as cert_file:
                pfx_data = cert_file.read()
                
            pass_bytes = senha_encontrada.encode('utf-8') if senha_encontrada else None
            
            # Tenta carregar a chave e certificados
            private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                pfx_data, pass_bytes
            )
            
            # Obter detalhes do sujeito do certificado
            subject = certificate.subject.rfc4514_string()
            cnpj_match = re.search(r'CNPJ=([0-9]{14})', subject)
            cnpj_cert = cnpj_match.group(1) if cnpj_match else "Não encontrado no subject"
            
            log(f"[{idx}/{total_files}] OK: '{f}' | CNPJ interno: {cnpj_cert}", "SUCCESS")
            sucessos.append((f, cnpj_cert))
        except Exception as e:
            log(f"[{idx}/{total_files}] ERRO: '{f}' | Motivo: {e}", "ERROR")
            falhas.append((f, str(e)))
            
    print("\n" + "="*80)
    log(f"Resumo do Teste: {len(sucessos)} com sucesso, {len(falhas)} falhas.", "SYSTEM")
    print("="*80)
    
    if falhas:
        print("\n=== CERTIFICADOS QUE FALHARAM NA VALIDAÇÃO ===")
        for f, err in falhas:
            print(f" - {f} : {err}")
        print("="*80)

if __name__ == "__main__":
    testar_todos()
