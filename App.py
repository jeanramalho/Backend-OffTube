from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os, sys, subprocess, json, uuid, re, tempfile, datetime, time, random, shutil, socket
from urllib.parse import urlparse
from pathlib import Path
from threading import Thread
from dotenv import load_dotenv
import logging
import requests

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app)

# Pastas de armazenamento
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"

# Intervalos e variáveis de controle
COOKIE_CHECK_INTERVAL = datetime.timedelta(hours=6)
last_cookie_check = datetime.datetime.now()
cookie_refresh_attempts = 0
MAX_COOKIE_ATTEMPTS = 3

# Lista de User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0"
]

# Configuração do logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Log de requests e responses
@app.before_request
def log_request_info():
    logger.info('Headers: %s', request.headers)
    logger.info('Body: %s', request.get_data())

@app.after_request
def log_response_info(response):
    logger.info('Response: %s', response.get_data())
    return response

###############################################################################
# Funções de atualização e obtenção de cookies
###############################################################################

def get_fallback_cookies():
    """Obtém cookies via requisição HTTP sem Selenium."""
    logger.info("Tentando obter cookies pelo método alternativo...")
    youtube_email = os.environ.get("YOUTUBE_EMAIL")
    youtube_password = os.environ.get("YOUTUBE_PASSWORD")
    
    if not youtube_email or not youtube_password:
        logger.error("Credenciais não configuradas")
        return None

    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    })

    try:
        session.get('https://accounts.google.com/ServiceLogin?service=youtube')
        login_data = {
            'identifier': youtube_email,
            'password': youtube_password,
            'continue': 'https://www.youtube.com/'
        }
        _ = session.post(
            'https://accounts.google.com/signin/v2/challenge/pwd',
            data=login_data
        )
        response = session.get('https://www.youtube.com/')
        if response.status_code != 200:
            logger.error(f"Autenticação falhou: {response.status_code}")
            return None

        netscape_cookies = []
        for cookie in session.cookies:
            domain = cookie.domain.lstrip('.')
            path = cookie.path
            secure = 'TRUE' if cookie.secure else 'FALSE'
            expiry = str(int(cookie.expires)) if cookie.expires else '0'
            http_only = "TRUE" if cookie.has_nonstandard_attr('HttpOnly') else "FALSE"
            netscape_cookies.append(f"{domain}\t{http_only}\t{path}\t{secure}\t{expiry}\t{cookie.name}\t{cookie.value}")
        
        cookies_content = '\n'.join(netscape_cookies)
        os.environ["YOUTUBE_COOKIES"] = cookies_content
        with open("youtube_cookies.txt", "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# https://curl.se/docs/http-cookies.html\n")
            f.write("# Gerado por OffTube\n\n")
            f.write(cookies_content)
        logger.info("Cookies obtidos via fallback com sucesso")
        return cookies_content
        
    except Exception as e:
        logger.error(f"Falha no método alternativo: {str(e)}")
        return None

def refresh_youtube_cookies():
    """Obtém novos cookies do YouTube usando Selenium (ou fallback)."""
    global cookie_refresh_attempts
    logger.info("Iniciando refresh dos cookies do YouTube...")
    cookie_refresh_attempts += 1
    if cookie_refresh_attempts > MAX_COOKIE_ATTEMPTS:
        logger.warning(f"Máximo de tentativas ({MAX_COOKIE_ATTEMPTS}) excedido. Aguardando próximo ciclo.")
        cookie_refresh_attempts = 0
        time.sleep(3600)  # espera 1 hora
        return None

    youtube_email = os.environ.get("YOUTUBE_EMAIL")
    youtube_password = os.environ.get("YOUTUBE_PASSWORD")
    if not youtube_email or not youtube_password:
        logger.error("Credenciais do YouTube não configuradas")
        return None

    try:
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
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-tools")
        chrome_options.add_argument("--disable-software-rasterizer")
        
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 30)

        driver.get("https://www.youtube.com")
        time.sleep(3)

        try:
            login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'accounts.google.com')]")))
            login_button.click()
        except Exception as e:
            logger.warning("Botão de login não encontrado; redirecionando para página de login")
            driver.get("https://accounts.google.com/ServiceLogin?service=youtube")
            time.sleep(3)
            
        # Inserir email
        wait.until(EC.visibility_of_element_located((By.ID, "identifierId")))
        driver.find_element(By.ID, "identifierId").send_keys(youtube_email)
        driver.find_element(By.ID, "identifierNext").click()
        # Inserir senha
        wait.until(EC.visibility_of_element_located((By.NAME, "password")))
        driver.find_element(By.NAME, "password").send_keys(youtube_password)
        driver.find_element(By.ID, "passwordNext").click()
        time.sleep(5)

        page_source = driver.page_source.lower()
        if "verify it's you" in page_source or "verificar sua identidade" in page_source:
            logger.warning("Verificação adicional requerida. Usando fallback.")
            driver.quit()
            return get_fallback_cookies()

        driver.get("https://www.youtube.com")
        time.sleep(5)

        all_cookies = driver.get_cookies()
        netscape_cookies = []
        for cookie in all_cookies:
            domain = cookie.get('domain', '').lstrip('.')
            if 'youtube' in domain or 'google' in domain:
                http_only = "TRUE" if cookie.get('httpOnly', False) else "FALSE"
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                expiry = str(int(cookie.get('expiry', 0)))
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                if domain and name and value:
                    netscape_cookies.append(f"{domain}\t{http_only}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

        if not netscape_cookies:
            logger.error("Nenhum cookie obtido via Selenium; usando fallback")
            driver.quit()
            return get_fallback_cookies()
            
        cookies_content = '\n'.join(netscape_cookies)
        os.environ["YOUTUBE_COOKIES"] = cookies_content
        try:
            with open("youtube_cookies.txt", "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# Gerado por OffTube\n\n")
                f.write(cookies_content)
        except Exception as e:
            logger.warning(f"Erro ao salvar cookies em arquivo: {str(e)}")
            
        logger.info("Cookies atualizados com sucesso")
        driver.quit()
        cookie_refresh_attempts = 0
        return cookies_content

    except Exception as e:
        logger.error(f"Erro ao atualizar cookies via Selenium: {str(e)}")
        return get_fallback_cookies()

def background_cookie_check():
    """Thread para verificação periódica dos cookies."""
    global last_cookie_check
    while True:
        try:
            now = datetime.datetime.now()
            if (now - last_cookie_check) > COOKIE_CHECK_INTERVAL:
                logger.info("Verificando validade dos cookies...")
                refresh_youtube_cookies()
                last_cookie_check = now
        except Exception as e:
            logger.error(f"Erro na verificação dos cookies: {str(e)}")
        time.sleep(3600)  # checa a cada hora

###############################################################################
# Rotas da API
###############################################################################

@app.route("/debug", methods=["GET"])
def debug_info():
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key != os.environ.get("API_KEY"):
        return jsonify({"error": "Acesso não autorizado"}), 401

    system_info = {
        "platform": sys.platform,
        "python_version": sys.version,
        "hostname": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "working_dir": os.getcwd(),
        "files": os.listdir('.'),
        "env_vars": {k: "[REDACTED]" if any(x in k for x in ["PASSWORD", "KEY", "SECRET", "TOKEN"]) else v 
                     for k, v in os.environ.items()},
        "youtube_cookies_set": bool(os.environ.get("YOUTUBE_COOKIES")),
        "videos": os.listdir(DOWNLOAD_FOLDER) if os.path.exists(DOWNLOAD_FOLDER) else []
    }
    return jsonify({"debug_info": system_info})

def is_auth_error(error_msg):
    auth_keywords = ["cookies", "login", "authentication", "private video", "sign in", "account", "restricted", "HTTP Error 403"]
    return any(keyword in error_msg.lower() for keyword in auth_keywords)

@app.route("/download", methods=["POST"])
def download_video():
    logger.info("Requisição de download iniciada")
    data = request.get_json()
    url = data.get("url")
    if not url:
        logger.error("URL não fornecida")
        return jsonify({"error": "URL é obrigatória"}), 400

    # Verifica e atualiza os cookies se necessário
    cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
    if not cookies_content:
        logger.info("Cookies não encontrados. Atualizando...")
        cookies_content = refresh_youtube_cookies()
        if not cookies_content:
            return jsonify({"error": "Não foi possível obter cookies do YouTube"}), 500

    video_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.%(ext)s")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")

    parsed_url = urlparse(url)
    if parsed_url.netloc not in ['www.youtube.com', 'youtube.com', 'youtu.be', 'm.youtube.com']:
        logger.error(f"URL inválida: {url}")
        return jsonify({"error": "URL do YouTube inválida"}), 400

    # Cria as pastas se não existirem
    Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
    Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

    temp_cookies_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
            temp_cookies.write("# Netscape HTTP Cookie File\n")
            temp_cookies.write("# Gerado por OffTube\n\n")
            temp_cookies.write(cookies_content)
            temp_cookies_path = temp_cookies.name

        user_agent = random.choice(USER_AGENTS)
        cmd = [
            "yt-dlp",
            "--cookies", temp_cookies_path,
            "--format", "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
            "--merge-output-format", "mp4",
            "--output", output_template,
            "--write-thumbnail", "--convert-thumbnails", "jpg",
            "--no-playlist",
            "--user-agent", user_agent,
            "--sleep-interval", "1", "--max-sleep-interval", "5",
            "--add-header", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
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
            "--add-header", "Referer: https://www.youtube.com/",
            "--add-header", "Origin: https://www.youtube.com",
            "--extractor-args", "youtube:player_client=android",
            "--extractor-args", "youtube:player_skip=webpage",
            url
        ]
        logger.info("Executando comando: %s", ' '.join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        logger.info("Saída do comando: %s", result.stdout)
        logger.info("Erro do comando: %s", result.stderr)

        if result.returncode != 0:
            error_msg = result.stderr
            logger.error("Falha no download: %s", error_msg)
            if is_auth_error(error_msg):
                logger.warning("Erro de autenticação detectado. Atualizando cookies e tentando novamente.")
                cookies_content = refresh_youtube_cookies()
                if not cookies_content:
                    return jsonify({"error": "Falha na autenticação com o YouTube"}), 401
                if os.path.exists(temp_cookies_path):
                    os.unlink(temp_cookies_path)
                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                    temp_cookies.write("# Netscape HTTP Cookie File\n")
                    temp_cookies.write("# Gerado por OffTube\n\n")
                    temp_cookies.write(cookies_content)
                    temp_cookies_path = temp_cookies.name
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    return jsonify({"error": "Falha persistente no download. Tente novamente mais tarde.", "details": result.stderr}), 500
            else:
                return jsonify({"error": "Não foi possível baixar o vídeo", "details": error_msg}), 500

        downloaded_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(video_id)]
        if not downloaded_files:
            logger.error("Vídeo baixado mas não encontrado")
            return jsonify({"error": "Vídeo baixado mas não encontrado no servidor"}), 500

        video_filename = downloaded_files[0]
        video_path = os.path.join(DOWNLOAD_FOLDER, video_filename)
        logger.info("Download concluído: %s", video_filename)

        return jsonify({
            "success": True,
            "video_id": video_id,
            "filename": video_filename,
            "download_url": f"/videos/{video_filename}",
            "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None
        })

    except subprocess.TimeoutExpired:
        logger.error("Timeout ao baixar o vídeo")
        return jsonify({"error": "Tempo limite excedido ao baixar o vídeo"}), 504
    except Exception as e:
        logger.error("Erro inesperado: %s", str(e))
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if temp_cookies_path and os.path.exists(temp_cookies_path):
            os.unlink(temp_cookies_path)

@app.route("/videos/<filename>", methods=["GET"])
def serve_video(filename):
    video_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(video_path):
        return send_file(video_path)
    return jsonify({"error": "Vídeo não encontrado"}), 404

@app.route("/delete/<video_id>", methods=["DELETE"])
def delete_video(video_id):
    """
    Rota para deletar o vídeo e a thumbnail associada.
    O arquivo do vídeo tem o nome {video_id}.ext e a thumbnail {video_id}.jpg
    """
    # Encontrar arquivo de vídeo que comece com video_id
    matched_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(video_id)]
    if not matched_files:
        return jsonify({"error": "Vídeo não encontrado"}), 404
    try:
        for filename in matched_files:
            os.unlink(os.path.join(DOWNLOAD_FOLDER, filename))
        thumb_file = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
        if os.path.exists(thumb_file):
            os.unlink(thumb_file)
        logger.info("Arquivos do vídeo %s deletados", video_id)
        return jsonify({"success": True, "message": "Vídeo e thumbnail removidos."})
    except Exception as e:
        logger.error("Erro ao deletar arquivos: %s", str(e))
        return jsonify({"error": "Falha ao deletar arquivos"}), 500

###############################################################################
# Função de limpeza periódica de arquivos antigos
###############################################################################

def cleanup_old_files():
    while True:
        try:
            now = time.time()
            max_age = 12 * 3600  # 12 horas
            for folder in [DOWNLOAD_FOLDER, THUMBNAIL_FOLDER]:
                for f in os.listdir(folder):
                    f_path = os.path.join(folder, f)
                    if os.path.isfile(f_path) and (now - os.path.getmtime(f_path)) > max_age:
                        os.unlink(f_path)
                        logger.info("Arquivo removido: %s", f_path)
            logger.info("Limpeza de arquivos antigos concluída")
        except Exception as e:
            logger.error("Erro na limpeza de arquivos: %s", str(e))
        time.sleep(3600)

###############################################################################
# Execução da Aplicação
###############################################################################

if __name__ == "__main__":
    # Atualiza yt-dlp antes de iniciar
    try:
        subprocess.run(["yt-dlp", "-U"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("yt-dlp atualizado com sucesso")
    except Exception as e:
        logger.warning("Falha ao atualizar yt-dlp: %s", str(e))
    
    # Inicializa cookies se não estiverem definidos
    if not os.environ.get("YOUTUBE_COOKIES"):
        logger.info("Cookies não definidos. Tentando obtenção inicial...")
        refresh_youtube_cookies()
    
    # Inicia threads em background
    Thread(target=background_cookie_check, daemon=True).start()
    Thread(target=cleanup_old_files, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    logger.info("Iniciando servidor na porta %s", port)
    app.run(host="0.0.0.0", port=port)
