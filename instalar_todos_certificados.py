import os
import re
import subprocess
import sys

def log(msg, level="INFO"):
    print(f"[{level}] {msg}")

def instalar_todos():
    log("=== INSTALADOR AUTOMÁTICO DE CERTIFICADOS DIGITAIS ===", "SYSTEM")
    
    folder = os.path.abspath(os.path.join("certificados", "CONDOMINIO"))
    if not os.path.exists(folder):
        log(f"Pasta de condomínios não encontrada em: '{folder}'", "ERROR")
        return
        
    files = [f for f in os.listdir(folder) if f.lower().endswith(".pfx") or f.lower().endswith(".p12")]
    total_files = len(files)
    
    log(f"Encontrados {total_files} certificados na pasta para instalação.", "INFO")
    
    log("Limpando certificados expirados do repositório do Windows...", "INFO")
    try:
        cmd_clean = "powershell -Command \"Get-ChildItem Cert:\\CurrentUser\\My | Where-Object { $_.NotAfter -lt (Get-Date) } | Remove-Item -Force -ErrorAction SilentlyContinue\""
        subprocess.run(cmd_clean, capture_output=True, shell=True)
        log("Limpeza de certificados expirados concluída.", "SUCCESS")
    except Exception as e_clean:
        log(f"Falha ao limpar certificados expirados: {e_clean}", "WARNING")
        
    sucessos = 0
    falhas = 0
    
    for idx, f in enumerate(files, start=1):
        caminho_completo = os.path.join(folder, f)
        
        # Extrair senha do nome do arquivo
        senha_padrao = "123456"
        senha_encontrada = senha_padrao
        
        match_senha = re.search(r'senha\s*([a-zA-Z0-9@#$_-]+)', f, re.IGNORECASE)
        if match_senha:
            senha_encontrada = match_senha.group(1)
            
        log(f"[{idx}/{total_files}] Instalando: '{f}' (Senha: {senha_encontrada})...", "INFO")
        
        try:
            senha_esc = senha_encontrada.replace("'", "''")
            cmd_import = f"powershell -Command \"$p = ConvertTo-SecureString '{senha_esc}' -AsPlainText -Force; Import-PfxCertificate -FilePath '{caminho_completo}' -CertStoreLocation Cert:\\CurrentUser\\My -Password $p\""
            
            res = subprocess.run(cmd_import, capture_output=True, text=True, shell=True)
            if res.returncode == 0:
                log(f"Instalado com sucesso: '{f}'", "SUCCESS")
                sucessos += 1
            else:
                stderr_msg = res.stderr.strip() if res.stderr else "Erro desconhecido"
                log(f"Erro ao instalar '{f}': {stderr_msg}", "ERROR")
                falhas += 1
        except Exception as e:
            log(f"Exceção ao instalar '{f}': {e}", "ERROR")
            falhas += 1
            
    print("\n" + "="*50)
    log(f"Instalação finalizada: {sucessos} com sucesso, {falhas} falhas.", "SYSTEM")
    print("="*50)

if __name__ == "__main__":
    instalar_todos()
