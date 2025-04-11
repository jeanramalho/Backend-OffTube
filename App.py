from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import subprocess

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

        result = subprocess.run([
            "yt-dlp",
            "--cookies", "cookies.txt",
            "-f", "bestvideo+bestaudio",
            "-o", output_template,
            url
        ], capture_output=True, text=True)

        print("[STDOUT]", result.stdout)
        print("[STDERR]", result.stderr)

        if result.returncode != 0:
            return jsonify({"error": result.stderr}), 500

        # Após o download, identifica o arquivo salvo
        for filename in os.listdir(DOWNLOAD_FOLDER):
            if filename.startswith(video_id):
                return jsonify({"url": f"/videos/{filename}"})

        return jsonify({"error": "Arquivo não encontrado após download"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Servir os vídeos
@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

# Listar os vídeos existentes
@app.route("/listar")
def listar_videos():
    return jsonify(os.listdir(DOWNLOAD_FOLDER))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=True)
