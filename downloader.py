"""
Video downloader using yt-dlp.
"""
import os, logging
import yt_dlp
from config import settings

logger = logging.getLogger(__name__)
os.makedirs(settings.DOWNLOADS_DIR, exist_ok=True)


def download_clip(clip_url: str, clip_id: str) -> str | None:
    output_template = os.path.join(settings.DOWNLOADS_DIR, f"{clip_id}.%(ext)s")
    ydl_opts = {
        "outtmpl":             output_template,
        "format":              "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet":               True,
        "no_warnings":         True,
        "noplaylist":          True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clip_url, download=True)
            ext  = info.get("ext", "mp4")
            path = os.path.join(settings.DOWNLOADS_DIR, f"{clip_id}.{ext}")
            if os.path.exists(path):
                return path
            for f in os.listdir(settings.DOWNLOADS_DIR):
                if f.startswith(clip_id):
                    return os.path.join(settings.DOWNLOADS_DIR, f)
    except Exception as e:
        logger.error(f"Download failed for {clip_url}: {e}")
    return None


def cleanup_clip(local_path: str):
    try:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
    except Exception as e:
        logger.warning(f"Could not delete {local_path}: {e}")
