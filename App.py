import os
import re
import logging
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pathlib import Path
from dotenv import load_dotenv
import time
import random

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

# Lista de user agents para alternar
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
]

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

def get_video_info_option3(url):
    """
    Obtém informações do vídeo via RapidAPI Option3.
    Endpoint: youtube-video-download-info.p.rapidapi.com
    Retorna um dicionário com title, thumbnail_url, download_url, video_id e quality.
    """
    video_id = extract_youtube_id(url)
    if not video_id:
        raise Exception("Option3: URL inválida.")
    api_url = "https://youtube-video-download-info.p.rapidapi.com/dl"
    headers = {
        "x-rapidapi-key": "e675e37fe3msh28737c9013eca79p1ed09cjsn7b8a4c446ef0",
        "x-rapidapi-host": "youtube-video-download-info.p.rapidapi.com"
    }
    params = {"id": video_id}
    resp = requests.get(api_url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("status") == "ok":
        raise Exception("Option3: API retornou erro.")
    
    formats = data.get("link", [])
    if not formats:
        raise Exception("Option3: Nenhuma stream encontrada.")
    
    target = 720
    chosen_url = None
    chosen_quality = 0
    
    for fmt in formats:
        q = fmt.get("quality")
        if not q or not isinstance(q, str):
            continue
        
        # Tenta extrair a qualidade do formato (ex: "720p", "360p")
        try:
            quality = int(re.sub(r"\D", "", q))
        except Exception:
            continue
            
        logger.info(f"Option3: Encontrou stream com qualidade {quality}p")
        
        # Verifica se é mp4
        if "mp4" not in fmt.get("format", "").lower() and "mp4" not in fmt.get("type", "").lower():
            continue
            
        if quality == target:
            chosen_url = fmt["url"]
            chosen_quality = target
            break
        elif quality < target and quality > chosen_quality:
            chosen_quality = quality
            chosen_url = fmt["url"]
    
    if not chosen_url:
        raise Exception("Option3: Nenhuma URL de download válida encontrada.")
    
    title = data.get("title") or f"video_{video_id}"
    thumb_url = data.get("thumb") or f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    
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
    Implementa várias estratégias de retry e alternância de user agents.
    """
    logger.info(f"Download iniciando (primeiros 100 caracteres): {download_url[:100]}...")
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    
    # Tentativas de download com diferentes configurações
    attempts = 3
    for attempt in range(attempts):
        try:
            # Cria uma nova sessão para cada tentativa
            session = requests.Session()
            
            # Alterna entre diferentes User Agents
            user_agent = random.choice(USER_AGENTS)
            
            # Adiciona variação aos headers para cada tentativa
            headers = {
                "User-Agent": user_agent,
                "Referer": referer_url,
                "Origin": "https://www.youtube.com",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "video",
                "Sec-Fetch-Site": "cross-site",
                "Range": "bytes=0-",
                "DNT": "1"
            }
            
            # Adiciona cookies aleatórios para simular comportamento de navegador
            if attempt > 0:
                headers["Cookie"] = f"YSC={random.randint(100000, 999999)}; VISITOR_INFO1_LIVE={random.randint(100000, 999999)}"
                
            session.headers.update(headers)
            
            # Pequena pausa entre tentativas
            if attempt > 0:
                time.sleep(2)
                logger.info(f"Tentativa {attempt+1} de {attempts} com User-Agent: {user_agent[:30]}...")
            
            # Executa o download com streaming para evitar carregar todo o arquivo na memória
            resp = session.get(download_url, stream=True, allow_redirects=True, timeout=60)
            resp.raise_for_status()
            
            # Verifica se o Content-Type é de vídeo
            content_type = resp.headers.get('Content-Type', '')
            if not content_type.startswith('video/') and not 'audio/' in content_type:
                logger.warning(f"Conteúdo não parece ser vídeo: {content_type}")
                if attempt == attempts - 1:  # Na última tentativa, aceitamos qualquer conteúdo
                    logger.warning("Última tentativa: aceitando conteúdo mesmo sem verificação de tipo")
                else:
                    continue
            
            # Salva o arquivo em partes
            with open(video_path, "wb") as f:
                downloaded = 0
                chunk_size = 8192
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Log de progresso a cada 5MB
                        if downloaded % (5 * 1024 * 1024) < chunk_size:
                            logger.info(f"Download em progresso: {downloaded / (1024 * 1024):.2f} MB")
            
            # Verifica se o arquivo foi baixado corretamente
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                logger.info(f"Download concluído (tamanho: {os.path.getsize(video_path)/1024/1024:.2f} MB)")
                
                # Tenta baixar a thumbnail
                try:
                    thumb_session = requests.Session()
                    thumb_session.headers.update({
                        "User-Agent": random.choice(USER_AGENTS),
                        "Referer": "https://www.youtube.com/"
                    })
                    
                    # Tenta várias resoluções de thumbnail
                    thumb_options = [
                        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                        f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                        f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg"
                    ]
                    
                    for thumb_url in thumb_options:
                        try:
                            thumb_resp = thumb_session.get(thumb_url, timeout=15)
                            if thumb_resp.status_code == 200:
                                with open(thumbnail_path, "wb") as f:
                                    f.write(thumb_resp.content)
                                logger.info(f"Thumbnail baixada com sucesso de {thumb_url}")
                                break
                        except Exception as e:
                            logger.warning(f"Erro ao baixar thumbnail {thumb_url}: {str(e)}")
                            continue
                except Exception as e:
                    logger.warning(f"Erro geral ao baixar thumbnail: {str(e)}")
                
                return True, title
            else:
                logger.warning(f"Tentativa {attempt+1}: Arquivo baixado está vazio ou inexistente")
                if os.path.exists(video_path):
                    os.remove(video_path)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Tentativa {attempt+1}: Erro de requisição: {str(e)}")
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception as e:
            logger.warning(f"Tentativa {attempt+1}: Erro geral: {str(e)}")
            if os.path.exists(video_path):
                os.remove(video_path)
    
    logger.error("Todas as tentativas de download falharam")
    return False, "Todas as tentativas de download falharam após múltiplas estratégias"

def try_all_download_options(url):
    """
    Tenta todas as opções de download em sequência até encontrar uma que funcione.
    Retorna as informações do vídeo ou levanta uma exceção.
    """
    errors = []
    
    # Tentativa 1: Option1
    try:
        logger.info("Tentando RapidAPI Option1...")
        info = get_video_info_option1(url)
        logger.info(f"Option1 retornou qualidade {info.get('quality', 0)}p")
        return info
    except Exception as e:
        msg = f"RapidAPI Option1 falhou: {str(e)}"
        logger.warning(msg)
        errors.append(msg)
    
    # Tentativa 2: Option2
    try:
        logger.info("Tentando RapidAPI Option2...")
        info = get_video_info_option2(url)
        logger.info(f"Option2 retornou qualidade {info.get('quality', 0)}p")
        return info
    except Exception as e:
        msg = f"RapidAPI Option2 falhou: {str(e)}"
        logger.warning(msg)
        errors.append(msg)
    
    # Tentativa 3: Option3
    try:
        logger.info("Tentando RapidAPI Option3...")
        info = get_video_info_option3(url)
        logger.info(f"Option3 retornou qualidade {info.get('quality', 0)}p")
        return info
    except Exception as e:
        msg = f"RapidAPI Option3 falhou: {str(e)}"
        logger.warning(msg)
        errors.append(msg)
    
    # Se chegou aqui, todas as opções falharam
    raise Exception(f"Todas as APIs falharam: {'; '.join(errors)}")

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

        # Estratégia 1: Tenta obter informações de todas as APIs em sequência
        try:
            info = try_all_download_options(url)
        except Exception as e:
            return jsonify({"error": "Falha na obtenção de informações do vídeo", "details": str(e)}), 500

        # Tentativa de download
        download_url = info.get("download_url")
        title = info.get("title", f"video_{video_id}")
        thumb_url = info.get("thumbnail_url")
        referer_url = url

        # Tenta fazer o download com a URL obtida
        success, result = download_from_url(download_url, video_id, title, referer_url)
        if not success:
            logger.warning(f"Download falhou: {result}")
            return jsonify({"error": "Download falhou", "details": result}), 500

        # Tenta baixar a thumbnail informada pela API, se disponível, como fallback
        thumb_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
        try:
            if thumb_url and not os.path.exists(thumb_path):
                r = requests.get(thumb_url, timeout=15)
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

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint para verificar a saúde da aplicação"""
    return jsonify({
        "status": "ok",
        "timestamp": time.time(),
        "version": "1.1.0"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)