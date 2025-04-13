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
        # Usa %(ext)s para deixar o yt-dlp decidir a extensão correta (ex: .webm, .mp4)
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.%(ext)s")
        
        # Caminho para o thumbnail
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")

        print(f"[INFO] Baixando vídeo: {url}")
        print(f"[INFO] Caminho de saída: {output_template}")

        # Criar arquivo temporário de cookies a partir da variável de ambiente
        cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
        
        if not cookies_content:
            print("[AVISO] Variável de ambiente YOUTUBE_COOKIES não encontrada")
            return jsonify({"error": "Cookies do YouTube não configurados no servidor"}), 500
            
        # Criar arquivo temporário para armazenar os cookies
        temp_cookies_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                temp_cookies.write(cookies_content)
                temp_cookies_path = temp_cookies.name
            
            print(f"[INFO] Arquivo temporário de cookies criado em: {temp_cookies_path}")
            
            # Primeiro, obtenha os metadados do vídeo
            info_result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "--dump-json",
                url
            ], capture_output=True, text=True)
            
            if info_result.returncode != 0:
                return jsonify({"error": "Erro ao obter informações do vídeo"}), 500
                
            video_info = json.loads(info_result.stdout)
            video_title = video_info.get("title", "Vídeo sem título")
            video_duration = video_info.get("duration", 0)
            
            # Baixe o thumbnail
            thumbnail_result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "--write-thumbnail",
                "--skip-download",
                "--convert-thumbnails", "jpg",
                "-o", os.path.join(THUMBNAIL_FOLDER, f"{video_id}"),
                url
            ], capture_output=True, text=True)
            
            # Localizar o thumbnail baixado
            thumbnail_url = None
            thumbnails = [f for f in os.listdir(THUMBNAIL_FOLDER) if f.startswith(video_id)]
            if thumbnails:
                thumbnail_url = f"/thumbnails/{thumbnails[0]}"
            
            # Agora, baixe o vídeo
            result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "-f", "bestvideo+bestaudio",
                "--merge-output-format", "mp4",  # Garante saída em mp4
                "-o", output_template,
                url
            ], capture_output=True, text=True)

            print("[STDOUT]", result.stdout)
            print("[STDERR]", result.stderr)
            
            # Remover o arquivo temporário de cookies após o uso
            if os.path.exists(temp_cookies_path):
                os.unlink(temp_cookies_path)
                print("[INFO] Arquivo temporário de cookies removido")
                temp_cookies_path = None

            if result.returncode != 0:
                return jsonify({"error": result.stderr}), 500

            # Após o download, identifica o arquivo salvo
            saved_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(video_id)]
            
            if not saved_files:
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
            # Garantir que o arquivo temporário seja removido em caso de erro
            if temp_cookies_path and os.path.exists(temp_cookies_path):
                os.unlink(temp_cookies_path)
                print("[INFO] Arquivo temporário de cookies removido (finally)")

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