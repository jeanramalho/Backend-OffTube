FROM python:3.10-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Instalar yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod +x /usr/local/bin/yt-dlp

# Copiar arquivos do projeto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Criar pastas se não forem criadas em tempo de execução
RUN mkdir -p videos thumbnails

ENV PORT=5000
EXPOSE $PORT

CMD ["python", "app.py"]
