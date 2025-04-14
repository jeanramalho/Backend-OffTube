FROM python:3.10-slim

WORKDIR /app

# Instalar dependências do sistema (ffmpeg, curl, etc.)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Atualizar certificados SSL
RUN update-ca-certificates

# Instalar yt-dlp diretamente no sistema
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod +x /usr/local/bin/yt-dlp

# Copiar arquivos da aplicação
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Criar pastas de vídeos e thumbnails, caso não existam
RUN mkdir -p videos thumbnails && \
    chmod -R 777 videos thumbnails

# Porta definida pelo Render automaticamente
ENV PORT=5000
EXPOSE $PORT

# Configurar variáveis de ambiente para SSL
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

CMD ["python", "App.py"]
