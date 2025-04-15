import os
import re
import logging
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pathlib import Path
from dotenv import load_dotenv

# Carregar variáveis de ambiente, se houver
load_dotenv()

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Diretórios para armazenar vídeos e thumbnails
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

def extract_youtube_id(url):
    """Extrai o ID do vídeo a partir de uma URL do YouTube."""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    m = re.search(pattern, url)
    return m.group(1) if m else None

def get_video_info_option1(url):
    """
    Obtém informações do vídeo via RapidAPI Option1.
    Endpoint: youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com
    Retorna um dicionário com title, thumbnail_url, download_url, video_id e quality.
    Prioriza stream 720p ou a melhor abaixo.
    """
    api_url = "https://youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com/videodownload.php"
    headers = {
        "x-rapidapi-key": "e675e37fe3msh28737c9013eca79p1ed09cjsn7b8a4c446ef0",
        "x-rapidapi-host": "youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com"
    }
    params = {"url": url}
    resp = requests.get(api_url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or len(data) == 0:
        raise Exception("Option1: Resposta em formato inválido.")
    item = data[0]
    if "urls" not in item or not item["urls"]:
        raise Exception("Option1: Nenhuma URL de download encontrada.")
    urls = item["urls"]
    target = 720
    chosen_url = None
    chosen_quality = 0
    for entry in urls:
        if entry.get("extension") != "mp4" and entry.get("name") != "MP4":
            continue
        quality_str = entry.get("quality") or entry.get("subName")
        if not quality_str:
            continue
        try:
            quality = int(re.sub(r"\D", "", quality_str))
        except Exception:
            continue
        logger.info(f"Option1: Encontrou stream com qualidade {quality}p")
        if quality == target:
            chosen_url = entry["url"]
            chosen_quality = target
            break
        elif quality < target and quality > chosen_quality:
            chosen_quality = quality
            chosen_url = entry["url"]
    if not chosen_url:
        raise Exception("Option1: Nenhuma URL de download válida encontrada.")
    title = item.get("title") or f"video_{extract_youtube_id(url)}"
    thumb = item.get("pictureUrl") or f"https://i.ytimg.com/vi/{extract_youtube_id(url)}/maxresdefault.jpg"
    return {
        "title": title,
        "thumbnail_url": thumb,
        "download_url": chosen_url,
        "video_id": extract_youtube_id(url),
        "quality": chosen_quality
    }

def get_video_info_option2(url):
    """
    Obtém informações do vídeo via RapidAPI Option2.
    Endpoint: youtube-media-downloader.p.rapidapi.com
    Retorna um dicionário com title, thumbnail_url, download_url, video_id e quality.
    """
    video_id = extract_youtube_id(url)
    if not video_id:
        raise Exception("Option2: URL inválida.")
    api_url = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"
    headers = {
        "x-rapidapi-key": "e675e37fe3msh28737c9013eca79p1ed09cjsn7b8a4c446ef0",
        "x-rapidapi-host": "youtube-media-downloader.p.rapidapi.com"
    }
    params = {"videoId": video_id}
    resp = requests.get(api_url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("status"):
        raise Exception("Option2: API retornou erro.")
    videos = data.get("videos", {}).get("items", [])
    if not videos:
        raise Exception("Option2: Nenhuma stream encontrada.")
    target = 720
    chosen_url = None
    chosen_quality = 0
    for vid in videos:
        quality_str = vid.get("quality")
        if not quality_str:
            continue
        try:
            quality = int(re.sub(r"\D", "", quality_str))
        except Exception:
            continue
        logger.info(f"Option2: Encontrou stream com qualidade {quality}p")
        if quality == target:
            chosen_url = vid["url"]
            chosen_quality = target
            break
        elif quality < target and quality > chosen_quality:
            chosen_quality = quality
            chosen_url = vid["url"]
    if not chosen_url:
        raise Exception("Option2: Nenhuma URL de download válida encontrada.")
    title = data.get("title") or f"video_{video_id}"
    thumbs = data.get("thumbnails", [])
    thumb_url = thumbs[0]["url"] if thumbs else f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    return {
        "title": title,
        "thumbnail_url": thumb_url,
        "download_url": chosen_url,
        "video_id": video_id,
        "quality": chosen_quality
    }

def download_from_url(download_url, video_id, title, referer_url):
    """
    Tenta baixar o arquivo utilizando a URL obtida via RapidAPI.
    Utiliza uma sessão de requests com headers que simulam uma requisição real.
    O header Referer é definido como a URL completa do vídeo do YouTube.
    """
    logger.info(f"Download iniciando (primeiros 100 caracteres): {download_url[:100]}...")
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer_url,
        "Origin": "https://www.youtube.com",
        "Accept": "*/*",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "video",
        "Range": "bytes=0-"
    })
    try:
        resp = session.get(download_url, stream=True, allow_redirects=True, timeout=60)
        resp.raise_for_status()
        with open(video_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            logger.info(f"Download concluído (tamanho: {os.path.getsize(video_path)/1024/1024:.2f} MB)")
            # Tenta baixar a thumbnail padrão
            try:
                thumb_resp = session.get(f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg", timeout=30)
                if thumb_resp.status_code != 200:
                    thumb_resp = session.get(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", timeout=30)
                if thumb_resp.status_code == 200:
                    with open(thumbnail_path, "wb") as f:
                        f.write(thumb_resp.content)
                    logger.info("Thumbnail baixada com sucesso.")
            except Exception as e:
                logger.warning(f"Erro ao baixar thumbnail: {str(e)}")
            return True, title
        else:
            raise Exception("Arquivo baixado está vazio ou inexistente")
    except Exception as e:
        logger.error(f"Erro no download: {str(e)}")
        return False, str(e)

@app.route("/download", methods=["POST"])
def handle_download():
    try:
        if not request.is_json:
            return jsonify({"error": "Requisição deve conter JSON válido"}), 400
        data = request.get_json()
        url = data.get("url")
        if not url:
            return jsonify({"error": "URL é obrigatória"}), 400
        video_id = extract_youtube_id(url)
        if not video_id:
            return jsonify({"error": "URL do YouTube inválida"}), 400

        # Se o vídeo já estiver salvo, retorna os dados
        video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            try:
                yt_info_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                info_resp = requests.get(yt_info_url, timeout=10)
                title = info_resp.json().get("title", f"video_{video_id}") if info_resp.status_code == 200 else f"video_{video_id}"
            except:
                title = f"video_{video_id}"
            return jsonify({
                "success": True,
                "message": "Vídeo já existe no sistema",
                "video_id": video_id,
                "filename": f"{video_id}.mp4",
                "download_url": f"/videos/{video_id}.mp4",
                "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
                "title": title
            })

        # Tenta obter as informações via Option1; se a qualidade for inferior a 720, tenta Option2 para ver se há melhor opção
        info = None
        try:
            logger.info("Tentando RapidAPI Option1...")
            info = get_video_info_option1(url)
            logger.info(f"Option1 retornou qualidade {info.get('quality', 0)}p")
        except Exception as e:
            logger.warning(f"RapidAPI Option1 falhou: {str(e)}")
        if info and info.get("quality", 0) < 720:
            try:
                logger.info("Option1 retornou qualidade abaixo de 720p; tentando Option2...")
                info2 = get_video_info_option2(url)
                q2 = info2.get("quality", 0)
                logger.info(f"Option2 retornou qualidade {q2}p")
                if q2 >= 720:
                    info = info2
                    logger.info("Utilizando dados da Option2 (qualidade >= 720p).")
                else:
                    logger.info("Option2 também retornou qualidade inferior; mantendo Option1.")
            except Exception as e:
                logger.warning(f"Option2 falhou: {str(e)}")
        if not info:
            return jsonify({"error": "Todos os métodos de download falharam",
                            "details": "Não foi possível obter informações válidas do vídeo via RapidAPI"}), 500

        download_url = info.get("download_url")
        title = info.get("title", f"video_{video_id}")
        thumb_url = info.get("thumbnail_url")
        # Usa a URL completa do vídeo como Referer
        referer_url = url
        success, result = download_from_url(download_url, video_id, title, referer_url)
        if not success:
            logger.warning(f"Download via Option1/Option2 falhou: {result}")
            return jsonify({"error": "Download falhou", "details": result}), 500

        # Tenta baixar a thumbnail informada pela API, se disponível, como fallback
        thumb_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
        try:
            if thumb_url:
                r = requests.get(thumb_url, timeout=30)
                if r.status_code == 200:
                    with open(thumb_path, "wb") as f:
                        f.write(r.content)
                    logger.info("Thumbnail baixada a partir das informações da API.")
        except Exception as e:
            logger.warning(f"Erro ao baixar thumbnail da API: {str(e)}")
        return jsonify({
            "success": True,
            "video_id": video_id,
            "filename": f"{video_id}.mp4",
            "download_url": f"/videos/{video_id}.mp4",
            "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(thumb_path) else None,
            "title": title
        })
    except Exception as e:
        logger.error(f"Erro interno: {str(e)}")
        return jsonify({"error": "Erro interno", "details": str(e)}), 500

@app.route("/videos/<filename>", methods=["GET"])
def serve_video(filename):
    try:
        path = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(path):
            return jsonify({"error": "Vídeo não encontrado"}), 404
        return send_file(path, as_attachment=True)
    except Exception as e:
        logger.error(f"Erro ao servir vídeo: {str(e)}")
        return jsonify({"error": "Erro ao servir vídeo"}), 500

@app.route("/thumbnails/<filename>", methods=["GET"])
def serve_thumbnail(filename):
    try:
        path = os.path.join(THUMBNAIL_FOLDER, filename)
        if not os.path.exists(path):
            return jsonify({"error": "Thumbnail não encontrada"}), 404
        return send_file(path)
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
