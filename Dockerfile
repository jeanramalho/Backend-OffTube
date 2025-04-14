FROM python:3.11-slim

# Configurar ambiente não interativo
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências essenciais
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates unzip xvfb \
    libglib2.0-0 libnss3 libfontconfig1 libxss1 \
    libasound2 libxtst6 libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Instalar Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Instalar ChromeDriver compatível
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f 1) \
    && CHROMEDRIVER_VERSION=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") \
    && wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip -d /usr/bin \
    && rm chromedriver_linux64.zip \
    && chmod +x /usr/bin/chromedriver

# Instalar FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Configurar permissões e ambiente
RUN mkdir -p videos thumbnails \
    && chmod 777 videos thumbnails

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROME_PATH=/usr/bin/google-chrome \
    PATH="/usr/bin:${PATH}"

EXPOSE ${PORT:-10000}

# Script de inicialização melhorado
RUN echo '#!/bin/bash\n\
Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &\n\
sleep 2\n\
python -u App.py' > /app/start.sh \
    && chmod +x /app/start.sh

CMD ["/app/start.sh"]