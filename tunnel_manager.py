import os
import re
import sys
import json
import time
import subprocess
import threading
import requests

# Variáveis globais de controle
active_tunnel_url = None
ssh_process = None
running = False

def log(msg, level="TUNNEL"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def load_config():
    config_default = {
        "portal_url": "https://cav.receita.fazenda.gov.br/ecac/",
        "clientes_file": "clientes.csv",
        "relatorios_dir": "relatorios",
        "timeout_ms": 30000,
        "download_timeout_ms": 60000,
        "cert_first_char": "J",
        "whatsapp_enabled": True
    }
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_default.update(json.load(f))
        except Exception as e:
            log(f"Erro ao carregar config.json: {e}", "ERROR")
    if os.path.exists("config_private.json"):
        try:
            with open("config_private.json", "r", encoding="utf-8") as f:
                config_default.update(json.load(f))
        except Exception as e:
            log(f"Erro ao carregar config_private.json: {e}", "ERROR")
    return config_default

def registrar_webhook_zapi(public_url):
    config = load_config()
    if not config.get("whatsapp_enabled"):
        log("Envio de WhatsApp desabilitado nas configurações. Pulando registro de webhook.")
        return False
        
    instance = config.get("whatsapp_zapi_instance")
    token = config.get("whatsapp_zapi_token")
    client_token = config.get("whatsapp_zapi_client_token")
    
    if not instance or not token:
        log("Erro: Instância ou Token da Z-API não configurados. Não foi possível registrar o webhook.", "ERROR")
        return False
        
    webhook_url = f"{public_url}/api/webhook/whatsapp"
    endpoints = [
        "update-webhook-received",
        "update-webhook-connected",
        "update-webhook-disconnected"
    ]
    
    headers = {
        "Content-Type": "application/json"
    }
    if client_token:
        headers["Client-Token"] = client_token
        
    payload = {
        "value": webhook_url
    }
    
    log(f"Iniciando registro do webhook automático: {webhook_url}...")
    
    success = True
    for endpoint in endpoints:
        url = f"https://api.z-api.io/instances/{instance}/token/{token}/{endpoint}"
        try:
            # Z-API usa PUT para atualização de webhook
            response = requests.put(url, headers=headers, json=payload, timeout=15)
            if response.status_code in [200, 201]:
                log(f"Webhook registrado com sucesso no evento '{endpoint}'!", "SUCCESS")
            else:
                log(f"Falha ao registrar webhook no evento '{endpoint}'. Status: {response.status_code}, Resposta: {response.text}", "WARNING")
                success = False
        except Exception as e:
            log(f"Erro de conexão ao registrar webhook '{endpoint}': {e}", "ERROR")
            success = False
            
    return success

def tunnel_worker():
    global active_tunnel_url, ssh_process, running
    
    while running:
        log("Iniciando túnel SSH com localhost.run...")
        
        # Comando SSH nativo para expor a porta 5000 local
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-R", "80:127.0.0.1:5000",
            "nokey@localhost.run"
        ]
        
        try:
            # Rodar o processo SSH capturando stdout e stderr
            ssh_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            url_detected = False
            
            # Ler a saída do processo linha por linha
            for line in iter(ssh_process.stdout.readline, ''):
                if not running:
                    break
                
                # Logar a linha do SSH para depuração
                line_clean = line.strip()
                if line_clean:
                    log(f"SSH: {line_clean}", "SSH_DEBUG")
                    
                # Procurar padrão de URL HTTPS lhr.life
                match = re.search(r"(https://[a-zA-Z0-9.-]+\.lhr\.life)", line)
                if match and not url_detected:
                    active_tunnel_url = match.group(1)
                    log(f"Túnel estabelecido com sucesso! URL pública: {active_tunnel_url}", "SUCCESS")
                    url_detected = True
                    
                    # Registrar webhook de forma assíncrona para não travar a leitura do stdout
                    threading.Thread(target=registrar_webhook_zapi, args=(active_tunnel_url,), daemon=True).start()
                    
            # Se saiu do loop, espera o término do processo
            ssh_process.wait()
            
        except Exception as e:
            log(f"Erro de execução do túnel SSH: {e}", "ERROR")
            
        if running:
            log("Túnel SSH desconectado. Aguardando 10 segundos antes de reconectar...", "WARNING")
            time.sleep(10)

def start():
    global running
    if running:
        return
    running = True
    t = threading.Thread(target=tunnel_worker, daemon=True)
    t.start()
    log("Thread do gerenciador de túnel SSH iniciada.")

def stop():
    global running, ssh_process, active_tunnel_url
    running = False
    active_tunnel_url = None
    if ssh_process:
        try:
            ssh_process.terminate()
            log("Processo do túnel SSH encerrado.")
        except Exception:
            pass
        ssh_process = None

import atexit
atexit.register(stop)
