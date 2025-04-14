# Modificações no app.py
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import sys
import subprocess
import json
import uuid
import re
import tempfile
from dotenv import load_dotenv
from threading import Thread
import datetime
import time
import base64
import requests
import random
import shutil
import socket
from urllib.parse import urlparse
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configurações
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
last_cookie_check = datetime.datetime.now()
cookie_check_interval = datetime.timedelta(hours=6)  # Verificar a cada 6 horas

# Adicionar variáveis de controle para melhorar gestão do estado
cookie_refresh_attempts = 0
MAX_COOKIE_ATTEMPTS = 3
PROXY_SERVERS = os.environ.get("PROXY_SERVERS", "").split(",")
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0"
]

# Configurar logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@app.before_request
def log_request_info():
    logger.info('Headers: %s', request.headers)
    logger.info('Body: %s', request.get_data())

@app.after_request
def log_response_info(response):
    logger.info('Response: %s', response.get_data())
    return response

def update_ytdlp():
    """Atualiza o yt-dlp periodicamente para manter compatibilidade"""
    print("[INFO] Verificando atualizações do yt-dlp...")
    try:
        subprocess.run(
            ["yt-dlp", "-U"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print("[INFO] yt-dlp atualizado com sucesso")
    except subprocess.CalledProcessError as e:
        print(f"[AVISO] Falha ao atualizar yt-dlp: {str(e)}")

def background_cookie_check():
    """Verifica periodicamente a validade dos cookies"""
    global last_cookie_check
    while True:
        try:
            now = datetime.datetime.now()
            if (now - last_cookie_check) > cookie_check_interval:
                print("[INFO] Verificando validade dos cookies...")
                refresh_youtube_cookies()
                last_cookie_check = now
        except Exception as e:
            print(f"[ERRO] Falha na verificação de cookies: {str(e)}")
        time.sleep(3600)  # Verificar a cada hora

def get_fallback_cookies():
    """
    Tenta obter cookies do YouTube diretamente sem Selenium como fallback
    """
    print("[INFO] Tentando obter cookies via método alternativo...")
    
    youtube_email = os.environ.get("YOUTUBE_EMAIL")
    youtube_password = os.environ.get("YOUTUBE_PASSWORD")
    
    if not youtube_email or not youtube_password:
        print("[ERRO] Credenciais não configuradas")
        return None
        
    # Usar bibliotecas HTTP padrão como fallback
    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    })
    
    try:
        # Carregar página inicial
        session.get('https://accounts.google.com/ServiceLogin?service=youtube')
        
        # Fazer login
        login_data = {
            'identifier': youtube_email,
            'password': youtube_password,
            'continue': 'https://www.youtube.com/'
        }
        
        response = session.post(
            'https://accounts.google.com/signin/v2/challenge/pwd',
            data=login_data
        )
        
        # Ir para YouTube para capturar cookies
        response = session.get('https://www.youtube.com/')
        
        if response.status_code != 200:
            print(f"[ERRO] Falha na autenticação alternativa: {response.status_code}")
            return None
            
        # Converter cookies para formato netscape
        netscape_cookies = []
        for cookie in session.cookies:
            domain = cookie.domain.lstrip('.')
            path = cookie.path
            secure = 'TRUE' if cookie.secure else 'FALSE'
            expiry = str(int(cookie.expires)) if cookie.expires else '0'
            http_only = 'TRUE' if cookie.has_nonstandard_attr('HttpOnly') else 'FALSE'
            
            netscape_cookies.append(f"{domain}\t{http_only}\t{path}\t{secure}\t{expiry}\t{cookie.name}\t{cookie.value}")
        
        cookies_content = '\n'.join(netscape_cookies)
        
        # Salvar cookies
        os.environ["YOUTUBE_COOKIES"] = cookies_content
        with open("youtube_cookies.txt", "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# https://curl.se/docs/http-cookies.html\n")
            f.write("# This file was generated by OffTube! Edit at your own risk.\n\n")
            f.write(cookies_content)
            
        print("[INFO] Cookies obtidos com sucesso via método alternativo")
        return cookies_content
        
    except Exception as e:
        print(f"[ERRO] Falha no método alternativo: {str(e)}")
        return None

def refresh_youtube_cookies():
    """
    Função para obter novos cookies do YouTube usando Selenium
    """
    global cookie_refresh_attempts
    logger.info("Iniciando refresh de cookies do YouTube...")
    
    # Incrementar contador de tentativas
    cookie_refresh_attempts += 1
    if cookie_refresh_attempts > MAX_COOKIE_ATTEMPTS:
        logger.warning(f"Excedido número máximo de tentativas ({MAX_COOKIE_ATTEMPTS}). Aguardando próximo ciclo.")
        cookie_refresh_attempts = 0
        time.sleep(3600)  # Esperar 1 hora
        return None
    
    # Credenciais do YouTube
    youtube_email = os.environ.get("YOUTUBE_EMAIL")
    youtube_password = os.environ.get("YOUTUBE_PASSWORD")
    
    if not youtube_email or not youtube_password:
        logger.error("Credenciais do YouTube não configuradas")
        return None
    
    try:
        # Configurar Chrome em modo headless com melhorias
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Reduzir uso de memória
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-tools")
        chrome_options.add_argument("--disable-software-rasterizer")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            wait = WebDriverWait(driver, 30)
            
            # Acessar YouTube diretamente
            driver.get("https://www.youtube.com")
            time.sleep(3)
            
            # Procurar botão de login e clicar
            try:
                login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'accounts.google.com')]")))
                login_button.click()
            except Exception as e:
                logger.warning(f"Não foi possível encontrar botão de login: {str(e)}")
                driver.get("https://accounts.google.com/ServiceLogin?service=youtube")
                time.sleep(3)
            
            # Login com email
            wait.until(EC.visibility_of_element_located((By.ID, "identifierId")))
            driver.find_element(By.ID, "identifierId").send_keys(youtube_email)
            driver.find_element(By.ID, "identifierNext").click()
            
            # Login com senha
            wait.until(EC.visibility_of_element_located((By.NAME, "password")))
            driver.find_element(By.NAME, "password").send_keys(youtube_password)
            driver.find_element(By.ID, "passwordNext").click()
            
            # Esperar login completar e verificar se precisa de verificação adicional
            time.sleep(5)
            
            # Verificar se estamos em página de verificação
            page_source = driver.page_source.lower()
            if "verify it's you" in page_source or "verificar sua identidade" in page_source:
                logger.warning("Necessária verificação adicional. Tentando método alternativo...")
                driver.quit()
                return get_fallback_cookies()
            
            # Navegar para o YouTube
            driver.get("https://www.youtube.com")
            time.sleep(5)
            
            # Obter cookies
            all_cookies = driver.get_cookies()
            
            # Formatar cookies para o formato Netscape
            netscape_cookies = []
            for cookie in all_cookies:
                domain = cookie.get('domain', '')
                if 'youtube' in domain or 'google' in domain:
                    # Remover o ponto inicial do domínio se existir
                    domain = domain.lstrip('.')
                    
                    http_only = "TRUE" if cookie.get('httpOnly', False) else "FALSE"
                    path = cookie.get('path', '/')
                    secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                    expiry = str(int(cookie.get('expiry', 0)))
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    
                    # Adicionar apenas cookies válidos
                    if domain and name and value:
                        netscape_cookies.append(f"{domain}\t{http_only}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
            
            if not netscape_cookies:
                logger.error("Nenhum cookie válido encontrado via Selenium")
                driver.quit()
                return get_fallback_cookies()
                
            cookies_content = '\n'.join(netscape_cookies)
            
            # Salvar na variável de ambiente
            os.environ["YOUTUBE_COOKIES"] = cookies_content
            
            # Salvar em arquivo para persistência
            try:
                with open("youtube_cookies.txt", "w") as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    f.write("# https://curl.se/docs/http-cookies.html\n")
                    f.write("# This file was generated by OffTube! Edit at your own risk.\n\n")
                    f.write(cookies_content)
            except Exception as e:
                logger.warning(f"Não foi possível salvar cookies em arquivo: {str(e)}")
                
            logger.info("Cookies do YouTube atualizados com sucesso")
            
            # Fechar browser
            driver.quit()
            
            # Resetar contador de tentativas
            cookie_refresh_attempts = 0
            
            return cookies_content
            
        except Exception as selenium_error:
            logger.error(f"Falha ao usar Selenium: {str(selenium_error)}")
            
            if 'driver' in locals():
                try:
                    driver.quit()
                except:
                    pass
                    
            # Tentar método alternativo
            return get_fallback_cookies()
            
    except Exception as e:
        logger.error(f"Falha ao atualizar cookies: {str(e)}")
        return get_fallback_cookies()

@app.route("/debug", methods=["GET"])
def debug_info():
    """Endpoint para coletar informações de debug"""
    try:
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != os.environ.get("API_KEY"):
            return jsonify({"error": "Acesso não autorizado"}), 401

        # Obter status do sistema
        system_info = {
            "platform": sys.platform,
            "python_version": sys.version,
            "hostname": socket.gethostname(),
            "ip": socket.gethostbyname(socket.gethostname()),
            "working_dir": os.getcwd(),
            "files_in_working_dir": os.listdir('.'),
            "env_vars": {k: "[REDACTED]" if "PASSWORD" in k or "KEY" in k or "SECRET" in k or "TOKEN" in k else v 
                         for k, v in os.environ.items()},
            "cookies_file_exists": os.path.exists("youtube_cookies.txt"),
            "cookies_file_size": os.path.getsize("youtube_cookies.txt") if os.path.exists("youtube_cookies.txt") else 0,
            "cookies_env_set": bool(os.environ.get("YOUTUBE_COOKIES")),
            "downloads_folder": {
                "exists": os.path.exists(DOWNLOAD_FOLDER),
                "items": os.listdir(DOWNLOAD_FOLDER) if os.path.exists(DOWNLOAD_FOLDER) else []
            },
            "disk_usage": shutil.disk_usage("/")._asdict()
        }
        
        # Testar se o executável do Chrome está acessível
        chrome_test = {"chrome_executable": None, "chrome_version": None}
        try:
            chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")
            chrome_test["chrome_executable"] = os.path.exists(chrome_path)
            chrome_version = subprocess.run(
                [chrome_path, "--version"], 
                capture_output=True, 
                text=True
            ).stdout.strip()
            chrome_test["chrome_version"] = chrome_version
        except Exception as e:
            chrome_test["chrome_error"] = str(e)
        
        system_info["chrome"] = chrome_test
        
        # Testar yt-dlp
        ytdlp_test = {}
        try:
            ytdlp_version = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True
            ).stdout.strip()
            ytdlp_test["version"] = ytdlp_version
            ytdlp_test["available"] = True
        except Exception as e:
            ytdlp_test["available"] = False
            ytdlp_test["error"] = str(e)
            
        system_info["yt-dlp"] = ytdlp_test

        return jsonify({"debug_info": system_info})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
def is_auth_error(error_msg):
    """Verifica se o erro é relacionado a autenticação/cookies"""
    auth_keywords = [
        "cookies", 
        "login", 
        "authentication", 
        "private video", 
        "sign in",
        "account",
        "restricted",
        "HTTP Error 403"
    ]
    return any(keyword in error_msg.lower() for keyword in auth_keywords)

@app.route("/download", methods=["POST"])
def download_video():
    try:
        logger.info("Iniciando requisição de download")
        data = request.get_json()
        url = data.get("url")

        if not url:
            logger.error("URL não fornecida")
            return jsonify({"error": "URL é obrigatória"}), 400

        # Verificação inicial de cookies
        cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
        if not cookies_content:
            logger.warning("Cookies não encontrados, tentando obter novos cookies")
            cookies_content = refresh_youtube_cookies()
            if not cookies_content:
                logger.error("Não foi possível obter cookies do YouTube")
                return jsonify({"error": "Não foi possível obter cookies do YouTube"}), 500

        video_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.%(ext)s")
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")

        logger.info(f"Baixando vídeo: {url}")
        logger.info(f"Caminho de saída: {output_template}")

        # Verificar se a URL é válida
        parsed_url = urlparse(url)
        if not (parsed_url.netloc in ['www.youtube.com', 'youtube.com', 'youtu.be', 'm.youtube.com']):
            logger.error(f"URL inválida: {url}")
            return jsonify({"error": "URL do YouTube inválida"}), 400
            
        # Verificar e criar pastas se não existirem
        Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
        Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)
            
        temp_cookies_path = None
        try:
            # Criar arquivo de cookies no formato Netscape
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                # Adicionar cabeçalho Netscape
                temp_cookies.write("# Netscape HTTP Cookie File\n")
                temp_cookies.write("# https://curl.se/docs/http-cookies.html\n")
                temp_cookies.write("# This file was generated by OffTube! Edit at your own risk.\n\n")
                temp_cookies.write(cookies_content)
                temp_cookies_path = temp_cookies.name

            # Usar um User-Agent aleatório para cada requisição
            user_agent = random.choice(USER_AGENTS)
            
            # Comando para baixar o vídeo com mais opções para evitar bloqueios
            cmd = [
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "--format", "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                "--merge-output-format", "mp4",
                "--output", output_template,
                "--write-thumbnail",
                "--convert-thumbnails", "jpg",
                "--no-playlist",
                "--user-agent", user_agent,
                "--sleep-interval", "1", "--max-sleep-interval", "5",
                "--add-header", f"Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "--add-header", "Accept-Language: pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "--add-header", "Accept-Encoding: gzip, deflate, br",
                "--add-header", "DNT: 1",
                "--add-header", "Connection: keep-alive",
                "--add-header", "Upgrade-Insecure-Requests: 1",
                "--add-header", "Sec-Fetch-Dest: document",
                "--add-header", "Sec-Fetch-Mode: navigate",
                "--add-header", "Sec-Fetch-Site: none",
                "--add-header", "Sec-Fetch-User: ?1",
                "--add-header", "Cache-Control: max-age=0",
                "--add-header", f"Referer: https://www.youtube.com/",
                "--add-header", "Origin: https://www.youtube.com",
                "--extractor-args", "youtube:player_client=android",
                "--extractor-args", "youtube:player_skip=webpage",
                url
            ]

            logger.info(f"Executando comando: {' '.join(cmd)}")

            # Executar o comando
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutos de timeout
            )

            logger.info(f"Saída do comando: {result.stdout}")
            logger.info(f"Erro do comando: {result.stderr}")

            # Verificar se houve erro
            if result.returncode != 0:
                error_msg = result.stderr
                logger.error(f"Falha ao baixar vídeo: {error_msg}")
                
                # Verificar se é erro de autenticação
                if is_auth_error(str(error_msg)):
                    logger.warning("Erro de autenticação detectado, tentando atualizar cookies...")
                    cookies_content = refresh_youtube_cookies()
                    if not cookies_content:
                        return jsonify({"error": "Falha na autenticação com o YouTube"}), 401
                    
                    # Tentar novamente com novos cookies
                    if os.path.exists(temp_cookies_path):
                        os.unlink(temp_cookies_path)
                        
                    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                        temp_cookies.write("# Netscape HTTP Cookie File\n")
                        temp_cookies.write("# https://curl.se/docs/http-cookies.html\n")
                        temp_cookies.write("# This file was generated by OffTube! Edit at your own risk.\n\n")
                        temp_cookies.write(cookies_content)
                        temp_cookies_path = temp_cookies.name
                        
                    # Nova tentativa com outros cookies
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    
                    if result.returncode != 0:
                        error_msg = result.stderr
                        logger.error(f"Segunda tentativa falhou: {error_msg}")
                        return jsonify({"error": "Falha persistente no download. Por favor, tente novamente mais tarde."}), 500
                
                # Se não for erro de autenticação ou a segunda tentativa falhar
                if result.returncode != 0:
                    return jsonify({"error": "Não foi possível baixar o vídeo", "details": error_msg}), 500

            # Encontrar o arquivo baixado
            downloaded_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(video_id)]
            if not downloaded_files:
                logger.error("Vídeo baixado mas não encontrado no servidor")
                return jsonify({"error": "Vídeo baixado mas não encontrado no servidor"}), 500

            video_filename = downloaded_files[0]
            video_path = os.path.join(DOWNLOAD_FOLDER, video_filename)

            logger.info(f"Download concluído com sucesso: {video_filename}")

            # Retornar informações do vídeo
            return jsonify({
                "success": True,
                "video_id": video_id,
                "filename": video_filename,
                "download_url": f"/videos/{video_filename}",
                "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None
            })

        finally:
            # Limpar arquivo temporário de cookies
            if temp_cookies_path and os.path.exists(temp_cookies_path):
                os.unlink(temp_cookies_path)

    except subprocess.TimeoutExpired:
        logger.error("Tempo limite excedido ao baixar o vídeo")
        return jsonify({"error": "Tempo limite excedido ao baixar o vídeo"}), 504
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500

# Nova função para limpar regularmente arquivos antigos
def cleanup_old_files():
    """Remove vídeos e thumbnails antigos para evitar encher o disco"""
    while True:
        try:
            now = time.time()
            # Remover arquivos mais antigos que 12 horas
            max_age = 12 * 3600
            
            # Limpar pasta de vídeos
            for f in os.listdir(DOWNLOAD_FOLDER):
                f_path = os.path.join(DOWNLOAD_FOLDER, f)
                if os.path.isfile(f_path) and (now - os.path.getmtime(f_path)) > max_age:
                    os.unlink(f_path)
                    print(f"[INFO] Arquivo removido: {f_path}")
            
            # Limpar pasta de thumbnails
            for f in os.listdir(THUMBNAIL_FOLDER):
                f_path = os.path.join(THUMBNAIL_FOLDER, f)
                if os.path.isfile(f_path) and (now - os.path.getmtime(f_path)) > max_age:
                    os.unlink(f_path)
            
            print("[INFO] Limpeza de arquivos antigos concluída")
        except Exception as e:
            print(f"[ERRO] Falha na limpeza de arquivos: {str(e)}")
            
        # Executar a cada 1 hora
        time.sleep(3600)

if __name__ == "__main__":
    # Tentar atualizar yt-dlp no início
    update_ytdlp()
    
    # Verificar cookies no início
    cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
    if not cookies_content:
        logger.warning("Cookies não encontrados, tentando obter novos cookies...")
        refresh_youtube_cookies()
    
    # Iniciar thread de verificação de cookies
    cookie_checker = Thread(target=background_cookie_check)
    cookie_checker.daemon = True  # Encerrar quando o programa principal encerrar
    cookie_checker.start()
    
    # Iniciar thread de limpeza de arquivos
    cleanup_thread = Thread(target=cleanup_old_files)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    # Iniciar aplicativo Flask
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Iniciando servidor na porta {port}")
    app.run(host="0.0.0.0", port=port)