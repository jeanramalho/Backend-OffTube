from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
import re
import requests
from pytube import YouTube
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Pastas onde os vídeos e thumbnails serão armazenados
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"

# Cria as pastas caso não existam
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

def sanitize_filename(filename: str) -> str:
    """Remove caracteres inválidos para nomes de arquivos."""
    return re.sub(r'[\\/*?:"<>|]', "_", filename)

@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL é obrigatória"}), 400

    # Verifica se a URL parece ser do YouTube
    if not any(domain in url for domain in ["youtube.com", "youtu.be"]):
        return jsonify({"error": "URL inválida. Certifique-se que é do YouTube"}), 400

    try:
        yt = YouTube(url)
    except Exception as e:
        return jsonify({"error": "Falha ao acessar o vídeo", "details": str(e)}), 500

    try:
        # Seleciona a stream com maior resolução (progressive para ter áudio e vídeo juntos)
        stream = yt.streams.get_highest_resolution()
        if not stream:
            return jsonify({"error": "Nenhuma stream encontrada para esse vídeo"}), 500

        # Gerar um ID único que será usado para o arquivo e thumbnail
        video_id = str(uuid.uuid4())
        # Opcionalmente podemos usar o title do vídeo, mas é mais seguro gerar um ID
        filename = f"{video_id}.mp4"
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)

        # Realiza o download do vídeo
        stream.download(output_path=DOWNLOAD_FOLDER, filename=filename)

        # Baixar a thumbnail se disponível
        thumbnail_url = yt.thumbnail_url
        thumbnail_filename = f"{video_id}.jpg"
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, thumbnail_filename)
        if thumbnail_url:
            thumb_response = requests.get(thumbnail_url, stream=True)
            if thumb_response.status_code == 200:
                with open(thumbnail_path, "wb") as f:
                    for chunk in thumb_response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)

        response = {
            "success": True,
            "video_id": video_id,
            "title": yt.title,
            "filename": filename,
            "download_url": f"/videos/{filename}",
            "thumbnail_url": f"/thumbnails/{thumbnail_filename}" if os.path.exists(thumbnail_path) else None,
            "duration": yt.length  # duração em segundos
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": "Erro ao processar o download", "details": str(e)}), 500

@app.route("/videos/<filename>", methods=["GET"])
def serve_video(filename):
    video_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(video_path):
        return send_file(video_path)
    return jsonify({"error": "Vídeo não encontrado"}), 404

@app.route("/thumbnails/<filename>", methods=["GET"])
def serve_thumbnail(filename):
    thumb_path = os.path.join(THUMBNAIL_FOLDER, filename)
    if os.path.exists(thumb_path):
        return send_file(thumb_path)
    return jsonify({"error": "Thumbnail não encontrada"}), 404

@app.route("/delete/<video_id>", methods=["DELETE"])
def delete_video(video_id):
    """
    Deleta o vídeo e a thumbnail usando o video_id (nome do arquivo gerado no download)
    """
    video_file = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumb_file = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    
    errors = []
    # Tenta remover o vídeo
    if os.path.exists(video_file):
        try:
            os.remove(video_file)
        except Exception as e:
            errors.append(f"Erro ao deletar vídeo: {str(e)}")
    else:
        errors.append("Arquivo de vídeo não encontrado")
    
    # Tenta remover a thumbnail se existir
    if os.path.exists(thumb_file):
        try:
            os.remove(thumb_file)
        except Exception as e:
            errors.append(f"Erro ao deletar thumbnail: {str(e)}")
    
    if errors:
        return jsonify({"error": "Problemas durante a remoção", "details": errors}), 500
    return jsonify({"success": True, "message": "Vídeo e thumbnail removidos."})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
