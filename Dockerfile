FROM python:3.10-slim

WORKDIR /app

# Instalar dependências do sistema (ffmpeg, curl, etc.)
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Instalar yt-dlp diretamente no sistema
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod +x /usr/local/bin/yt-dlp

# Copiar arquivos da aplicação
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Criar pastas de vídeos e thumbnails, caso não existam
RUN mkdir -p videos thumbnails

# Porta definida pelo Render automaticamente
ENV PORT=5000
EXPOSE $PORT

CMD ["python", "app.py"]
