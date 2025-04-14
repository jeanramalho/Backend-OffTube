from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os, uuid
from pathlib import Path
from pytube import YouTube
import logging
import requests
import time
import ssl

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuração para desabilitar verificação SSL temporariamente
ssl._create_default_https_context = ssl._create_unverified_context

DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

def download_video(url, video_id):
    try:
        logger.info(f"Iniciando download do vídeo: {url}")
        
        # Configurar headers para o pytube
        headers = {
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
        }

        # Criar objeto YouTube com headers personalizados
        yt = YouTube(
            url,
            use_oauth=False,
            allow_oauth_cache=True
        )
        
        # Configurar headers para o pytube
        yt.bypass_age_gate()
        
        # Obter informações do vídeo
        title = yt.title
        logger.info(f"Título do vídeo: {title}")
        
        # Baixar thumbnail primeiro
        thumbnail_url = yt.thumbnail_url
        response = requests.get(thumbnail_url, headers=headers)
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
