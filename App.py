import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging
import uuid
from pathlib import Path
import requests
import re
import time
import json
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

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

# Rota de teste para verificar se a API está online
@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "API is running"})

def extract_youtube_id(url):
    """Extrai o ID do vídeo de uma URL do YouTube"""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    if not match:
        return None
    return match.group(1)

def get_video_info_free_api(url):
    """
    Obtém informações do vídeo usando a API gratuita 'YouTube Quick Video Downloader'
    """
    try:
        # Extrair ID do vídeo
        video_id = extract_youtube_id(url)
        if not video_id:
            raise Exception("URL do YouTube inválida")
            
        logger.info(f"Obtendo informações para o vídeo com ID: {video_id}")
        
        # Construir a URL da API
        api_url = "https://youtube-video-download-info.p.rapidapi.com/dl"
        
        querystring = {"id": video_id}
        
        headers = {
            "X-RapidAPI-Key": os.getenv("RAPIDAPI_KEY", "CHAVE_DE_EXEMPLO"),
            "X-RapidAPI-Host": "youtube-video-download-info.p.rapidapi.com"
        }
        
        logger.info(f"Fazendo requisição para a API gratuita")
        response = requests.get(api_url, headers=headers, params=querystring)
        
        if response.status_code != 200:
            logger.error(f"Erro na API: Status {response.status_code}, Resposta: {response.text}")
            raise Exception(f"Erro ao acessar a API: {response.status_code}")
            
        try:
            data = response.json()
            logger.info("Resposta da API recebida com sucesso")
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON: {str(e)}")
            logger.error(f"Conteúdo recebido: {response.text[:500]}...")
            raise Exception("Falha ao processar resposta da API")
            
        # Verificar se a resposta contém dados válidos
        if not data or "link" not in data:
            logger.error(f"Resposta inválida da API: {data}")
            raise Exception("A API não retornou links de download")
            
        # Encontrar o melhor formato de qualidade disponível
        formats = data.get("link", [])
        best_video = None
        
        # Procurar por mp4 com a maior resolução
        for fmt in formats:
            if fmt.get("type") == "mp4":
                if not best_video or fmt.get("quality", 0) > best_video.get("quality", 0):
                    best_video = fmt
        
        # Se não encontrou mp4, usar qualquer formato disponível
        if not best_video and formats:
            best_video = formats[0]
            
        if not best_video:
            raise Exception("Nenhum formato de vídeo disponível")
            
        # Informações do vídeo
        title = data.get("title", f"video_{video_id}")
        thumbnail_url = data.get("thumb", f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
        download_url = best_video.get("url")
        
        if not download_url:
            raise Exception("URL de download não encontrada")
            
        return {
            'title': title,
            'thumbnail_url': thumbnail_url,
            'download_url': download_url,
            'video_id': video_id
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter informações do vídeo: {str(e)}")
        raise

def get_video_info_alternative(url):
    """
    Método alternativo para obter informações do vídeo sem API key
    """
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise Exception("URL do YouTube inválida")
            
        # Usar serviço y2mate diretamente sem API key
        api_url = f"https://x2download.app/api/ajaxSearch"
        
        payload = {
            "q": url,
            "vt": "home"
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://x2download.app',
            'Referer': 'https://x2download.app/'
        }
        
        logger.info(f"Tentando método alternativo para: {video_id}")
        response = requests.post(api_url, headers=headers, data=payload)
        
        if response.status_code != 200:
            raise Exception(f"Erro ao acessar serviço alternativo: {response.status_code}")
            
        try:
            data = response.json()
        except:
            logger.error(f"Erro ao decodificar resposta: {response.text[:500]}...")
            raise Exception("Resposta inválida do serviço alternativo")
            
        if not data.get("links") or not data.get("title"):
            raise Exception("Dados inválidos do serviço alternativo")
            
        # Obter o link de download de melhor qualidade
        links = data.get("links", {}).get("mp4", {})
        best_link = None
        best_quality = 0
        
        for quality, link_info in links.items():
            try:
                q = int(quality.replace("p", ""))
                if q > best_quality:
                    best_quality = q
                    best_link = link_info.get("k")
            except:
                continue
                
        if not best_link:
            raise Exception("Nenhum link de download encontrado")
            
        # Obter o link direto de download
        download_api = "https://x2download.app/api/ajaxConvert"
        convert_payload = {
            "vid": video_id,
            "k": best_link
        }
        
        convert_response = requests.post(download_api, headers=headers, data=convert_payload)
        
        if convert_response.status_code != 200:
            raise Exception(f"Erro ao converter vídeo: {convert_response.status_code}")
            
        try:
            convert_data = convert_response.json()
        except:
            raise Exception("Erro ao decodificar resposta de conversão")
            
        if not convert_data.get("dlink"):
            raise Exception("Link direto não encontrado")
            
        return {
            'title': data.get("title", f"video_{video_id}"),
            'thumbnail_url': f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            'download_url': convert_data.get("dlink"),
            'video_id': video_id
        }
        
    except Exception as e:
        logger.error(f"Erro no método alternativo: {str(e)}")
        raise

def download_video(video_info):
    try:
        video_id = video_info['video_id']
        logger.info(f"Iniciando download do vídeo: {video_id}")
        
        # Baixar thumbnail
        if video_info["thumbnail_url"]:
            logger.info(f"Baixando thumbnail: {video_info['thumbnail_url']}")
            response = requests.get(video_info["thumbnail_url"])
            if response.status_code == 200:
                with open(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg"), 'wb') as f:
                    f.write(response.content)
                logger.info("Thumbnail baixada com sucesso")
        
        # Baixar o vídeo
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.youtube.com/'
        }
        
        logger.info(f"Baixando vídeo de: {video_info['download_url']}")
        response = requests.get(video_info["download_url"], headers=headers, stream=True)
        
        if response.status_code == 200:
            video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
            total_size = 0
            with open(video_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            logger.info(f"Download completo. Tamanho do arquivo: {total_size/1024/1024:.2f}MB")
            return True, {
                "title": video_info["title"]
            }
        else:
            logger.error(f"Erro ao baixar vídeo. Status code: {response.status_code}")
            logger.error(f"Resposta: {response.text[:500]}...")
            raise Exception(f"Erro ao baixar vídeo: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Erro ao baixar vídeo: {str(e)}")
        return False, str(e)

@app.route("/download", methods=["POST"])
def handle_download():
    try:
        # Verificar se o request contém JSON válido
        if not request.is_json:
            logger.error("Requisição não contém JSON válido")
            return jsonify({"error": "Requisição deve conter JSON válido"}), 400
            
        data = request.get_json()
        logger.info(f"Dados recebidos: {data}")
        
        if not data:
            return jsonify({"error": "Dados JSON inválidos"}), 400
            
        url = data.get("url")
        if not url:
            return jsonify({"error": "URL é obrigatória"}), 400
            
        # Extrair ID do vídeo para validação
        video_id = extract_youtube_id(url)
        if not video_id:
            return jsonify({"error": "URL do YouTube inválida"}), 400
        
        # Verificar se o vídeo já existe no sistema
        video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
        if os.path.exists(video_path):
            logger.info(f"Vídeo {video_id} já existe no sistema")
            # Buscar informações do título
            try:
                # Tentativa simples de obter título do YouTube
                yt_info_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                info_response = requests.get(yt_info_url)
                title = "Vídeo sem título"
                if info_response.status_code == 200:
                    title = info_response.json().get("title", "Vídeo sem título")
            except:
                title = "Vídeo sem título"
                
            return jsonify({
                "success": True,
                "message": "Vídeo já existe no sistema",
                "video_id": video_id,
                "filename": f"{video_id}.mp4",
                "download_url": f"/videos/{video_id}.mp4",
                "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
                "title": title
            })
        
        # Tentar obter informações do vídeo usando primeiro método
        video_info = None
        error_message = None
        
        try:
            logger.info("Tentando obter informações com API principal")
            video_info = get_video_info_free_api(url)
        except Exception as e:
            error_message = str(e)
            logger.warning(f"API principal falhou: {error_message}")
            
            # Tentar método alternativo
            try:
                logger.info("Tentando método alternativo")
                video_info = get_video_info_alternative(url)
            except Exception as e2:
                logger.error(f"Método alternativo também falhou: {str(e2)}")
                return jsonify({
                    "error": "Falha ao processar URL do vídeo",
                    "details": f"Tentamos múltiplos métodos, mas todos falharam. Erro: {str(e2)}"
                }), 500
        
        if not video_info:
            return jsonify({
                "error": "Não foi possível obter informações do vídeo",
                "details": error_message or "Erro desconhecido"
            }), 500
        
        # Baixar vídeo
        success, result = download_video(video_info)
        
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
    app.run(host="0.0.0.0", port=port, debug=True)