import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging
import uuid
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re

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

# Lista de instâncias do Invidious (podemos alternar entre elas se uma falhar)
INVIDIOUS_INSTANCES = [
    "https://invidious.snopyta.org",
    "https://invidious.kavin.rocks",
    "https://vid.puffyan.us"
]

def get_video_info(video_id):
    for instance in INVIDIOUS_INSTANCES:
        try:
            url = f"{instance}/api/v1/videos/{video_id}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                return {
                    "title": data.get("title", ""),
                    "thumbnail_url": data.get("videoThumbnails", [{}])[0].get("url", ""),
                    "formats": data.get("formatStreams", [])
                }
        except Exception as e:
            logger.warning(f"Falha na instância {instance}: {str(e)}")
            continue
    raise Exception("Todas as instâncias falharam")

def download_video(video_id, video_info):
    try:
        logger.info(f"Iniciando download do vídeo: {video_id}")
        
        # Baixar thumbnail
        if video_info["thumbnail_url"]:
            response = requests.get(video_info["thumbnail_url"])
            if response.status_code == 200:
                with open(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg"), 'wb') as f:
                    f.write(response.content)
                logger.info("Thumbnail baixada com sucesso")
        
        # Encontrar o melhor formato de vídeo
        best_format = None
        for fmt in video_info["formats"]:
            if fmt.get("type", "").startswith("video/mp4"):
                if not best_format or fmt.get("quality", "") > best_format.get("quality", ""):
                    best_format = fmt
        
        if not best_format:
            raise Exception("Nenhum formato MP4 disponível")
        
        # Baixar o vídeo
        video_url = best_format["url"]
        response = requests.get(video_url, stream=True)
        if response.status_code == 200:
            video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
            with open(video_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True, {
                "title": video_info["title"],
                "quality": best_format.get("quality", "")
            }
        else:
            raise Exception(f"Erro ao baixar vídeo: {response.status_code}")
            
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

        # Extrair ID do vídeo
        video_id = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if not video_id:
            return jsonify({"error": "URL do YouTube inválida"}), 400
        video_id = video_id.group(1)
        
        # Obter informações do vídeo
        video_info = get_video_info(video_id)
        
        # Baixar vídeo
        success, result = download_video(video_id, video_info)
        
        if not success:
            return jsonify({
                "error": "Erro ao baixar vídeo",
                "details": str(result)
            }), 500

        return jsonify({
            "success": True,
            "video_id": video_id,
            "filename": f"{video_id}.mp4",
            "download_url": f"/videos/{video_id}.mp4",
            "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
            "title": result["title"]
        })
        
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
