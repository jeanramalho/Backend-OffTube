from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import subprocess
import tempfile

app = Flask(__name__)
CORS(app)

# Pasta onde os vídeos serão salvos
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "videos")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

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
            return jsonify({"url": f"/videos/{saved_files[0]}"})

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[INFO] Iniciando servidor na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=True)