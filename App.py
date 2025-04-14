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

def get_video_info_rapidapi(url):
    """
    Obtém informações do vídeo usando a API do RapidAPI que funcionou no exemplo
    """
    try:
        # Extrair ID do vídeo
        video_id = extract_youtube_id(url)
        if not video_id:
            raise Exception("URL do YouTube inválida")
            
        logger.info(f"Obtendo informações para o vídeo com ID: {video_id}")
        
        # Construir a URL da API - usando o endpoint que funcionou no exemplo
        api_url = "https://youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com/videodownload.php"
        
        querystring = {"url": url}
        
        headers = {
            "X-RapidAPI-Key": os.getenv("RAPIDAPI_KEY", "e675e37fe3msh28737c9013eca79p1ed09cjsn7b8a4c446ef0"),
            "X-RapidAPI-Host": "youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com"
        }
        
        logger.info(f"Fazendo requisição para a API RapidAPI")
        response = requests.get(api_url, headers=headers, params=querystring)
        
        if response.status_code != 200:
            logger.error(f"Erro na API: Status {response.status_code}, Resposta: {response.text}")
            raise Exception(f"Erro ao acessar a API: {response.status_code}")
            
        try:
            data = response.json()
            logger.info("Resposta da API recebida com sucesso")
            logger.info(f"Dados da API: {json.dumps(data)[:500]}...")
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON: {str(e)}")
            logger.error(f"Conteúdo recebido: {response.text[:500]}...")
            raise Exception("Falha ao processar resposta da API")
        
        # Processar dados do formato desta API específica
        if not data or not isinstance(data, dict):
            raise Exception("Formato de resposta inválido")
            
        # Esta API pode ter estrutura diferente - adaptando o parsing baseado no exemplo fornecido
        title = data.get("title", f"video_{video_id}")
        thumbnail_url = data.get("thumbnail", f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
        
        # Buscar o melhor link de download disponível
        download_url = None
        formats = []
        
        # Verificar diferentes campos que podem conter links
        for key in ["mp4", "videos", "formats", "links"]:
            if key in data and isinstance(data[key], (list, dict)):
                formats = data[key]
                break
                
        # Se formats for um dicionário (comum em algumas APIs)
        if isinstance(formats, dict):
            best_quality = 0
            for quality, link in formats.items():
                try:
                    # Tentar extrair o número da qualidade (ex: "720" de "720p")
                    quality_val = int(re.search(r'(\d+)', quality).group(1))
                    if quality_val > best_quality and isinstance(link, str) and link.startswith("http"):
                        best_quality = quality_val
                        download_url = link
                except (AttributeError, ValueError):
                    # Se não conseguir extrair a qualidade, só usar se não tiver outro
                    if not download_url and isinstance(link, str) and link.startswith("http"):
                        download_url = link
        
        # Se formats for uma lista (outro formato comum)
        elif isinstance(formats, list):
            best_quality = 0
            for item in formats:
                if isinstance(item, dict):
                    quality = item.get("quality", "0")
                    link = item.get("url", "")
                    
                    try:
                        quality_val = int(re.search(r'(\d+)', quality).group(1))
                        if quality_val > best_quality and link.startswith("http"):
                            best_quality = quality_val
                            download_url = link
                    except (AttributeError, ValueError):
                        if not download_url and link.startswith("http"):
                            download_url = link
        
        # Verificar se encontramos um URL válido
        if not download_url:
            # Verificar diretamente no objeto raiz se há um URL de download
            for key in ["url", "download_url", "link", "video_url"]:
                if key in data and isinstance(data[key], str) and data[key].startswith("http"):
                    download_url = data[key]
                    break
        
        if not download_url:
            raise Exception("URL de download não encontrada na resposta")
            
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
    Método alternativo para obter informações do vídeo usando o serviço Y2mate
    """
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise Exception("URL do YouTube inválida")
        
        logger.info(f"Tentando método alternativo para: {video_id}")
        
        # Primeiro, buscar uma API pública alternativa que não requer chave
        api_url = f"https://api.vevioz.com/api/button/mp4/{video_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://vevioz.com/'
        }
        
        logger.info(f"Buscando links no serviço vevioz")
        response = requests.get(api_url, headers=headers)
        
        # Verificar se temos HTML com links
        if response.status_code == 200:
            try:
                # Se for HTML, tentar extrair os links
                html_content = response.text
                # Buscar links dos downloads disponíveis
                download_links = re.findall(r'href=[\'"]?([^\'" >]+)', html_content)
                
                # Filtar apenas links de download de mp4
                mp4_links = [link for link in download_links if link.startswith("https://") and ".mp4" in link]
                
                if mp4_links:
                    # Usar o primeiro link disponível
                    download_url = mp4_links[0]
                    
                    # Para título, usar um regex simples
                    title_match = re.search(r'<b>(.*?)</b>', html_content)
                    title = title_match.group(1) if title_match else f"Video {video_id}"
                    
                    logger.info(f"Link de download encontrado no método alternativo: {download_url[:50]}...")
                    
                    return {
                        'title': title,
                        'thumbnail_url': f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                        'download_url': download_url,
                        'video_id': video_id
                    }
            except Exception as e:
                logger.error(f"Erro ao processar resposta HTML: {str(e)}")
        
        # Se o método acima falhar, tentar com o serviço y2mate
        logger.info("Tentando método y2mate")
        
        # Etapa 1: Iniciar o processo de análise
        analyze_url = "https://www.y2mate.com/mates/analyzeV2/ajax"
        payload = {
            "url": url,
            "q_auto": 0,
            "ajax": 1
        }
        
        analyze_response = requests.post(analyze_url, data=payload, headers=headers)
        
        if analyze_response.status_code != 200:
            raise Exception(f"Erro ao analisar vídeo: {analyze_response.status_code}")
        
        try:
            analyze_data = analyze_response.json()
        except:
            logger.error(f"Erro ao decodificar resposta y2mate: {analyze_response.text[:500]}...")
            raise Exception("Resposta inválida do serviço y2mate")
        
        if not analyze_data.get("status") == "success":
            raise Exception("Análise do vídeo falhou")
        
        # Extrair informações necessárias
        title = analyze_data.get("title", f"Video {video_id}")
        vid = analyze_data.get("vid", "")
        
        if not vid:
            raise Exception("ID do vídeo não encontrado na resposta")
        
        # Etapa 2: Converter para obter o link de download
        convert_url = "https://www.y2mate.com/mates/convertV2/index"
        
        # Tentar várias qualidades, do melhor para o pior
        qualities = ["1080p", "720p", "480p", "360p", "144p"]
        download_url = None
        
        for quality in qualities:
            convert_payload = {
                "vid": vid,
                "k": f"mp4_{quality}",
            }
            
            logger.info(f"Tentando obter vídeo na qualidade {quality}")
            convert_response = requests.post(convert_url, data=convert_payload, headers=headers)
            
            if convert_response.status_code == 200:
                try:
                    convert_data = convert_response.json()
                    if convert_data.get("status") == "success" and convert_data.get("dlink"):
                        download_url = convert_data.get("dlink")
                        logger.info(f"Link de download encontrado: {quality}")
                        break
                except:
                    continue
        
        if not download_url:
            raise Exception("Nenhum link de download encontrado")
        
        return {
            'title': title,
            'thumbnail_url': f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            'download_url': download_url,
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
        
        logger.info(f"Baixando vídeo de: {video_info['download_url'][:50]}...")
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
            logger.info("Tentando obter informações com API RapidAPI")
            video_info = get_video_info_rapidapi(url)
        except Exception as e:
            error_message = str(e)
            logger.warning(f"API RapidAPI falhou: {error_message}")
            
            # Tentar método alternativo
            try:
                logger.info("Tentando método alternativo")
                video_info = get_video_info_alternative(url)
            except Exception as e2:
                logger.error(f"Método alternativo também falhou: {str(e2)}")
                
                # Último recurso - tentar método direto usando pytube
                try:
                    # Este método requer pytube, adicione ao requirements.txt
                    logger.info("Tentando método direto")
                    from pytube import YouTube
                    
                    yt = YouTube(url)
                    stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                    
                    if not stream:
                        raise Exception("Nenhum stream disponível")
                        
                    video_info = {
                        'title': yt.title,
                        'thumbnail_url': yt.thumbnail_url,
                        'download_url': stream.url,
                        'video_id': video_id
                    }
                    logger.info("Método direto bem-sucedido")
                except Exception as e3:
                    logger.error(f"Todos os métodos falharam. Último erro: {str(e3)}")
                    return jsonify({
                        "error": "Falha ao processar URL do vídeo",
                        "details": f"Tentamos múltiplos métodos, mas todos falharam. Erro: {str(e3)}"
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