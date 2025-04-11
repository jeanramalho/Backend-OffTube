# 🎬 OffTube - YouTube Video Downloader API

**OffTube** é uma API simples e eficiente desenvolvida em **Python + Flask**, que permite baixar vídeos completos do YouTube (com áudio e imagem) via requisições HTTP. É ideal para aplicações mobile ou web que desejam consumir e armazenar vídeos de forma prática e segura.

---

## 🚀 Visão Geral

O OffTube nasceu como parte de um app pessoal iOS, com o objetivo de facilitar o download e reprodução offline de vídeos do YouTube, respeitando os termos de uso e com foco educacional e experimental.

Com apenas uma requisição POST, a API retorna um arquivo `.mp4` pronto para ser usado em qualquer player ou integração.

---

## 🧠 Tecnologias e Ferramentas

- **Python 3**
- **Flask** — Web framework leve e rápido
- **yt-dlp** — Poderosa ferramenta de download de mídias do YouTube
- **FFmpeg** — Utilizado para combinar vídeo e áudio
- **Flask-CORS** — Suporte a requisições cross-origin

---

## 📦 Como usar localmente

### 1. Clone o repositório
```bash
git clone https://github.com/seu-usuario/offtube-api.git
cd offtube-api
```

### 2. Instale as dependências
```bash
pip install -r requirements.txt
```

### 3. Instale o FFmpeg (necessário para combinar vídeo e áudio)

#### macOS:
```bash
brew install ffmpeg
```

#### Ubuntu/Debian:
```bash
sudo apt install ffmpeg
```

#### Windows:
Baixe em: [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/)  
E adicione o caminho `bin` ao seu `PATH`.

### 4. Execute o servidor
```bash
python app.py
```

A API estará disponível em:  
📍 `http://127.0.0.1:5000`

---

## 📡 Endpoint

### `POST /download`

Baixa um vídeo do YouTube em formato `.mp4`.

#### 🔸 Body (JSON):
```json
{
  "url": "https://www.youtube.com/watch?v=GPO3cyi2dHM"
}
```

#### 🔸 Resposta:
```json
{
  "url": "/videos/123e4567-e89b-12d3-a456-426614174000.mp4"
}
```

### `GET /videos/<filename>`

Acessa o vídeo salvo pelo nome retornado no download.

---

## 💼 Sobre o autor

Desenvolvido por [Jean Ramalho](https://www.linkedin.com/in/jean-ramalho/), desenvolvedor iOS apaixonado por soluções mobile que entregam valor real, com foco em performance, UX e organização de código.

📬 Contato: [jeanramalho.dev@gmail.com](mailto:jeanramalho.dev@gmail.com)

---

## 🌟 Diferenciais do Projeto

- Estrutura limpa e modular para fácil deploy em nuvem (Render, Railway, etc)
- Perfeito para integrar com apps iOS nativos (MVVM / ViewCode)
- Projeto didático e funcional, ideal para portfólio técnico
- Demonstrativo real de integração backend + app mobile com consumo de vídeo

---


> **Disclaimer:** Este projeto é para fins educacionais e pessoais. Respeite sempre os termos de uso e direitos autorais das plataformas.