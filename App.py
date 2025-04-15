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
from pytube import YouTube
from pytube.exceptions import RegexMatchError, VideoUnavailable

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

def download_from_url(download_url, video_id, title):
    """Download video directly from a URL."""
    logger.info(f"Iniciando download direto da URL: {download_url[:100]}...")
    
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    
    try:
        # Download the video using requests
        response = requests.get(download_url, stream=True)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Save the video to a file
        with open(video_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Verify the file exists and has content
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            logger.info(f"Download direto concluído com sucesso. Tamanho: {os.path.getsize(video_path)/1024/1024:.2f} MB")
            
            # Try to get the thumbnail as well
            try:
                thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                thumbnail_response = requests.get(thumbnail_url)
                if thumbnail_response.status_code == 200:
                    with open(thumbnail_path, 'wb') as f:
                        f.write(thumbnail_response.content)
                    logger.info(f"Thumbnail baixada com sucesso")
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
    Baixa o vídeo diretamente usando o pytube
    """
    logger.info(f"Iniciando download com pytube para {url}")
    
    # Caminhos para salvar os arquivos
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    
    try:
        # Criar objeto YouTube
        yt = YouTube(url)
        
        # Salvar thumbnail
        if yt.thumbnail_url:
            logger.info(f"Salvando thumbnail: {yt.thumbnail_url}")
            thumbnail_response = requests.get(yt.thumbnail_url)
            if thumbnail_response.status_code == 200:
                with open(thumbnail_path, 'wb') as f:
                    f.write(thumbnail_response.content)
        
        # Tentar obter stream de 720p primeiro
        logger.info("Procurando stream de 720p")
        stream = yt.streams.filter(progressive=True, file_extension='mp4', res="720p").first()
        
        # Se não encontrar 720p, procurar a melhor qualidade abaixo
        if not stream:
            logger.info("Stream de 720p não encontrado, procurando alternativas")
            all_streams = yt.streams.filter(progressive=True, file_extension='mp4')
            
            # Ordenar streams por qualidade
            quality_streams = []
            for s in all_streams:
                try:
                    if s.resolution:
                        quality = int(s.resolution[:-1])  # Remove o 'p' da resolução
                        quality_streams.append((quality, s))
                except (ValueError, TypeError, AttributeError):
                    continue
            
            # Ordenar por qualidade (decrescente)
            quality_streams.sort(reverse=True)
            
            # Encontrar a melhor qualidade menor ou igual a 720p
            for quality, s in quality_streams:
                if quality <= 720:
                    stream = s
                    logger.info(f"Selecionada qualidade: {quality}p")
                    break
            
            # Se ainda não encontrou, pegar o primeiro stream disponível
            if not stream and all_streams:
                stream = all_streams.first()
                logger.info(f"Usando primeira stream disponível: {stream.resolution}")
        
        if not stream:
            raise Exception("Nenhum stream disponível para download")
        
        # Baixar o vídeo
        logger.info(f"Baixando vídeo em {stream.resolution}")
        stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{video_id}.mp4")
        
        # Verificar se o arquivo foi baixado e tem tamanho > 0
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            logger.info(f"Download concluído com sucesso. Tamanho: {os.path.getsize(video_path)/1024/1024:.2f} MB")
            return True, {"title": yt.title or f"Video {video_id}"}
        else:
            raise Exception("Arquivo baixado está vazio ou não existe")
            
    except Exception as e:
        logger.error(f"Erro no download com pytube: {str(e)}")
        return False, str(e)

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
        
        # Método 1: Usar RapidAPI como primeira opção
        try:
            logger.info("Tentando obter informações com API RapidAPI (Método principal)")
            video_info = get_video_info_rapidapi(url)
            
            if video_info and video_info.get("download_url"):
                download_url = video_info.get("download_url")
                title = video_info.get("title", f"Video {video_id}")
                thumbnail_url = video_info.get("thumbnail_url")
                
                # Baixar o thumbnail se disponível
                if thumbnail_url:
                    try:
                        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
                        thumbnail_response = requests.get(thumbnail_url)
                        if thumbnail_response.status_code == 200:
                            with open(thumbnail_path, 'wb') as f:
                                f.write(thumbnail_response.content)
                            logger.info("Thumbnail baixada com sucesso")
                    except Exception as e:
                        logger.warning(f"Erro ao baixar thumbnail: {str(e)}")
                
                # Download direto usando a URL obtida
                success, result = download_from_url(download_url, video_id, title)
                if success:
                    logger.info("Download feito com URL direta do RapidAPI")
                    return jsonify({
                        "success": True,
                        "video_id": video_id,
                        "filename": f"{video_id}.mp4",
                        "download_url": f"/videos/{video_id}.mp4",
                        "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
                        "title": title
                    })
                else:
                    logger.warning(f"Download direto falhou: {result}")
        except Exception as e:
            logger.warning(f"Método RapidAPI falhou: {str(e)}")
        
        # Método 2: Se RapidAPI falhar, tentar com pytube
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
                    "title": result["title"]
                })
            else:
                logger.warning(f"Download com pytube falhou: {result}")
        except Exception as e:
            logger.warning(f"Método pytube falhou: {str(e)}")
        
        # Método 3: Fazer uma última tentativa com pytube com configurações diferentes
        try:
            logger.info("Fazendo tentativa final com pytube")
            # Tentando novamente com mais configurações
            yt = YouTube(url)
            
            # Tentar stream progressivo (áudio e vídeo juntos)
            streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution')
            if not streams:
                streams = yt.streams.filter(file_extension='mp4').order_by('resolution')
            
            if not streams:
                return jsonify({
                    "error": "Nenhuma stream de vídeo encontrada",
                    "details": "O vídeo pode estar indisponível ou protegido"
                }), 500
            
            # Salvar thumbnail
            if yt.thumbnail_url:
                thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
                thumbnail_response = requests.get(yt.thumbnail_url)
                if thumbnail_response.status_code == 200:
                    with open(thumbnail_path, 'wb') as f:
                        f.write(thumbnail_response.content)
            
            # Encontrar o stream adequado
            stream = None
            for s in streams:
                if s.resolution and s.resolution.endswith('p'):
                    try:
                        quality = int(s.resolution[:-1])
                        if quality <= 720:
                            stream = s
                            logger.info(f"Selecionada qualidade {quality}p")
                            break
                    except (ValueError, TypeError):
                        continue
            
            # Se não encontrou nada adequado, usar o de maior qualidade
            if not stream:
                stream = streams.last()
                
            # Download direto
            out_file = stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{video_id}.mp4")
            
            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                logger.info(f"Download final bem-sucedido: {out_file}")
                return jsonify({
                    "success": True,
                    "video_id": video_id,
                    "filename": f"{video_id}.mp4",
                    "download_url": f"/videos/{video_id}.mp4",
                    "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")) else None,
                    "title": yt.title or f"Video {video_id}"
                })
            else:
                return jsonify({
                    "error": "Falha no download final",
                    "details": "Arquivo não foi baixado corretamente"
                }), 500
                
        except Exception as e:
            logger.error(f"Todas as tentativas falharam: {str(e)}")
            return jsonify({
                "error": "Todos os métodos de download falharam",
                "details": str(e)
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
    app.run(host="0.0.0.0", port=port, debug=True)