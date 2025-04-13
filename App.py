from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import subprocess
import tempfile
import json
import re

app = Flask(__name__)
CORS(app)

# Pasta onde os vídeos serão salvos
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "videos")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Pasta para thumbnails
THUMBNAIL_FOLDER = os.path.join(os.getcwd(), "thumbnails")
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
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                temp_cookies.write(cookies_content)
                temp_cookies_path = temp_cookies.name
            
            print(f"[INFO] Arquivo temporário de cookies criado em: {temp_cookies_path}")
            
            # Obter informações do vídeo com timeout aumentado
            info_result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "--dump-json",
                "--socket-timeout", "30",  # Aumenta o timeout para 30 segundos
                url
            ], capture_output=True, text=True, timeout=60)  # Timeout total de 60 segundos
            
            if info_result.returncode != 0:
                print(f"[ERRO] Falha ao obter informações do vídeo: {info_result.stderr}")
                return jsonify({"error": f"Erro ao obter informações do vídeo: {info_result.stderr}"}), 500
                
            video_info = json.loads(info_result.stdout)
            video_title = video_info.get("title", "Vídeo sem título")
            video_duration = video_info.get("duration", 0)
            
            # Verificar se o vídeo está disponível
            if video_info.get("availability") != "public":
                print(f"[ERRO] Vídeo não disponível: {url}")
                return jsonify({"error": "Vídeo não está disponível"}), 400
            
            # Baixar thumbnail
            thumbnail_result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "--write-thumbnail",
                "--skip-download",
                "--convert-thumbnails", "jpg",
                "-o", os.path.join(THUMBNAIL_FOLDER, f"{video_id}"),
                url
            ], capture_output=True, text=True, timeout=30)
            
            thumbnail_url = None
            thumbnails = [f for f in os.listdir(THUMBNAIL_FOLDER) if f.startswith(video_id)]
            if thumbnails:
                thumbnail_url = f"/thumbnails/{thumbnails[0]}"
            
            # Baixar vídeo com formato específico
            result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",  # Prioriza MP4
                "--merge-output-format", "mp4",
                "--socket-timeout", "30",
                "-o", output_template,
                url
            ], capture_output=True, text=True, timeout=300)  # Timeout de 5 minutos para download

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

# Servir os vídeos
@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

# Servir thumbnails
@app.route("/thumbnails/<path:filename>")
def serve_thumbnail(filename):
    return send_from_directory(THUMBNAIL_FOLDER, filename)

# Listar os vídeos existentes
@app.route("/listar")
def listar_videos():
    videos = os.listdir(DOWNLOAD_FOLDER)
    return jsonify(videos)

# Verificar status da API
@app.route("/status")
def status():
    return jsonify({
        "status": "online",
        "videos_count": len(os.listdir(DOWNLOAD_FOLDER)),
        "cookies_configured": bool(os.environ.get("YOUTUBE_COOKIES"))
    })

@app.route("/videos/<filename>", methods=["DELETE"])
def delete_video(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(file_path):
        return jsonify({"error": "Arquivo não encontrado"}), 404

    try:
        os.remove(file_path)
        print(f"[INFO] Vídeo {filename} removido com sucesso.")
        return jsonify({"message": "Vídeo removido com sucesso"}), 200
    except Exception as e:
        print(f"[ERRO] Falha ao remover {filename}: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[INFO] Iniciando servidor na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=True)