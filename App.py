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
import json

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

def get_video_info(url):
    try:
        # Configurar headers para simular um navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://www.y2mate.com',
            'Referer': 'https://www.y2mate.com/'
        }
        
        # Extrair ID do vídeo para uso posterior
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if not video_id_match:
            raise Exception("URL do YouTube inválida")
        video_id = video_id_match.group(1)
        
        # Fazer a requisição inicial para obter os dados do vídeo
        logger.info(f"Fazendo requisição para y2mate com URL: {url}")
        response = requests.post(
            'https://www.y2mate.com/mates/analyzeV2/ajax',
            headers=headers,
            data={
                'url': url,
                'q_auto': '0',
                'ajax': '1'
            }
        )
        
        logger.info(f"Status code da resposta: {response.status_code}")
        logger.info(f"Conteúdo da resposta: {response.text[:500]}...")  # Log primeiros 500 caracteres
        
        if response.status_code != 200:
            raise Exception(f"Erro ao acessar y2mate: {response.status_code}")
        
        # Tentar fazer parse do JSON
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON: {str(e)}")
            logger.error(f"Resposta recebida: {response.text}")
            raise Exception(f"Resposta inválida do serviço: {str(e)}")
            
        if not data.get('status') == 'success':
            logger.error(f"Falha na API do Y2Mate: {data}")
            raise Exception("Falha ao analisar vídeo")
            
        # Extrair informações do vídeo
        title = data.get('title', '')
        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
        
        # Obter o valor 'k' para o download
        mp4_links = data.get('links', {}).get('mp4', {})
        # Tente obter o formato automático, ou use o primeiro disponível
        k_value = None
        if 'auto' in mp4_links:
            k_value = mp4_links['auto'].get('k', '')
        else:
            # Pegar a primeira qualidade disponível
            for quality in mp4_links.values():
                if quality.get('k'):
                    k_value = quality.get('k')
                    break
                    
        if not k_value:
            raise Exception("Não foi possível encontrar link de download")
            
        # Obter links de download
        logger.info(f"Obtendo link de download com k={k_value}")
        response = requests.post(
            'https://www.y2mate.com/mates/convertV2/index',
            headers=headers,
            data={
                'vid': video_id,
                'k': k_value
            }
        )
        
        logger.info(f"Status code da resposta de download: {response.status_code}")
        logger.info(f"Conteúdo da resposta de download: {response.text[:500]}...")
        
        if response.status_code != 200:
            raise Exception(f"Erro ao obter links: {response.status_code}")
            
        # Tentar fazer parse do JSON
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON de download: {str(e)}")
            logger.error(f"Resposta recebida: {response.text}")
            raise Exception(f"Resposta inválida do serviço de download: {str(e)}")
            
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

        # Extrair ID do vídeo
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if not video_id_match:
            return jsonify({"error": "URL do YouTube inválida"}), 400
        video_id = video_id_match.group(1)
        
        # Obter informações do vídeo
        try:
            video_info = get_video_info(url)
        except Exception as e:
            logger.error(f"Falha ao obter informações do vídeo: {str(e)}")
            return jsonify({
                "error": "Falha ao processar URL do vídeo",
                "details": str(e)
            }), 500
        
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
    app.run(host="0.0.0.0", port=port, debug=True)