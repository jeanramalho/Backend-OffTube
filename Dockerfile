# Use uma imagem oficial do Python leve
FROM python:3.10-slim

# Define o diretório de trabalho no contêiner
WORKDIR /app

# Copia o arquivo de dependências para o contêiner
COPY requirements.txt .

# Instala as dependências
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia todo o código da aplicação para o contêiner
COPY . .

# Cria as pastas para armazenar os vídeos e thumbnails (caso não sejam criadas pelo código)
RUN mkdir -p videos thumbnails

# Define a variável de ambiente PORT (o Render irá injetar sua própria variável, mas caso não seja definida, usa 5000)
ENV PORT=5000

# Expõe a porta que a aplicação usará
EXPOSE $PORT

# Comando para iniciar a aplicação
CMD ["python", "app.py"]
