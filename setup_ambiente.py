import os
import sys
import glob
import subprocess
import winreg
import json

def log_step(message):
    print(f"\n[+] {message}")

def log_success(message):
    print(f"    [OK] {message}")

def log_error(message):
    print(f"    [ERRO]: {message}")

def run_powershell(command):
    """Executes a PowerShell command and returns the output/errors."""
    process = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr

def setup_directories():
    log_step("Criando diretórios necessários...")
    os.makedirs("relatorios", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    log_success("Pastas 'relatorios' e 'logs' criadas com sucesso.")

def find_and_install_certificate():
    log_step("Buscando certificado digital (.pfx)...")
    pfx_files = glob.glob("*.pfx")
    
    if not pfx_files:
        log_error("Nenhum arquivo de certificado .pfx encontrado no diretório atual.")
        return False
        
    pfx_path = os.path.abspath(pfx_files[0])
    log_success(f"Certificado localizado: {os.path.basename(pfx_path)}")
    
    # Extrair a senha do nome do arquivo
    # Exemplo: 173995771_JEJ_SERVICOS_PROFISSIONAIS_LTDA_05443435000124SENHA123456.pfx
    filename = os.path.basename(pfx_path)
    password = None
    
    if "SENHA" in filename:
        try:
            parts = filename.split("SENHA")
            password = parts[1].replace(".pfx", "")
        except Exception:
            pass
            
    if not password:
        password = "123456" # Senha padrão sugerida
        log_step(f"Não foi possível extrair a senha dinamicamente. Utilizando senha padrão: {password}")
    else:
        log_success(f"Senha extraída dinamicamente do nome do arquivo: {password}")
        
    log_step("Instalando certificado no repositório do Windows (Current User -> Personal)...")
    
    # Comando PowerShell para importar o PFX
    ps_command = f"""
    $pfxpath = '{pfx_path}'
    $password = '{password}'
    $secure = ConvertTo-SecureString $password -AsPlainText -Force
    try {{
        $cert = Import-PfxCertificate -FilePath $pfxpath -CertStoreLocation Cert:\\CurrentUser\\My -Password $secure -ErrorAction Stop
        Write-Output "Certificado importado com sucesso: $($cert.Subject)"
    }} catch {{
        Write-Error $_.Exception.Message
    }}
    """
    
    returncode, stdout, stderr = run_powershell(ps_command)
    
    if returncode == 0 and "sucesso" in stdout.lower():
        log_success(stdout.strip())
        return True
    else:
        log_error(f"Falha ao importar o certificado: {stderr.strip() or stdout.strip()}")
        return False

def configure_browser_policies():
    log_step("Configurando políticas de auto-seleção de certificado no Registro do Windows...")
    
    # Padrões que o navegador deve auto-selecionar sem perguntar ao usuário
    patterns = [
        '{"pattern":"https://sso.acesso.gov.br","filter":{}}',
        '{"pattern":"https://cav.receita.fazenda.gov.br","filter":{}}'
    ]
    
    browsers = {
        "Google Chrome": r"Software\Policies\Google\Chrome\AutoSelectCertificateForUrls",
        "Microsoft Edge": r"Software\Policies\Microsoft\Edge\AutoSelectCertificateForUrls"
    }
    
    for browser_name, reg_path in browsers.items():
        try:
            # Criar/Abrir a chave no registro (CurrentUser)
            key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
            
            # Adicionar cada padrão de URL
            for idx, pattern in enumerate(patterns, start=1):
                winreg.SetValueEx(key, str(idx), 0, winreg.REG_SZ, pattern)
                
            winreg.CloseKey(key)
            log_success(f"Políticas configuradas com sucesso para o {browser_name}.")
        except Exception as e:
            log_error(f"Falha ao configurar registro para {browser_name}: {e}")

def create_config_file():
    log_step("Criando arquivo de configuração padrão (config.json)...")
    config = {
        "headless": False,             # Rodar com navegador visível para segurança e acompanhamento
        "timeout_ms": 30000,          # Timeout padrão de 30 segundos
        "relatorios_dir": "relatorios",
        "clientes_file": "clientes.csv",
        "portal_url": "https://cav.receita.fazenda.gov.br/eCAC/Default.aspx#",
        "download_timeout_ms": 60000  # Timeout para download de PDFs
    }
    
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
        
    log_success("Arquivo config.json criado com sucesso.")

def main():
    print("=" * 60)
    print(" CONFIGURAÇÃO DE AMBIENTE: AGENTE E-CAC FISCAL")
    print("=" * 60)
    
    setup_directories()
    cert_success = find_and_install_certificate()
    configure_browser_policies()
    create_config_file()
    
    print("\n" + "=" * 60)
    if cert_success:
        print(" AMBIENTE CONFIGURADO COM SUCESSO E PRONTO PARA USO!")
        print(" Agora você pode instalar os pacotes Python com:")
        print(" pip install playwright pandas")
        print(" playwright install chromium")
    else:
        print(" AMBIENTE CONFIGURADO COM AVISOS.")
        print(" Por favor, verifique se o arquivo .pfx está correto ou instale-o manualmente.")
    print("=" * 60)

if __name__ == "__main__":
    main()
