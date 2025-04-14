from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os, uuid
from pathlib import Path
import yt_dlp
import requests
from pytube import YouTube
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

def download_with_yt_dlp(url, video_id):
    ydl_opts = {
        'format': 'best[ext=mp4]',
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{video_id}.%(ext)s'),
        'writethumbnail': True,
        'convertthumbnails': 'jpg',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'nocheckcertificate': True,
        'extractor_args': {'youtube': {'player_client': ['android']}},
        'cookiesfrombrowser': ('chrome',),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Accept-Encoding': 'gzip,deflate',
            'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
        },
        'socket_timeout': 30,
        'retries': 3,
        'no_color': True,
        'ignoreerrors': True,
        'force_generic_extractor': False,
    }
    
    try:
        logger.info(f"Tentando baixar vídeo com yt-dlp: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            logger.info(f"Download concluído com sucesso: {info.get('title', 'Sem título')}")
            return True, info
    except Exception as e:
        logger.error(f"Erro ao baixar com yt-dlp: {str(e)}")
        return False, str(e)

def download_with_pytube(url, video_id):
    try:
        logger.info(f"Tentando baixar vídeo com pytube: {url}")
        yt = YouTube(
            url,
            use_oauth=False,
            allow_oauth_cache=True
        )
        
        # Configurar headers para o pytube
        yt.bypass_age_gate()
        
        video = yt.streams.filter(
            progressive=True,
            file_extension='mp4'
        ).order_by('resolution').desc().first()
        
        if video:
            logger.info(f"Stream encontrado: {video.resolution}")
            video.download(
                output_path=DOWNLOAD_FOLDER,
                filename=f"{video_id}.mp4"
            )
            
            # Baixar thumbnail
            thumbnail_url = yt.thumbnail_url
            response = requests.get(
                thumbnail_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            )
            
            if response.status_code == 200:
                with open(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg"), 'wb') as f:
                    f.write(response.content)
            
            logger.info(f"Download concluído com sucesso: {yt.title}")
            return True, {"title": yt.title}
        
        logger.error("Nenhum stream disponível")
        return False, "Nenhum stream disponível"
    except Exception as e:
        logger.error(f"Erro ao baixar com pytube: {str(e)}")
        return False, str(e)

@app.route("/download", methods=["POST"])
def download_video():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Dados JSON inválidos"}), 400
            
        url = data.get("url")
        if not url:
            return jsonify({"error": "URL é obrigatória"}), 400

        logger.info(f"Iniciando download para URL: {url}")
        video_id = str(uuid.uuid4())
        
        # Primeiro tenta com yt-dlp
        success, result = download_with_yt_dlp(url, video_id)
        
        # Se falhar, tenta com pytube
        if not success:
            logger.info("Tentando download com pytube como fallback")
            success, result = download_with_pytube(url, video_id)
        
        if not success:
            logger.error(f"Falha no download: {result}")
            return jsonify({
                "error": "Erro ao baixar vídeo",
                "details": str(result)
            }), 500

        video_filename = f"{video_id}.mp4"
        video_path = os.path.join(DOWNLOAD_FOLDER, video_filename)
        
        if not os.path.exists(video_path):
            logger.error(f"Arquivo não encontrado após download: {video_path}")
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
        logger.info(f"Download concluído com sucesso: {video_id}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Erro interno: {str(e)}")
        return jsonify({
            "error": "Erro interno",
            "details": str(e)
        }), 500

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
