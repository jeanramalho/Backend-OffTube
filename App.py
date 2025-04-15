import os
import re
import logging
import requests
import subprocess
import json
import time
import uuid
from flask import Flask, request, jsonify, send_file, redirect
from flask_cors import CORS
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import storage

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Directories for temporary storage
TEMP_FOLDER = "/tmp"
DOWNLOAD_FOLDER = os.path.join(TEMP_FOLDER, "videos")
THUMBNAIL_FOLDER = os.path.join(TEMP_FOLDER, "thumbnails")
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(THUMBNAIL_FOLDER).mkdir(exist_ok=True)

# Google Cloud Storage configuration
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "backend-offtube-videos")
storage_client = storage.Client()
try:
    bucket = storage_client.get_bucket(GCS_BUCKET_NAME)
    logger.info(f"Connected to GCS bucket: {GCS_BUCKET_NAME}")
except Exception as e:
    logger.error(f"Failed to connect to GCS bucket: {str(e)}")
    bucket = None

def extract_youtube_id(url):
    """Extract YouTube video ID from URL."""
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    m = re.search(pattern, url)
    return m.group(1) if m else None

def file_exists_in_gcs(file_path):
    """Check if a file exists in Google Cloud Storage."""
    if not bucket:
        return False
    blob = bucket.blob(file_path)
    return blob.exists()

def upload_to_gcs(local_path, gcs_path):
    """Upload a file to Google Cloud Storage."""
    if not bucket:
        logger.error("No GCS bucket available")
        return False
    try:
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(local_path)
        logger.info(f"Uploaded {local_path} to gs://{GCS_BUCKET_NAME}/{gcs_path}")
        return True
    except Exception as e:
        logger.error(f"Error uploading to GCS: {str(e)}")
        return False

def download_from_gcs(gcs_path, local_path):
    """Download a file from Google Cloud Storage."""
    if not bucket:
        logger.error("No GCS bucket available")
        return False
    try:
        blob = bucket.blob(gcs_path)
        blob.download_to_filename(local_path)
        logger.info(f"Downloaded gs://{GCS_BUCKET_NAME}/{gcs_path} to {local_path}")
        return True
    except Exception as e:
        logger.error(f"Error downloading from GCS: {str(e)}")
        return False

def get_gcs_signed_url(gcs_path, expires_in_seconds=3600):
    """Get a signed URL for a file in Google Cloud Storage."""
    if not bucket:
        logger.error("No GCS bucket available")
        return None
    try:
        blob = bucket.blob(gcs_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=time.time() + expires_in_seconds,
            method="GET"
        )
        return url
    except Exception as e:
        logger.error(f"Error generating signed URL: {str(e)}")
        return None

def download_with_ytdlp(url, video_id):
    """Download video using yt-dlp CLI tool."""
    logger.info(f"Starting download with yt-dlp: {url}")
    
    # Create temporary paths
    temp_id = str(uuid.uuid4())
    temp_video_path = os.path.join(TEMP_FOLDER, f"{temp_id}.mp4")
    temp_thumb_path = os.path.join(TEMP_FOLDER, f"{temp_id}.jpg")
    
    final_video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    final_thumb_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    
    # Get video info first
    try:
        info_command = [
            "yt-dlp", 
            "--dump-json",
            "--no-playlist",
            url
        ]
        
        result = subprocess.run(info_command, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error(f"yt-dlp info failed: {result.stderr}")
            return False, f"yt-dlp info failed: {result.stderr}", None
            
        video_info = json.loads(result.stdout)
        title = video_info.get('title', f"video_{video_id}")
        
        # Download video
        download_command = [
            "yt-dlp",
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", temp_video_path,
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "--thumbnail-template", temp_thumb_path,
            "--no-playlist",
            url
        ]
        
        download_result = subprocess.run(download_command, capture_output=True, text=True, timeout=300)
        if download_result.returncode != 0:
            logger.error(f"yt-dlp download failed: {download_result.stderr}")
            return False, f"yt-dlp download failed: {download_result.stderr}", None
        
        # Check if the files were downloaded successfully
        if os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0:
            # Move files to final location
            os.rename(temp_video_path, final_video_path)
            if os.path.exists(temp_thumb_path):
                os.rename(temp_thumb_path, final_thumb_path)
            
            logger.info(f"Download completed (size: {os.path.getsize(final_video_path)/1024/1024:.2f} MB)")
            
            # Upload to GCS if bucket is available
            if bucket:
                gcs_video_path = f"videos/{video_id}.mp4"
                gcs_thumb_path = f"thumbnails/{video_id}.jpg"
                upload_to_gcs(final_video_path, gcs_video_path)
                
                if os.path.exists(final_thumb_path):
                    upload_to_gcs(final_thumb_path, gcs_thumb_path)
            
            return True, title, final_thumb_path if os.path.exists(final_thumb_path) else None
        else:
            return False, "File was not downloaded or is empty", None
            
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp process timed out")
        return False, "Download process timed out", None
    except Exception as e:
        logger.error(f"Error using yt-dlp: {str(e)}")
        return False, f"Error using yt-dlp: {str(e)}", None

@app.route("/download", methods=["POST"])
def handle_download():
    try:
        if not request.is_json:
            return jsonify({"error": "Request must contain valid JSON"}), 400
        
        data = request.get_json()
        url = data.get("url")
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        video_id = extract_youtube_id(url)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL"}), 400
        
        # Define paths
        gcs_video_path = f"videos/{video_id}.mp4"
        gcs_thumb_path = f"thumbnails/{video_id}.jpg"
        local_video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
        local_thumb_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
        
        # Check if files already exist in GCS
        if bucket and file_exists_in_gcs(gcs_video_path):
            # Get video info
            try:
                yt_info_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                info_resp = requests.get(yt_info_url, timeout=10)
                title = info_resp.json().get("title", f"video_{video_id}") if info_resp.status_code == 200 else f"video_{video_id}"
            except:
                title = f"video_{video_id}"
            
            # Generate signed URLs
            video_url = get_gcs_signed_url(gcs_video_path)
            thumb_url = get_gcs_signed_url(gcs_thumb_path) if file_exists_in_gcs(gcs_thumb_path) else None
            
            return jsonify({
                "success": True,
                "message": "Video already exists",
                "video_id": video_id,
                "filename": f"{video_id}.mp4",
                "download_url": video_url or f"/videos/{video_id}.mp4",
                "thumbnail_url": thumb_url or (f"/thumbnails/{video_id}.jpg" if file_exists_in_gcs(gcs_thumb_path) else None),
                "title": title
            })
        
        # Check if files exist locally
        if os.path.exists(local_video_path) and os.path.getsize(local_video_path) > 0:
            try:
                yt_info_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                info_resp = requests.get(yt_info_url, timeout=10)
                title = info_resp.json().get("title", f"video_{video_id}") if info_resp.status_code == 200 else f"video_{video_id}"
            except:
                title = f"video_{video_id}"
                
            # Upload to GCS if available
            if bucket:
                upload_to_gcs(local_video_path, gcs_video_path)
                if os.path.exists(local_thumb_path):
                    upload_to_gcs(local_thumb_path, gcs_thumb_path)
                
                # Generate signed URLs
                video_url = get_gcs_signed_url(gcs_video_path)
                thumb_url = get_gcs_signed_url(gcs_thumb_path) if os.path.exists(local_thumb_path) else None
                
                return jsonify({
                    "success": True,
                    "message": "Video already exists locally, uploaded to cloud",
                    "video_id": video_id,
                    "filename": f"{video_id}.mp4",
                    "download_url": video_url or f"/videos/{video_id}.mp4",
                    "thumbnail_url": thumb_url or (f"/thumbnails/{video_id}.jpg" if os.path.exists(local_thumb_path) else None),
                    "title": title
                })
            
            return jsonify({
                "success": True,
                "message": "Video already exists locally",
                "video_id": video_id,
                "filename": f"{video_id}.mp4",
                "download_url": f"/videos/{video_id}.mp4",
                "thumbnail_url": f"/thumbnails/{video_id}.jpg" if os.path.exists(local_thumb_path) else None,
                "title": title
            })
        
        # Download the video
        success, result, thumb_path = download_with_ytdlp(url, video_id)
        
        if not success:
            logger.error(f"Download failed: {result}")
            return jsonify({"error": "Download failed", "details": result}), 500
        
        title = result if isinstance(result, str) else f"video_{video_id}"
        
        # Generate URLs based on where the file is stored
        video_url = None
        thumb_url = None
        
        if bucket:
            video_url = get_gcs_signed_url(gcs_video_path)
            if file_exists_in_gcs(gcs_thumb_path):
                thumb_url = get_gcs_signed_url(gcs_thumb_path)
        
        return jsonify({
            "success": True,
            "video_id": video_id,
            "filename": f"{video_id}.mp4",
            "download_url": video_url or f"/videos/{video_id}.mp4",
            "thumbnail_url": thumb_url or (f"/thumbnails/{video_id}.jpg" if thumb_path else None),
            "title": title
        })
    except Exception as e:
        logger.error(f"Internal error: {str(e)}")
        return jsonify({"error": "Internal error", "details": str(e)}), 500

@app.route("/videos/<filename>", methods=["GET"])
def serve_video(filename):
    try:
        video_id = filename.split('.')[0]
        gcs_path = f"videos/{filename}"
        local_path = os.path.join(DOWNLOAD_FOLDER, filename)
        
        # Check if the file exists in GCS
        if bucket and file_exists_in_gcs(gcs_path):
            # Generate a signed URL and redirect to it
            signed_url = get_gcs_signed_url(gcs_path)
            if signed_url:
                return redirect(signed_url)
        
        # If not in GCS or failed to get signed URL, check locally
        if not os.path.exists(local_path):
            # Try to download from GCS
            if bucket:
                download_success = download_from_gcs(gcs_path, local_path)
                if not download_success:
                    return jsonify({"error": "Video not found"}), 404
            else:
                return jsonify({"error": "Video not found"}), 404
        
        return send_file(local_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Error serving video: {str(e)}")
        return jsonify({"error": "Error serving video"}), 500

@app.route("/thumbnails/<filename>", methods=["GET"])
def serve_thumbnail(filename):
    try:
        gcs_path = f"thumbnails/{filename}"
        local_path = os.path.join(THUMBNAIL_FOLDER, filename)
        
        # Check if the file exists in GCS
        if bucket and file_exists_in_gcs(gcs_path):
            # Generate a signed URL and redirect to it
            signed_url = get_gcs_signed_url(gcs_path)
            if signed_url:
                return redirect(signed_url)
        
        # If not in GCS or failed to get signed URL, check locally
        if not os.path.exists(local_path):
            # Try to download from GCS
            if bucket:
                download_success = download_from_gcs(gcs_path, local_path)
                if not download_success:
                    return jsonify({"error": "Thumbnail not found"}), 404
            else:
                return jsonify({"error": "Thumbnail not found"}), 404
        
        return send_file(local_path)
    except Exception as e:
        logger.error(f"Error serving thumbnail: {str(e)}")
        return jsonify({"error": "Error serving thumbnail"}), 500

@app.route("/delete/<video_id>", methods=["DELETE"])
def delete_video(video_id):
    video_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp4")
    thumb_path = os.path.join(THUMBNAIL_FOLDER, f"{video_id}.jpg")
    gcs_video_path = f"videos/{video_id}.mp4"
    gcs_thumb_path = f"thumbnails/{video_id}.jpg"
    
    errors = []
    
    # Delete from GCS
    if bucket:
        try:
            if file_exists_in_gcs(gcs_video_path):
                bucket.blob(gcs_video_path).delete()
            if file_exists_in_gcs(gcs_thumb_path):
                bucket.blob(gcs_thumb_path).delete()
        except Exception as e:
            errors.append(f"GCS deletion error: {str(e)}")
    
    # Delete local files
    for f in [video_path, thumb_path]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception as e:
            errors.append(str(e))
    
    if errors:
        return jsonify({"error": "Failed to delete some files", "details": errors}), 500
    
    return jsonify({"success": True})

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint to check the health of the application"""
    return jsonify({
        "status": "ok",
        "timestamp": time.time(),
        "version": "1.2.0",
        "gcs_connected": bucket is not None
    })

@app.route("/", methods=["GET"])
def root():
    """Root endpoint"""
    return jsonify({
        "message": "YouTube Downloader API",
        "status": "running",
        "endpoints": {
            "/download": "POST - Download a YouTube video",
            "/videos/<filename>": "GET - Get a video file",
            "/thumbnails/<filename>": "GET - Get a thumbnail image",
            "/delete/<video_id>": "DELETE - Delete a video",
            "/health": "GET - Check API health"
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)