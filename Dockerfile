# Use uma imagem oficial do Python leve
FROM python:3.10-slim

# Define o diretório de trabalho
WORKDIR /app

# Instale dependências do sistema
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Instale yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod +x /usr/local/bin/yt-dlp

# Copie os arquivos do projeto
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .

# Crie as pastas para armazenar vídeos e thumbnails
RUN mkdir -p videos thumbnails

# Configure a porta; o Cloud Run define a variável PORT
ENV PORT=8080
EXPOSE 8080

# Inicia o servidor; use gunicorn para produção (opcional)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
