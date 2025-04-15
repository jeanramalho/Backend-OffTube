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
import random

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
    """Obtém informações do vídeo usando a API do RapidAPI"""
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise Exception("URL do YouTube inválida")

        logger.info(f"Obtendo informações para o vídeo com ID: {video_id}")

        api_url = "https://youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com/videodownload.php"
        querystring = {"url": url}
        headers = {
            "X-RapidAPI-Key": os.getenv("RAPIDAPI_KEY", "e675e37fe3msh28737c9013eca79p1ed09cjsn7b8a4c446ef0"),
            "X-RapidAPI-Host": "youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com"
        }

        # Adicionar delay para evitar erros de rate limit
        time.sleep(1)

        response = requests.get(api_url, headers=headers, params=querystring)
        if response.status_code != 200:
            logger.error(f"Erro na API: Status {response.status_code}, Resposta: {response.text}")
            raise Exception(f"Erro ao acessar a API: {response.status_code}")

        # Log da resposta para debugging
        logger.info(f"Resposta da API RapidAPI: {response.text[:200]}...")
        
        data = response.json()

        # A resposta é uma lista, pegamos o primeiro item
        if not isinstance(data, list) or len(data) == 0:
            raise Exception("Formato de resposta inválido")
        
        main_data = data[0]  # Primeiro item da lista
        
        # Verificar se urls existe
        if "urls" not in main_data or not main_data["urls"]:
            raise Exception("Nenhuma URL de download encontrada na resposta")
            
        urls = main_data.get("urls", [])

        # Log para verificar a estrutura dos URLs
        logger.info(f"Encontradas {len(urls)} opções de URLs")
        if urls:
            logger.info(f"Exemplo de URL primeira opção: {urls[0]}")

        # Priorizar 720p ou a melhor qualidade abaixo
        target_quality = 720
        best_url = None
        best_quality = 0
        highest_below_target = 0
        best_below_target_url = None

        for entry in urls:
            # Pular entradas que não são MP4
            if entry.get("extension") != "mp4" and entry.get("name") != "MP4":
                continue
                
            # Extrair qualidade como número
            quality_str = entry.get("quality", "")
            quality_str = entry.get("subName", quality_str)  # Tenta o campo subName se quality não existir
            
            try:
                quality = int(re.sub(r'\D', '', quality_str))
            except:
                continue
                
            logger.info(f"Opção de qualidade encontrada: {quality}p")
            
            # Verificar URL
            url = entry.get("url", "")
            if not url:
                continue
                
            # Corrigir URL se for relativa
            if url.startswith("/"):
                url = "https://youtube-quick-video-downloader-free-api-downlaod-all-video.p.rapidapi.com" + url
                
            # Encontrar a qualidade exata de 720p
            if quality == target_quality:
                best_url = url
                best_quality = quality
                logger.info(f"Encontrada qualidade alvo exata: {quality}p")
                break
                
            # Se não encontrou ainda a qualidade alvo, guarde a melhor abaixo do alvo
            elif quality < target_quality and quality > highest_below_target:
                highest_below_target = quality
                best_below_target_url = url
                logger.info(f"Nova melhor qualidade abaixo do alvo: {quality}p")
                
            # Guardar a melhor qualidade como fallback
            elif quality > best_quality:
                best_quality = quality
                best_url = url
                logger.info(f"Nova melhor qualidade geral: {quality}p")

        # Se encontrou exatamente 720p, usa ela
        if best_quality == target_quality and best_url:
            download_url = best_url
            logger.info(f"Usando qualidade exata: {target_quality}p")
        # Se não, usa a melhor qualidade abaixo de 720p
        elif highest_below_target > 0 and best_below_target_url:
            download_url = best_below_target_url
            logger.info(f"Usando melhor qualidade abaixo do alvo: {highest_below_target}p")
        # Se não encontrou nada abaixo de 720p, usa a melhor qualidade disponível
        elif best_url:
            download_url = best_url
            logger.info(f"Usando melhor qualidade disponível: {best_quality}p")
        else:
            raise Exception("Nenhum link de download válido encontrado")

        # Extrair título do vídeo
        title = main_data.get("title", "")
        if not title:
            # Tentar outras fontes para o título
            title = main_data.get("meta", {}).get("title", "")
        
        if not title:
            title = f"video_{video_id}"

        # Obter thumbnail
        thumbnail_url = main_data.get("pictureUrl", "")
        if not thumbnail_url:
            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

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
    Método alternativo para obter informações do vídeo usando serviços alternativos
    """
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise Exception("URL do YouTube inválida")
        
        logger.info(f"Tentando método alternativo para: {video_id}")
        
        # Lista de user agents para rotação
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0'
        ]
        
        # Adicionar delay para evitar rate limits
        time.sleep(random.uniform(1, 2))
        
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.google.com/'
        }
        
        # MÉTODO 1: Tentar com pytube diretamente
        try:
            from pytube import YouTube
            
            logger.info("Tentando método pytube direto")
            yt = YouTube(url)
            
            # Procurar stream com qualidade 720p ou melhor qualidade abaixo
            target_quality = 720
            stream = None
            
            # Primeiro, tentar encontrar exatamente 720p
            streams_720p = yt.streams.filter(progressive=True, file_extension='mp4', resolution='720p')
            if streams_720p:
                stream = streams_720p.first()
                logger.info("Encontrado stream de 720p")
            
            # Se não encontrar 720p, encontrar a melhor qualidade abaixo
            if not stream:
                all_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution')
                
                best_below_target = None
                for s in all_streams:
                    try:
                        res = int(s.resolution[:-1])  # Remover o 'p' do final
                        if res < target_quality and (best_below_target is None or res > int(best_below_target.resolution[:-1])):
                            best_below_target = s
                    except:
                        continue
                
                if best_below_target:
                    stream = best_below_target
                    logger.info(f"Encontrado stream abaixo de 720p: {stream.resolution}")
                else:
                    # Se não encontrar nada abaixo, pegar o melhor disponível
                    stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                    logger.info(f"Usando melhor stream disponível: {stream.resolution if stream else 'Nenhum'}")
            
            if stream:
                logger.info(f"Stream encontrado: {stream.resolution}")
                return {
                    'title': yt.title,
                    'thumbnail_url': yt.thumbnail_url,
                    'download_url': stream.url,
                    'video_id': video_id
                }
            else:
                logger.warning("Nenhum stream adequado encontrado via pytube")
        except Exception as e:
            logger.warning(f"Método pytube falhou: {str(e)}")
        
        # MÉTODO 2: Tentar serviço Y2mate
        try:
            logger.info("Tentando método y2mate")
            
            # Usar outro user agent
            headers['User-Agent'] = random.choice(user_agents)
            
            # Etapa 1: Iniciar o processo de análise
            analyze_url = "https://www.y2mate.com/mates/analyzeV2/ajax"
            payload = {
                "url": url,
                "q_auto": 0,
                "ajax": 1
            }
            
            # Adicionar delay para evitar rate limits
            time.sleep(random.uniform(1, 2))
            
            analyze_response = requests.post(analyze_url, data=payload, headers=headers)
            
            if analyze_response.status_code != 200:
                raise Exception(f"Erro ao analisar vídeo: {analyze_response.status_code}")
            
            try:
                analyze_data = analyze_response.json()
            except:
                logger.error(f"Erro ao decodificar resposta y2mate: {analyze_response.text[:100]}...")
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
            
            # Primeiro tentar 720p, depois qualidades inferiores
            qualities = ["720p", "480p", "360p", "240p", "144p"]
            download_url = None
            
            for quality in qualities:
                convert_payload = {
                    "vid": vid,
                    "k": f"mp4_{quality}",
                }
                
                # Adicionar delay para evitar rate limits
                time.sleep(random.uniform(0.5, 1))
                
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
            
            if download_url:
                return {
                    'title': title,
                    'thumbnail_url': f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                    'download_url': download_url,
                    'video_id': video_id
                }
        except Exception as e2:
            logger.warning(f"Método y2mate falhou: {str(e2)}")
        
        # Se chegou aqui, nenhum método funcionou
        raise Exception("Todos os métodos alternativos falharam")
        
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
        
        # Baixar o vídeo com um user agent aleatório
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0'
        ]
        
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://www.youtube.com/'
        }
        
        # Verificar se a URL de download é válida
        if not video_info["download_url"] or not video_info["download_url"].startswith(("http://", "https://")):
            logger.error(f"URL de download inválida: {video_info['download_url']}")
            raise Exception("URL de download inválida")
        
        logger.info(f"Baixando vídeo de: {video_info['download_url'][:50]}...")
        
        # Tentar o download com tratamento de retry
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                response = requests.get(video_info["download_url"], headers=headers, stream=True, timeout=30)
                
                if response.status_code == 200:
                    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
                    total_size = 0
                    with open(video_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                total_size += len(chunk)
                    
                    # Verificar se o arquivo foi baixado completamente
                    if total_size > 0:
                        logger.info(f"Download completo. Tamanho do arquivo: {total_size/1024/1024:.2f}MB")
                        success = True
                    else:
                        logger.warning("Arquivo baixado está vazio")
                        retry_count += 1
                        time.sleep(2)
                else:
                    logger.error(f"Erro ao baixar vídeo. Status code: {response.status_code}")
                    retry_count += 1
                    time.sleep(2)
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Erro de conexão ao baixar vídeo: {str(e)}")
                retry_count += 1
                time.sleep(2)
        
        if success:
            return True, {
                "title": video_info["title"]
            }
        else:
            raise Exception(f"Falha após {max_retries} tentativas de download")
            
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
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
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
        
        # Lista para armazenar erros de cada método
        errors = []
        
        # Método 1: RapidAPI
        try:
            logger.info("Tentando obter informações com API RapidAPI")
            video_info = get_video_info_rapidapi(url)
            if video_info:
                logger.info("API RapidAPI bem-sucedida")
        except Exception as e:
            error_message = str(e)
            errors.append(f"RapidAPI: {error_message}")
            logger.warning(f"API RapidAPI falhou: {error_message}")
        
        # Método 2: Alternativo
        if not video_info:
            try:
                logger.info("Tentando método alternativo")
                video_info = get_video_info_alternative(url)
                if video_info:
                    logger.info("Método alternativo bem-sucedido")
            except Exception as e2:
                errors.append(f"Alternativo: {str(e2)}")
                logger.error(f"Método alternativo também falhou: {str(e2)}")
        
        # Método 3: Pytube direto como último recurso
        if not video_info:
            try:
                logger.info("Tentando método pytube direto")
                from pytube import YouTube
                
                # Adicionar delay para evitar rate limits
                time.sleep(random.uniform(1, 2))
                
                yt = YouTube(url)
                
                # Primeiro procurar 720p
                stream = yt.streams.filter(progressive=True, file_extension='mp4', resolution='720p').first()
                
                # Se não encontrar 720p, buscar a melhor qualidade abaixo
                if not stream:
                    logger.info("720p não disponível, buscando qualidade inferior")
                    streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution')
                    
                    # Encontrar a melhor qualidade abaixo de 720p
                    target = 720
                    best_below = None
                    
                    for s in streams:
                        try:
                            res = int(s.resolution[:-1])  # Remover 'p' do final
                            if res < target and (best_below is None or res > int(best_below.resolution[:-1])):
                                best_below = s
                        except:
                            continue
                    
                    if best_below:
                        stream = best_below
                        logger.info(f"Usando qualidade {stream.resolution}")
                    else:
                        # Se não encontrar nenhuma abaixo, pegar a melhor disponível
                        stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                        logger.info(f"Usando melhor qualidade disponível: {stream.resolution if stream else 'Nenhuma'}")
                
                if not stream:
                    raise Exception("Nenhum stream disponível")
                    
                video_info = {
                    'title': yt.title,
                    'thumbnail_url': yt.thumbnail_url,
                    'download_url': stream.url,
                    'video_id': video_id
                }
                logger.info("Método pytube direto bem-sucedido")
            except Exception as e3:
                errors.append(f"Pytube: {str(e3)}")
                logger.error(f"Todos os métodos falharam. Erros: {', '.join(errors)}")
                return jsonify({
                    "error": "Falha ao processar URL do vídeo",
                    "details": f"Tentamos múltiplos métodos, mas todos falharam. Erro: {str(e3)}"
                }), 500
        
        if not video_info:
            return jsonify({
                "error": "Não foi possível obter informações do vídeo",
                "details": f"Todos os métodos falharam. Erros: {', '.join(errors)}"
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