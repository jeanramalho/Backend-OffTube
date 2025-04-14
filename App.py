import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging
import uuid
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re
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

def get_video_info(url):
    try:
        # Primeiro, obter a página de download
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Fazer a requisição inicial
        response = requests.post(
            'https://www.y2mate.com/mates/analyzeV2/ajax',
            headers=headers,
            data={
                'url': url,
                'q_auto': '0',
                'ajax': '1'
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Erro ao acessar y2mate: {response.status_code}")
            
        data = response.json()
        if not data.get('status') == 'success':
            raise Exception("Falha ao analisar vídeo")
            
        # Extrair informações do vídeo
        video_id = data.get('vid')
        title = data.get('title', '')
        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
        
        # Obter links de download
        response = requests.post(
            'https://www.y2mate.com/mates/convertV2/index',
            headers=headers,
            data={
                'vid': video_id,
                'k': data.get('links', {}).get('mp4', {}).get('auto', {}).get('k', '')
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Erro ao obter links: {response.status_code}")
            
        data = response.json()
        if not data.get('status') == 'success':
            raise Exception("Falha ao obter links de download")
            
        download_url = data.get('dlink', '')
        
        return {
            'title': title,
            'thumbnail_url': thumbnail_url,
            'download_url': download_url
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter informações do vídeo: {str(e)}")
        raise

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
        
        # Baixar o vídeo
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.y2mate.com/'
        }
        
        response = requests.get(video_info["download_url"], headers=headers, stream=True)
        if response.status_code == 200:
            video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
            with open(video_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True, {
                "title": video_info["title"]
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
        video_info = get_video_info(url)
        
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
