from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import subprocess
import json
import uuid
import re
import tempfile
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configurações
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"

# Criar pastas se não existirem
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        video_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.%(ext)s")
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")

        print(f"[INFO] Baixando vídeo: {url}")
        print(f"[INFO] Caminho de saída: {output_template}")

        # Verificar se a URL é válida
        if not re.match(r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/', url):
            print(f"[ERRO] URL inválida: {url}")
            return jsonify({"error": "URL do YouTube inválida"}), 400

        # Criar arquivo temporário de cookies
        cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
        
        if not cookies_content:
            print("[AVISO] Variável de ambiente YOUTUBE_COOKIES não encontrada")
            return jsonify({"error": "Cookies do YouTube não configurados no servidor"}), 500
            
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
                                if not any(d in domain for d in ['.youtube.com', 'youtube.com']):
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
                                print(f"[DEBUG] Cookie formatado: {formatted_line.strip()}")
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
                "--add-header", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
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
                "--add-header", "X-YouTube-Identity-Token: ",
                "--add-header", "X-YouTube-Page-CL: 0",
                "--add-header", "X-YouTube-Page-Label: 0",
                "--add-header", "X-YouTube-Utc-Offset: -180",
                "--add-header", "X-YouTube-Variants-Checksum: ",
                "--add-header", "X-YouTube-Time-Zone: America/Sao_Paulo",
                "--add-header", "X-YouTube-Ad-Signals: ",
                "--add-header", "X-YouTube-Device-Latency: ",
                "--add-header", "X-YouTube-Initial-Player-Response: ",
                "--add-header", "X-YouTube-Initial-Data: ",
                "--add-header", "X-YouTube-Client-Data: ",
                "--add-header", "X-YouTube-Client-Name: 1",
                "--add-header", "X-YouTube-Client-Version: 2.20240111.01.00",
                "--add-header", "X-YouTube-Device: cbr=Chrome&cbrver=120.0.0.0&c=WEB&cver=2.20240111.01.00&cplatform=DESKTOP",
                "--add-header", "X-YouTube-Identity-Token: ",
                "--add-header", "X-YouTube-Page-CL: 0",
                "--add-header", "X-YouTube-Page-Label: 0",
                "--add-header", "X-YouTube-Utc-Offset: -180",
                "--add-header", "X-YouTube-Variants-Checksum: ",
                "--add-header", "X-YouTube-Time-Zone: America/Sao_Paulo",
                "--add-header", "X-YouTube-Ad-Signals: ",
                "--add-header", "X-YouTube-Device-Latency: ",
                "--add-header", "X-YouTube-Initial-Player-Response: ",
                "--add-header", "X-YouTube-Initial-Data: ",
                "--add-header", "X-YouTube-Client-Data: ",
                "--prefer-insecure",
                "--no-playlist",
                "--force-ipv4",
                "--geo-bypass",
                "--geo-bypass-country", "BR",
                "--extractor-args", "youtube:player_skip=js,webpage",
                "--extractor-args", "youtube:player_client=web",
                "--extractor-args", "youtube:player_skip=webpage",
                "--extractor-args", "youtube:player_skip=js",
                "--extractor-args", "youtube:player_skip=webpage,js",
                "--extractor-args", "youtube:player_client=web;player_skip=js,webpage",
                "--extractor-args", "youtube:player_client=android;player_skip=js,webpage",
                "--extractor-args", "youtube:player_client=ios;player_skip=js,webpage",
                "--extractor-args", "youtube:player_client=web;player_skip=js,webpage;player_skip=webpage,js",
                "--extractor-args", "youtube:player_client=android;player_skip=js,webpage;player_skip=webpage,js",
                "--extractor-args", "youtube:player_client=ios;player_skip=js,webpage;player_skip=webpage,js",
                "--extractor-args", "youtube:player_client=web;player_skip=js,webpage;player_skip=webpage,js;player_skip=js",
                "--extractor-args", "youtube:player_client=android;player_skip=js,webpage;player_skip=webpage,js;player_skip=js",
                "--extractor-args", "youtube:player_client=ios;player_skip=js,webpage;player_skip=webpage,js;player_skip=js"
            ]
            
            # Tentar diferentes métodos de extração
            extraction_methods = [
                [],  # Método padrão
                ["--extractor-args", "youtube:player_client=android"],
                ["--extractor-args", "youtube:player_client=web"],
                ["--extractor-args", "youtube:player_client=ios"],
                ["--extractor-args", "youtube:player_client=android_embedded"],
                ["--extractor-args", "youtube:player_client=web_embedded"],
                ["--extractor-args", "youtube:player_client=ios_embedded"],
                ["--extractor-args", "youtube:player_skip=js,webpage"],
                ["--extractor-args", "youtube:player_skip=webpage"],
                ["--extractor-args", "youtube:player_skip=js"],
                ["--extractor-args", "youtube:player_skip=webpage,js"],
                ["--extractor-args", "youtube:player_client=web;player_skip=js,webpage"],
                ["--extractor-args", "youtube:player_client=android;player_skip=js,webpage"],
                ["--extractor-args", "youtube:player_client=ios;player_skip=js,webpage"],
                ["--extractor-args", "youtube:player_client=web;player_skip=js,webpage;player_skip=webpage,js"],
                ["--extractor-args", "youtube:player_client=android;player_skip=js,webpage;player_skip=webpage,js"],
                ["--extractor-args", "youtube:player_client=ios;player_skip=js,webpage;player_skip=webpage,js"],
                ["--extractor-args", "youtube:player_client=web;player_skip=js,webpage;player_skip=webpage,js;player_skip=js"],
                ["--extractor-args", "youtube:player_client=android;player_skip=js,webpage;player_skip=webpage,js;player_skip=js"],
                ["--extractor-args", "youtube:player_client=ios;player_skip=js,webpage;player_skip=webpage,js;player_skip=js"]
            ]
            
            video_info = None
            last_error = None
            
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
    return jsonify({"status": "online", "cookies_configured": bool(os.environ.get("YOUTUBE_COOKIES"))})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))