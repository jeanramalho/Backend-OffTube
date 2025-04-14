import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import logging
import uuid
from pathlib import Path
import time
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configurar pastas
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

def get_ydl_opts(video_id):
    return {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{video_id}.%(ext)s'),
        'writesubtitles': False,
        'writeautomaticsub': False,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        },
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'extractor_retries': 3,
        'no_check_certificate': True,
        'prefer_insecure': True,
        'http_chunk_size': 10485760,  # 10MB
        'continuedl': True,
        'noprogress': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'geo_bypass_ip_block': '0.0.0.0/0',
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls'],
                'player_skip': ['js', 'configs', 'webpage']
            }
        }
    }

def download_video(url, video_id):
    try:
        logger.info(f"Iniciando download do vídeo: {url}")
        
        ydl_opts = get_ydl_opts(video_id)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Primeiro, obter informações do vídeo
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '')
            thumbnail_url = info.get('thumbnail', '')
            
            logger.info(f"Título do vídeo: {title}")
            
            # Baixar thumbnail
            if thumbnail_url:
                thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
                ydl.download([thumbnail_url])
                logger.info("Thumbnail baixada com sucesso")
            
            # Agora baixar o vídeo
            ydl.download([url])
            
            # Verificar se o arquivo foi baixado
            video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
            if not os.path.exists(video_path):
                raise Exception("Arquivo de vídeo não foi criado após o download")
            
            return True, {
                "title": title,
                "thumbnail_url": f"/thumbnails/{video_id}.jpg" if thumbnail_url else None
            }
            
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

        return jsonify({
            "success": True,
            "video_id": video_id,
            "filename": f"{video_id}.mp4",
            "download_url": f"/videos/{video_id}.mp4",
            "thumbnail_url": result.get("thumbnail_url")
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
