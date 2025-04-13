@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        video_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.%(ext)s")
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")

        print(f"[INFO] Baixando vídeo: {url}")
        print(f"[INFO] Caminho de saída: {output_template}")

        # Verificar se a URL é válida
        if not re.match(r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/', url):
            print(f"[ERRO] URL inválida: {url}")
            return jsonify({"error": "URL do YouTube inválida"}), 400

        # Criar arquivo temporário de cookies
        cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
        
        if not cookies_content:
            print("[AVISO] Variável de ambiente YOUTUBE_COOKIES não encontrada")
            return jsonify({"error": "Cookies do YouTube não configurados no servidor"}), 500
            
        temp_cookies_path = None
        try:
            # Criar arquivo de cookies no formato Netscape
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as temp_cookies:
                # Converter cookies para formato Netscape
                cookies_lines = cookies_content.split('\n')
                for line in cookies_lines:
                    if line.strip() and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            # Formatar linha no padrão Netscape
                            domain = parts[0]
                            flag = parts[1]
                            path = parts[2]
                            secure = parts[3]
                            expiration = parts[4]
                            name = parts[5]
                            value = parts[6]
                            formatted_line = f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n"
                            temp_cookies.write(formatted_line)
                temp_cookies_path = temp_cookies.name
            
            print(f"[INFO] Arquivo temporário de cookies criado em: {temp_cookies_path}")
            
            # Obter informações do vídeo com configurações adicionais
            info_result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "--dump-json",
                "--socket-timeout", "30",
                "--retries", "10",  # Aumenta número de tentativas
                "--fragment-retries", "10",  # Aumenta tentativas de fragmentos
                "--extractor-retries", "10",  # Aumenta tentativas do extrator
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # User-Agent realista
                url
            ], capture_output=True, text=True, timeout=60)
            
            if info_result.returncode != 0:
                print(f"[ERRO] Falha ao obter informações do vídeo: {info_result.stderr}")
                return jsonify({"error": f"Erro ao obter informações do vídeo: {info_result.stderr}"}), 500
                
            video_info = json.loads(info_result.stdout)
            video_title = video_info.get("title", "Vídeo sem título")
            video_duration = video_info.get("duration", 0)
            
            # Verificar se o vídeo está disponível
            if video_info.get("availability") != "public":
                print(f"[ERRO] Vídeo não disponível: {url}")
                return jsonify({"error": "Vídeo não está disponível"}), 400
            
            # Baixar thumbnail
            thumbnail_result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "--write-thumbnail",
                "--skip-download",
                "--convert-thumbnails", "jpg",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "-o", os.path.join(THUMBNAIL_FOLDER, f"{video_id}"),
                url
            ], capture_output=True, text=True, timeout=30)
            
            thumbnail_url = None
            thumbnails = [f for f in os.listdir(THUMBNAIL_FOLDER) if f.startswith(video_id)]
            if thumbnails:
                thumbnail_url = f"/thumbnails/{thumbnails[0]}"
            
            # Baixar vídeo com configurações adicionais
            result = subprocess.run([
                "yt-dlp",
                "--cookies", temp_cookies_path,
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--socket-timeout", "30",
                "--retries", "10",
                "--fragment-retries", "10",
                "--extractor-retries", "10",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "-o", output_template,
                url
            ], capture_output=True, text=True, timeout=300)

            print("[STDOUT]", result.stdout)
            print("[STDERR]", result.stderr)

            if result.returncode != 0:
                print(f"[ERRO] Falha no download: {result.stderr}")
                return jsonify({"error": f"Erro ao baixar vídeo: {result.stderr}"}), 500

            saved_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(video_id)]
            
            if not saved_files:
                print("[ERRO] Nenhum arquivo encontrado após download")
                return jsonify({"error": "Arquivo não encontrado após download"}), 500
                
            print(f"[INFO] Vídeo baixado com sucesso: {saved_files[0]}")
            
            return jsonify({
                "url": f"/videos/{saved_files[0]}",
                "id": video_id,
                "title": video_title,
                "thumbnail": thumbnail_url,
                "duration": video_duration
            })

        finally:
            if temp_cookies_path and os.path.exists(temp_cookies_path):
                os.unlink(temp_cookies_path)
                print("[INFO] Arquivo temporário de cookies removido")

    except subprocess.TimeoutExpired:
        print("[ERRO] Timeout ao processar vídeo")
        return jsonify({"error": "Timeout ao processar vídeo"}), 500
    except Exception as e:
        print(f"[ERRO] {str(e)}")
        return jsonify({"error": str(e)}), 500