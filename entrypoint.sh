#!/bin/bash
set -e

# 1. Iniciar serviço do dbus se disponível
if [ -f /etc/init.d/dbus ]; then
    service dbus start || true
fi

# 2. Iniciar Xvfb em background para emular tela gráfica exigida pelo Chromium
log_msg() {
    echo "[ENTRYPOINT] $(date +'%Y-%m-%d %H:%M:%S') - $1"
}

log_msg "Iniciando Xvfb display virtual :99..."
Xvfb :99 -screen 0 1280x1024x24 -ac +extension GLX +render -noreset -nolisten tcp &
export DISPLAY=:99

# Aguarda o Xvfb inicializar
sleep 2

log_msg "Display virtual configurado. Iniciando aplicação..."
# 3. Executa o comando passado para o Docker
exec "$@"
