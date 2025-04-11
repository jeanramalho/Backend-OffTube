from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import subprocess

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "videos")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route("/download", methods=["POST"])
def download_video():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        video_id = str(uuid.uuid4())
        output_filename = f"{video_id}.mp4"
        output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)

        # 🔁 Comando atualizado com cookies
        result = subprocess.run([
            "yt-dlp",
            "--cookies", "cookies.txt",
            "-f", "bestvideo+bestaudio",
            "-o", output_path,
            url
        ], capture_output=True, text=True)

        if result.returncode != 0:
            return jsonify({"error": result.stderr}), 500

        return jsonify({"url": f"/videos/{output_filename}"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/videos/<filename>")
def serve_video(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=True)
