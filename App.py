from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import subprocess
import json
import uuid
import re
import tempfile
from dotenv import load_dotenv
from threading import Thread
import datetime
import time
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

# Criar pastas se não existirem
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

def refresh_youtube_cookies():
    """
    Função para obter novos cookies do YouTube usando Selenium
    """
    print("[INFO] Iniciando refresh de cookies do YouTube...")
    
    # Credenciais do YouTube (recomendo obter de variáveis de ambiente)
    youtube_email = os.environ.get("YOUTUBE_EMAIL")
    youtube_password = os.environ.get("YOUTUBE_PASSWORD")
    
    if not youtube_email or not youtube_password:
        print("[ERRO] Credenciais do YouTube não configuradas")
        return None
    
    try:
        # Configurar Chrome em modo headless
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 20)
        
        # Acessar YouTube
        driver.get("https://accounts.google.com/signin")
        
        # Login com email
        wait.until(EC.visibility_of_element_located((By.ID, "identifierId")))
        driver.find_element(By.ID, "identifierId").send_keys(youtube_email)
        driver.find_element(By.ID, "identifierNext").click()
        
        # Login com senha
        wait.until(EC.visibility_of_element_located((By.NAME, "password")))
        driver.find_element(By.NAME, "password").send_keys(youtube_password)
        driver.find_element(By.ID, "passwordNext").click()
        
        # Esperar login completar
        time.sleep(5)
        
        # Navegar para o YouTube
        driver.get("https://www.youtube.com")
        time.sleep(3)
        
        # Obter cookies
        all_cookies = driver.get_cookies()
        
        # Formatar cookies para o formato que você usa
        netscape_cookies = []
        for cookie in all_cookies:
            domain = cookie.get('domain', '')
            if 'youtube' in domain or 'google' in domain:
                http_only = "TRUE" if cookie.get('httpOnly', False) else "FALSE"
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                expiry = str(int(cookie.get('expiry', 0)))
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                
                netscape_cookies.append(f"{domain}\t{http_only}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
                
        cookies_content = '\n'.join(netscape_cookies)
        
        # Salvar na variável de ambiente
        os.environ["YOUTUBE_COOKIES"] = cookies_content
        
        # Opcional: salvar em arquivo para persistência
        try:
            with open("youtube_cookies.txt", "w") as f:
                f.write(cookies_content)
        except Exception as e:
            print(f"[AVISO] Não foi possível salvar cookies em arquivo: {str(e)}")
            
        print("[INFO] Cookies do YouTube atualizados com sucesso")
        
        # Fechar browser
        driver.quit()
        
        return cookies_content
        
    except Exception as e:
        print(f"[ERRO] Falha ao atualizar cookies: {str(e)}")
        if 'driver' in locals():
            driver.quit()
        return None

def is_auth_error(error_text):
    """Verifica se o erro está relacionado à autenticação"""
    auth_errors = [
        "Sign in to confirm you're not a bot",
        "This video is private",
        "This video is only available to Music Premium members",
        "This video requires payment",
        "Please sign in to view this video",
        "Sign in to YouTube"
    ]
    
    return any(err in error_text for err in auth_errors)

def background_cookie_check():
    """Thread de fundo para verificar cookies periodicamente"""
    global last_cookie_check
    
    while True:
        now = datetime.datetime.now()
        
        # Verificar se é hora de atualizar
        if now - last_cookie_check > cookie_check_interval:
            print(f"[INFO] Verificação periódica de cookies: {now}")
            try:
                # Testar se cookies ainda são válidos com uma requisição simples
                test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Vídeo popular para teste
                
                cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
                if not cookies_content:
                    print("[AVISO] Cookies não encontrados, obtendo novos cookies...")
                    refresh_youtube_cookies()
                    last_cookie_check = now
                    continue
                
                # Criar arquivo temporário de cookies para o teste
                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                    temp_cookies.write("# Netscape HTTP Cookie File\n")
                    temp_cookies.write("# https://curl.se/docs/http-cookies.html\n")
                    temp_cookies.write("# This file was generated by OffTube! Edit at your own risk.\n\n")
                    temp_cookies.write(cookies_content)
                    temp_cookies_path = temp_cookies.name
                
                # Executar yt-dlp apenas para verificar título (teste rápido)
                test_cmd = [
                    "yt-dlp",
                    "--cookies", temp_cookies_path,
                    "--skip-download",
                    "--get-title",
                    test_url
                ]
                
                test_result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                # Limpar arquivo temporário
                if os.path.exists(temp_cookies_path):
                    os.unlink(temp_cookies_path)
                
                # Verificar se houve erro de autenticação
                if test_result.returncode != 0 or is_auth_error(test_result.stderr):
                    print("[AVISO] Cookies expirados, atualizando...")
                    refresh_youtube_cookies()
                else:
                    print("[INFO] Cookies ainda válidos, próxima verificação em 6 horas")
                
                last_cookie_check = now
                
            except Exception as e:
                print(f"[ERRO] Falha na verificação de cookies: {str(e)}")
            
        # Esperar 30 minutos antes da próxima verificação
        time.sleep(1800)

def update_ytdlp():
    """Função para atualizar yt-dlp"""
    try:
        subprocess.run(["pip", "install", "--upgrade", "yt-dlp"], check=True)
        print("[INFO] yt-dlp atualizado com sucesso")
    except Exception as e:
        print(f"[ERRO] Falha ao atualizar yt-dlp: {str(e)}")

@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        # Verificação inicial de cookies
        cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
        if not cookies_content:
            print("[AVISO] Cookies não encontrados, tentando obter novos cookies")
            cookies_content = refresh_youtube_cookies()
            if not cookies_content:
                return jsonify({"error": "Cookies do YouTube não configurados no servidor"}), 500

        video_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.%(ext)s")
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")

        print(f"[INFO] Baixando vídeo: {url}")
        print(f"[INFO] Caminho de saída: {output_template}")

        # Verificar se a URL é válida
        if not re.match(r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/', url):
            print(f"[ERRO] URL inválida: {url}")
            return jsonify({"error": "URL do YouTube inválida"}), 400
            
        temp_cookies_path = None
        try:
            # Criar arquivo de cookies no formato Netscape
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                # Adicionar cabeçalho Netscape
                temp_cookies.write("# Netscape HTTP Cookie File\n")
                temp_cookies.write("# https://curl.se/docs/http-cookies.html\n")
                temp_cookies.write("# This file was generated by OffTube! Edit at your own risk.\n\n")
                
                # Converter cookies para formato Netscape
                cookies_lines = cookies_content.split('\n')
                for line in cookies_lines:
                    if line.strip() and not line.startswith('#'):
                        try:
                            # Parse do cookie
                            parts = line.strip().split('\t')
                            if len(parts) >= 7:
                                domain = parts[0]
                                flag = parts[1]
                                path = parts[2]
                                secure = parts[3]
                                expiration = parts[4]
                                name = parts[5]
                                value = parts[6]
                                
                                # Filtrar apenas cookies do YouTube
                                if not any(d in domain for d in ['.youtube.com', 'youtube.com', '.google.com', 'google.com']):
                                    continue
                                
                                # Formatar linha no padrão Netscape
                                # O formato é: domain, flag, path, secure, expiration, name, value
                                # domain: deve começar com . para subdomínios
                                if not domain.startswith('.'):
                                    domain = '.' + domain
                                
                                # secure: deve ser TRUE ou FALSE
                                secure = 'TRUE' if secure.lower() == 'true' else 'FALSE'
                                
                                # expiration: deve ser um timestamp Unix
                                try:
                                    expiration = str(int(float(expiration)))
                                except:
                                    expiration = '0'  # Sessão
                                
                                # Verificar se o cookie é válido
                                if not all([domain, path, name, value]):
                                    continue
                                
                                formatted_line = f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n"
                                temp_cookies.write(formatted_line)
                        except Exception as e:
                            print(f"[AVISO] Erro ao processar cookie: {line} - {str(e)}")
                            continue
                
                temp_cookies_path = temp_cookies.name
                print(f"[INFO] Arquivo de cookies criado em: {temp_cookies_path}")
                
                # Verificar se o arquivo foi criado corretamente
                with open(temp_cookies_path, 'r') as f:
                    content = f.read()
                    print(f"[DEBUG] Conteúdo do arquivo de cookies:\n{content}")
            
            # Configurações base do yt-dlp
            base_opts = [
                "--cookies", temp_cookies_path,
                "--socket-timeout", "30",
                "--retries", "10",
                "--fragment-retries", "10",
                "--extractor-retries", "10",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--http-chunk-size", "10M",
                "--no-check-certificates",
                "--no-warnings",
                "--ignore-errors",
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
                "--add-header", "X-YouTube-Client-Name: 1",
                "--add-header", "X-YouTube-Client-Version: 2.20240111.01.00",
                "--add-header", "X-YouTube-Device: cbr=Chrome&cbrver=120.0.0.0&c=WEB&cver=2.20240111.01.00&cplatform=DESKTOP",
                "--prefer-insecure",
                "--no-playlist",
                "--force-ipv4",
                "--geo-bypass",
                "--geo-bypass-country", "BR",
                "--extractor-args", "youtube:player_skip=js,webpage",
                "--extractor-args", "youtube:player_client=web",
                "--extractor-args", "youtube:player_skip=webpage",
                "--extractor-args", "youtube:player_client=android",
                "--extractor-args", "youtube:player_client=ios",
                "--extractor-args", "youtube:player_client=web_embedded",
                "--extractor-args", "youtube:player_client=android_embedded",
                "--extractor-args", "youtube:player_client=ios_embedded",
                "--extractor-args", "youtube:player_client=web_mobile",
                "--extractor-args", "youtube:player_client=android_mobile",
                "--extractor-args", "youtube:player_client=ios_mobile"
            ]
            
            # Tentar diferentes métodos de extração
            extraction_methods = [
                [],  # Método padrão
                ["--extractor-args", "youtube:player_client=android"],
                ["--extractor-args", "youtube:player_client=web"],
                ["--extractor-args", "youtube:player_client=ios"],
                ["--extractor-args", "youtube:player_client=android_embedded"],
                ["--extractor-args", "youtube:player_client=web_embedded"],
                ["--extractor-args", "youtube:player_client=ios_embedded"]
            ]
            
            video_info = None
            last_error = None
            cookies_refreshed = False
            
            for method in extraction_methods:
                try:
                    print(f"[INFO] Tentando método de extração: {method}")
                    info_cmd = ["yt-dlp"] + base_opts + method + ["--skip-download", "--dump-json", url]
                    print(f"[DEBUG] Comando executado: {' '.join(info_cmd)}")
                    
                    info_result = subprocess.run(
                        info_cmd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    print(f"[DEBUG] Saída do comando: {info_result.stdout}")
                    print(f"[DEBUG] Erro do comando: {info_result.stderr}")
                    
                    if info_result.returncode == 0:
                        video_info = json.loads(info_result.stdout)
                        print(f"[INFO] Método de extração bem-sucedido: {method}")
                        break
                    else:
                        last_error = info_result.stderr
                        print(f"[AVISO] Falha no método de extração {method}: {info_result.stderr}")
                        
                        # Verificar se é erro de autenticação/cookies
                        if is_auth_error(info_result.stderr):
                            if not cookies_refreshed:
                                print("[AVISO] Detectado erro de cookies, tentando atualizar...")
                                new_cookies = refresh_youtube_cookies()
                                if new_cookies:
                                    cookies_content = new_cookies
                                    cookies_refreshed = True
                                    # Recriar arquivo de cookies com novos cookies
                                    if temp_cookies_path and os.path.exists(temp_cookies_path):
                                        os.unlink(temp_cookies_path)
                                        
                                    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                                        # Adicionar cabeçalho Netscape
                                        temp_cookies.write("# Netscape HTTP Cookie File\n")
                                        temp_cookies.write("# https://curl.se/docs/http-cookies.html\n")
                                        temp_cookies.write("# This file was generated by OffTube! Edit at your own risk.\n\n")
                                        
                                        # Adicionar cookies
                                        for line in cookies_content.split('\n'):
                                            if line.strip() and not line.startswith('#'):
                                                temp_cookies.write(line + '\n')
                                                
                                        temp_cookies_path = temp_cookies.name
                                        
                                    print("[INFO] Tentando novamente com cookies atualizados...")
                                    
                                    # Atualizar cookies no comando
                                    base_opts[1] = temp_cookies_path
                                    
                                    continue  # Tentar novamente o mesmo método com novos cookies
                                
                except Exception as e:
                    last_error = str(e)
                    print(f"[AVISO] Falha no método de extração {method}: {str(e)}")
                    continue
            
            if not video_info:
                print(f"[ERRO] Todos os métodos de extração falharam. Último erro: {last_error}")
                return jsonify({
                    "error": "Não foi possível extrair informações do vídeo",
                    "details": last_error
                }), 500
                
            video_title = video_info.get("title", "Vídeo sem título")
            video_duration = video_info.get("duration", 0)
            
            # Baixar thumbnail
            print("[INFO] Baixando thumbnail...")
            thumbnail_cmd = ["yt-dlp"] + base_opts + [
                "--write-thumbnail",
                "--skip-download",
                "--convert-thumbnails", "jpg",
                "-o", os.path.join(THUMBNAIL_FOLDER, f"{video_id}"),
                url
            ]
            thumbnail_result = subprocess.run(
                thumbnail_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            thumbnail_url = None
            thumbnails = [f for f in os.listdir(THUMBNAIL_FOLDER) if f.startswith(video_id)]
            if thumbnails:
                thumbnail_url = f"/thumbnails/{thumbnails[0]}"
            
            # Baixar vídeo
            print("[INFO] Iniciando download do vídeo...")
            download_cmd = ["yt-dlp"] + base_opts + [
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "-o", output_template,
                url
            ]
            result = subprocess.run(
                download_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            print("[STDOUT]", result.stdout)
            print("[STDERR]", result.stderr)

            if result.returncode != 0:
                print(f"[ERRO] Falha no download: {result.stderr}")
                return jsonify({"error": f"Erro ao baixar vídeo: {result.stderr}"}), 500

            saved_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(video_id)]
            
            if not saved_files:
                print("[ERRO] Nenhum arquivo encontrado após download")
                return jsonify({"error": "Arquivo não encontrado após download"}), 500
                
            print(f"[INFO] Vídeo baixado com sucesso: {saved_files[0]}")
            
            return jsonify({
                "url": f"/videos/{saved_files[0]}",
                "id": video_id,
                "title": video_title,
                "thumbnail": thumbnail_url,
                "duration": video_duration
            })

        finally:
            if temp_cookies_path and os.path.exists(temp_cookies_path):
                os.unlink(temp_cookies_path)
                print("[INFO] Arquivo temporário de cookies removido")

    except subprocess.TimeoutExpired:
        print("[ERRO] Timeout ao processar vídeo")
        return jsonify({"error": "Timeout ao processar vídeo"}), 500
    except Exception as e:
        print(f"[ERRO] {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/videos/<filename>")
def serve_video(filename):
    return send_file(os.path.join(DOWNLOAD_FOLDER, filename))

@app.route("/thumbnails/<filename>")
def serve_thumbnail(filename):
    return send_file(os.path.join(THUMBNAIL_FOLDER, filename))

@app.route("/status")
def status():
    # Verificar se o yt-dlp está funcionando corretamente
    try:
        yt_dlp_version = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        ).stdout.strip()
        
        # Verificar se os cookies foram configurados corretamente
        cookies_configured = bool(os.environ.get("YOUTUBE_COOKIES"))
        youtube_credentials = bool(os.environ.get("YOUTUBE_EMAIL") and os.environ.get("YOUTUBE_PASSWORD"))
        
        return jsonify({
            "status": "online",
            "version": {
                "yt-dlp": yt_dlp_version
            },
            "cookies_configured": cookies_configured,
            "youtube_credentials_configured": youtube_credentials,
            "last_cookie_check": last_cookie_check.isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "degraded",
            "error": str(e),
            "cookies_configured": bool(os.environ.get("YOUTUBE_COOKIES"))
        })

@app.route("/refresh-cookies", methods=["POST"])
def manual_refresh_cookies():
    """Endpoint para atualizar cookies manualmente"""
    try:
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != os.environ.get("API_KEY"):
            return jsonify({"error": "Acesso não autorizado"}), 401
            
        cookies = refresh_youtube_cookies()
        if cookies:
            return jsonify({"status": "success", "message": "Cookies atualizados com sucesso"})
        else:
            return jsonify({"error": "Falha ao atualizar cookies"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Tentar atualizar yt-dlp no início
    update_ytdlp()
    
    # Verificar cookies no início
    cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
    if not cookies_content:
        print("[AVISO] Cookies não encontrados, tentando obter novos cookies...")
        refresh_youtube_cookies()
    
    # Iniciar thread de verificação de cookies
    cookie_checker = Thread(target=background_cookie_check)
    cookie_checker.daemon = True  # Encerrar quando o programa principal encerrar
    cookie_checker.start()
    
    # Iniciar aplicativo Flask
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))