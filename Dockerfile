FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Evita prompts de interação durante a instalação de pacotes
ENV DEBIAN_FRONTEND=noninteractive

# Instala ferramentas do sistema para virtualização de display e suporte a certificados
RUN apt-get update && apt-get install -y \
    xvfb \
    libnss3-tools \
    libnss3 \
    dbus \
    dbus-x11 \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia os arquivos do projeto
COPY . .

# Torna o script de entrypoint executável
RUN chmod +x entrypoint.sh

# Porta padrão exposta pelo painel Flask
EXPOSE 5000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "app.py"]
