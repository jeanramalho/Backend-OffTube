from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os, uuid, subprocess
from pathlib import Path

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL é obrigatória"}), 400

    video_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.%(ext)s")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")

    cmd = [
    "python3", "-m", "yt_dlp",
    "--cookies", "cookies.txt",
    "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # User-Agent atualizado
    "--format", "bestvideo",
    "--merge-output-format", "mp4",
    "--output", output_template,
    "--write-thumbnail",
    "--convert-thumbnails", "jpg",
    "--no-playlist",
    "--quiet",
    "--verbose",  # Adicionado para obter logs detalhados
    "--no-check-certificate",  # Adicionado para contornar problemas de certificado (se necessário)
    url
]

    try:
        print(f"Executando: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return jsonify({"error": "Erro ao baixar vídeo", "details": result.stderr}), 500

        title = result.stdout.strip()
        video_filename = f"{video_id}.mp4"
        thumb_filename = f"{video_id}.jpg"
        response = {
            "success": True,
            "video_id": video_id,
            "title": title,
            "filename": video_filename,
            "download_url": f"/videos/{video_filename}",
            "thumbnail_url": f"/thumbnails/{thumb_filename}" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, thumb_filename)) else None
        }
        return jsonify(response)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Tempo limite excedido"}), 504
    except Exception as e:
        return jsonify({"error": "Erro interno", "details": str(e)}), 500

@app.route("/videos/<filename>", methods=["GET"])
def serve_video(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    return send_file(path) if os.path.exists(path) else (jsonify({"error": "Não encontrado"}), 404)

@app.route("/thumbnails/<filename>", methods=["GET"])
def serve_thumbnail(filename):
    path = os.path.join(THUMBNAIL_FOLDER, filename)
    return send_file(path) if os.path.exists(path) else (jsonify({"error": "Não encontrado"}), 404)

@app.route("/delete/<video_id>", methods=["DELETE"])
def delete_video(video_id):
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumb_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    errors = []

    for f in [video_path, thumb_path]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception as e:
            errors.append(str(e))

    if errors:
        return jsonify({"error": "Falha ao deletar arquivos", "details": errors}), 500
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
