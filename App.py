import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pytube import YouTube
import logging
import uuid
from pathlib import Path
import requests
import time

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configurar pastas
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

def download_video(url, video_id):
    try:
        logger.info(f"Iniciando download do vídeo: {url}")
        
        # Criar objeto YouTube
        yt = YouTube(url)
        
        # Obter informações do vídeo
        title = yt.title
        logger.info(f"Título do vídeo: {title}")
        
        # Baixar thumbnail
        thumbnail_url = yt.thumbnail_url
        response = requests.get(thumbnail_url)
        if response.status_code == 200:
            with open(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg"), 'wb') as f:
                f.write(response.content)
            logger.info("Thumbnail baixada com sucesso")
        
        # Tentar diferentes resoluções
        streams = yt.streams.filter(
            progressive=True,
            file_extension='mp4'
        ).order_by('resolution').desc()
        
        for stream in streams:
            try:
                logger.info(f"Tentando baixar em {stream.resolution}")
                stream.download(
                    output_path=DOWNLOAD_FOLDER,
                    filename=f"{video_id}.mp4"
                )
                logger.info(f"Download concluído em {stream.resolution}")
                return True, {
                    "title": title,
                    "resolution": stream.resolution
                }
            except Exception as e:
                logger.warning(f"Falha com resolução {stream.resolution}: {str(e)}")
                time.sleep(2)  # Esperar um pouco antes de tentar a próxima resolução
                continue
        
        return False, "Nenhuma resolução disponível para download"
        
    except Exception as e:
        logger.error(f"Erro ao baixar vídeo: {str(e)}")
        return False, str(e)

@app.route("/download", methods=["POST"])
def handle_download():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Dados JSON inválidos"}), 400
            
        url = data.get("url")
        if not url:
            return jsonify({"error": "URL é obrigatória"}), 400

        video_id = str(uuid.uuid4())
        success, result = download_video(url, video_id)
        
        if not success:
            return jsonify({
                "error": "Erro ao baixar vídeo",
                "details": str(result)
            }), 500

        video_filename = f"{video_id}.mp4"
        video_path = os.path.join(DOWNLOAD_FOLDER, video_filename)
        
        if not os.path.exists(video_path):
            return jsonify({
                "error": "Vídeo não foi baixado corretamente",
                "details": "Arquivo não encontrado após download"
            }), 500

        thumb_filename = f"{video_id}.jpg"
        response = {
            "success": True,
            "video_id": video_id,
            "filename": video_filename,
            "download_url": f"/videos/{video_filename}",
            "thumbnail_url": f"/thumbnails/{thumb_filename}" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, thumb_filename)) else None
        }
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Erro interno: {str(e)}")
        return jsonify({
            "error": "Erro interno",
            "details": str(e)
        }), 500

@app.route("/videos/<filename>", methods=["GET"])
def serve_video(filename):
    try:
        video_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(video_path):
            return jsonify({"error": "Vídeo não encontrado"}), 404
            
        return send_file(video_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Erro ao servir vídeo: {str(e)}")
        return jsonify({"error": "Erro ao servir vídeo"}), 500

@app.route("/thumbnails/<filename>", methods=["GET"])
def serve_thumbnail(filename):
    try:
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, filename)
        if not os.path.exists(thumbnail_path):
            return jsonify({"error": "Thumbnail não encontrada"}), 404
            
        return send_file(thumbnail_path)
    except Exception as e:
        logger.error(f"Erro ao servir thumbnail: {str(e)}")
        return jsonify({"error": "Erro ao servir thumbnail"}), 500

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
