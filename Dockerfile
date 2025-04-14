FROM python:3.11-slim

# Instalar dependências essenciais do sistema de forma otimizada
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates unzip xvfb \
    libglib2.0-0 libnss3 libfontconfig1 libxss1 \
    libasound2 libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# Instalar Chrome de forma mais eficiente
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Instalar ChromeDriver de forma mais eficiente
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f 1) \
    && CHROMEDRIVER_VERSION=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") \
    && wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip -d /usr/local/bin \
    && rm chromedriver_linux64.zip \
    && chmod +x /usr/local/bin/chromedriver

# Instalar FFmpeg mínimo
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# Configurar diretório de trabalho
WORKDIR /app

# Instalar apenas as dependências Python essenciais primeiro
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Criar diretórios para vídeos e thumbnails com permissões corretas
RUN mkdir -p videos thumbnails \
    && chmod 777 videos thumbnails

# Configurar variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROME_PATH=/usr/bin/google-chrome \
    PATH="/usr/local/bin:${PATH}"

# Expor porta
EXPOSE ${PORT:-10000}

# Iniciar Xvfb e a aplicação com script wrapper
RUN echo '#!/bin/bash\nXvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &\npython app.py' > /app/start.sh \
    && chmod +x /app/start.sh

CMD ["/app/start.sh"]