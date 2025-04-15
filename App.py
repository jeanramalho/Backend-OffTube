import os
import re
import logging
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pathlib import Path
from dotenv import load_dotenv
from pytube import YouTube
from pytube.exceptions import RegexMatchError, VideoUnavailable

# Carrega variáveis de ambiente
load_dotenv()

# Configura o logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configurar pastas onde os vídeos e thumbnails serão salvos
DOWNLOAD_FOLDER = "videos"
THUMBNAIL_FOLDER = "thumbnails"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

# Rota teste para verificar se a API está online
@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "API is running"})

def extract_youtube_id(url):
    """Extrai o ID do vídeo a partir de uma URL do YouTube"""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    if not match:
        return None
    return match.group(1)

def download_from_url(download_url, video_id, title):
    """
    Faz o download do vídeo usando a URL obtida via RapidAPI.
    O vídeo é salvo em DOWNLOAD_FOLDER com o nome <video_id>.mp4.
    Também tenta baixar a thumbnail do vídeo.
    """
    logger.info(f"Iniciando download direto da URL (primeiros 100 caracteres): {download_url[:100]}...")
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    
    try:
        # Se a URL for relativa, completa com a base RapidAPI
        if download_url.startswith("/"):
            base_url = "https://youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com"
            download_url = base_url + download_url
        
        # Headers ajustados para simular uma requisição feita por um navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.youtube.com/',
            'Origin': 'https://www.youtube.com',
            'Sec-Fetch-Dest': 'video',
            'Sec-Fetch-Mode': 'no-cors'
        }
        
        response = requests.get(download_url, headers=headers, stream=True, allow_redirects=True)
        response.raise_for_status()
        logger.info(f"Resposta do download direto: Status {response.status_code}, Content-Type: {response.headers.get('Content-Type')}, Content-Length: {response.headers.get('Content-Length', 'Desconhecido')}")
        
        # Grava o conteúdo em arquivo
        with open(video_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Verifica se o arquivo foi criado e possui conteúdo
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            logger.info(f"Download concluído com sucesso. Tamanho: {os.path.getsize(video_path)/1024/1024:.2f} MB")
            # Tenta baixar a thumbnail
            try:
                thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                thumb_response = requests.get(thumbnail_url)
                if thumb_response.status_code != 200:
                    thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                    thumb_response = requests.get(thumbnail_url)
                if thumb_response.status_code == 200:
                    with open(thumbnail_path, 'wb') as f:
                        f.write(thumb_response.content)
                    logger.info("Thumbnail baixada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao baixar thumbnail: {str(e)}")
            return True, title
        else:
            raise Exception("Arquivo baixado está vazio ou não existe")
    except Exception as e:
        logger.error(f"Erro no download direto: {str(e)}")
        return False, str(e)

def download_using_pytube(url, video_id):
    """
    Realiza o download do vídeo utilizando o pytube.
    Tenta primeiro obter uma stream com resolução 720p; caso não encontre,
    seleciona a melhor qualidade disponível abaixo de 720p.
    """
    logger.info(f"Iniciando download com pytube para {url}")
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    
    try:
        yt = YouTube(url)
        # Baixar thumbnail pelo pytube
        if yt.thumbnail_url:
            logger.info(f"Baixando thumbnail do pytube: {yt.thumbnail_url}")
            thumb_response = requests.get(yt.thumbnail_url)
            if thumb_response.status_code == 200:
                with open(thumbnail_path, 'wb') as f:
                    f.write(thumb_response.content)
        
        # Tenta stream em 720p
        logger.info("Procurando stream de 720p")
        stream = yt.streams.filter(progressive=True, file_extension='mp4', res="720p").first()
        if not stream:
            logger.info("Stream de 720p não encontrada, procurando alternativas abaixo de 720p")
            all_streams = yt.streams.filter(progressive=True, file_extension='mp4')
            quality_streams = []
            for s in all_streams:
                if s.resolution:
                    try:
                        quality = int(s.resolution.replace("p", ""))
                        quality_streams.append((quality, s))
                    except Exception:
                        continue
            quality_streams.sort(reverse=True, key=lambda x: x[0])
            stream = None
            for quality, s in quality_streams:
                if quality <= 720:
                    stream = s
                    logger.info(f"Selecionada stream com resolução: {quality}p")
                    break
            if not stream and quality_streams:
                stream = quality_streams[0][1]
                logger.info(f"Usando a melhor stream disponível: {quality_streams[0][0]}p")
        
        if not stream:
            raise Exception("Nenhuma stream disponível para download")
        
        logger.info(f"Baixando vídeo em {stream.resolution}")
        stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{video_id}.mp4")
        
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            logger.info(f"Download com pytube concluído com sucesso. Tamanho: {os.path.getsize(video_path)/1024/1024:.2f} MB")
            return True, {"title": yt.title or f"Video {video_id}"}
        else:
            raise Exception("Arquivo baixado está vazio ou não existe")
    except Exception as e:
        logger.error(f"Erro no download com pytube: {str(e)}")
        return False, str(e)

def get_video_info_rapidapi(url):
    """
    Obtém informações do vídeo via RapidAPI.
    Extrai o título, URL da thumbnail e, principalmente, a URL de download.
    Prioriza vídeo em 720p ou, se não houver, a melhor qualidade disponível abaixo de 720p.
    """
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise Exception("URL do YouTube inválida")

        logger.info(f"Obtendo informações para o vídeo com ID: {video_id}")

        api_url = "https://youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com/videodownload.php"
        querystring = {"url": url}
        headers = {
            "X-RapidAPI-Key": os.getenv("RAPIDAPI_KEY", "sua_chave_aqui"),
            "X-RapidAPI-Host": "youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com"
        }

        response = requests.get(api_url, headers=headers, params=querystring)
        response.raise_for_status()
        logger.info("Resposta da API RapidAPI recebida")
        
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Erro ao decodificar JSON da RapidAPI: {str(e)}")
            raise Exception("Resposta da API não é um JSON válido")
        
        if not isinstance(data, list) or len(data) == 0:
            raise Exception("Formato de resposta inválido")
        
        main_data = data[0]
        if "urls" not in main_data or not main_data["urls"]:
            raise Exception("Nenhuma URL de download encontrada na resposta")
            
        urls = main_data.get("urls", [])
        logger.info(f"Encontradas {len(urls)} opções de URLs")
        if urls:
            logger.info(f"Exemplo de URL (primeira opção): {urls[0]}")

        target_quality = 720
        best_url = None
        best_quality = 0
        highest_below_target = 0
        best_below_target_url = None

        for entry in urls:
            if entry.get("extension") != "mp4" and entry.get("name") != "MP4":
                continue
                
            quality_str = entry.get("quality", "") or entry.get("subName", "")
            if not quality_str:
                continue
                
            try:
                quality = int(re.sub(r'\D', '', quality_str))
            except Exception:
                continue
                
            logger.info(f"Opção de qualidade encontrada: {quality}p")
            url_entry = entry.get("url", "")
            if not url_entry:
                continue
                
            if quality == target_quality:
                best_url = url_entry
                best_quality = quality
                logger.info(f"Qualidade alvo exata encontrada: {quality}p")
                break
            elif quality < target_quality and quality > highest_below_target:
                highest_below_target = quality
                best_below_target_url = url_entry
                logger.info(f"Nova melhor qualidade abaixo do alvo: {quality}p")
            elif quality > best_quality:
                best_quality = quality
                best_url = url_entry
                logger.info(f"Nova melhor qualidade geral: {quality}p")

        if best_quality == target_quality and best_url:
            download_url = best_url
            logger.info(f"Utilizando qualidade exata: {target_quality}p")
        elif highest_below_target > 0 and best_below_target_url:
            download_url = best_below_target_url
            logger.info(f"Utilizando melhor qualidade abaixo do alvo: {highest_below_target}p")
        elif best_url:
            download_url = best_url
            logger.info(f"Utilizando a melhor qualidade disponível: {best_quality}p")
        else:
            raise Exception("Nenhum link de download válido encontrado")

        title = main_data.get("title", "") or main_data.get("meta", {}).get("title", "") or f"video_{video_id}"
        thumbnail_url = main_data.get("pictureUrl", "") or f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

        return {
            'title': title,
            'thumbnail_url': thumbnail_url,
            'download_url': download_url,
            'video_id': video_id
        }

    except Exception as e:
        logger.error(f"Erro ao obter informações do vídeo via RapidAPI: {str(e)}")
        raise

@app.route("/download", methods=["POST"])
def handle_download():
    try:
        if not request.is_json:
            logger.error("Requisição não contém JSON válido")
            return jsonify({"error": "Requisição deve conter JSON válido"}), 400
            
        data = request.get_json()
        logger.info(f"Dados recebidos: {data}")
        
        url = data.get("url")
        if not url:
            return jsonify({"error": "URL é obrigatória"}), 400
            
        video_id = extract_youtube_id(url)
        if not video_id:
            return jsonify({"error": "URL do YouTube inválida"}), 400
        
        video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            logger.info(f"Vídeo {video_id} já existe no sistema")
            try:
                yt_info_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                info_response = requests.get(yt_info_url)
                title = info_response.json().get("title", f"Video {video_id}") if info_response.status_code == 200 else f"Video {video_id}"
            except:
                title = f"Video {video_id}"
                
            return jsonify({
                "success": True,
                "message": "Vídeo já existe no sistema",
                "video_id": video_id,
                "filename": f"{video_id}.mp4",
                "download_url": f"/videos/{video_id}.mp4",
                "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
                "title": title
            })

        # MÉTODO 1: Usar RapidAPI
        try:
            logger.info("Tentando download com RapidAPI (Método primário)")
            video_info = get_video_info_rapidapi(url)
            if video_info and video_info.get("download_url"):
                download_url = video_info.get("download_url")
                title = video_info.get("title", f"Video {video_id}")
                thumbnail_url = video_info.get("thumbnail_url")
                
                if thumbnail_url:
                    thumb_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
                    thumb_response = requests.get(thumbnail_url)
                    if thumb_response.status_code == 200:
                        with open(thumb_path, 'wb') as f:
                            f.write(thumb_response.content)
                        logger.info("Thumbnail baixada com sucesso via RapidAPI")
                
                success, result = download_from_url(download_url, video_id, title)
                if success:
                    logger.info("Download feito com URL direta via RapidAPI")
                    return jsonify({
                        "success": True,
                        "video_id": video_id,
                        "filename": f"{video_id}.mp4",
                        "download_url": f"/videos/{video_id}.mp4",
                        "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
                        "title": title
                    })
                else:
                    logger.warning(f"Download direto via RapidAPI falhou: {result}")
                    raise Exception(f"Falha no download direto: {result}")
        except Exception as e:
            logger.warning(f"Método RapidAPI falhou: {str(e)}")
        
        # MÉTODO 2: Usar pytube
        try:
            logger.info("Tentando download com pytube (Método secundário)")
            success, result = download_using_pytube(url, video_id)
            if success:
                logger.info("Download com pytube bem-sucedido")
                return jsonify({
                    "success": True,
                    "video_id": video_id,
                    "filename": f"{video_id}.mp4",
                    "download_url": f"/videos/{video_id}.mp4",
                    "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
                    "title": result.get("title", f"Video {video_id}")
                })
            else:
                logger.warning(f"Download com pytube falhou: {result}")
                raise Exception(f"Falha no download com pytube: {result}")
        except Exception as e:
            logger.warning(f"Método pytube falhou: {str(e)}")

        return jsonify({
            "error": "Todos os métodos de download falharam",
            "details": "Não foi possível baixar o vídeo com nenhum dos métodos disponíveis"
        }), 500

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
