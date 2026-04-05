"""
TikTok uploader using the TikTok Content Posting API v2.
Docs: https://developers.tiktok.com/doc/content-posting-api-get-started

Setup:
  1. Create an app at https://developers.tiktok.com
  2. Enable the "Content Posting API" product
  3. Get your Client Key + Client Secret
  4. Complete OAuth to get an Access Token
  5. Paste the Access Token in Settings

Scopes needed: video.publish
"""
import os, json, logging, requests, time
from config import settings

logger = logging.getLogger(__name__)

API_BASE     = "https://open.tiktokapis.com/v2"
TOKEN_FILE   = "tiktok_token.json"


# ── Token management ─────────────────────────────────────────────────────────

def _load_token() -> dict:
    """Load token data from file or fall back to config."""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    # Fall back to env-supplied token
    if settings.TIKTOK_ACCESS_TOKEN:
        return {"access_token": settings.TIKTOK_ACCESS_TOKEN}
    return {}

def _save_token(data: dict):
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)

def _refresh_token(refresh_token: str) -> dict | None:
    """Exchange a refresh token for a new access token."""
    try:
        resp = requests.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            data={
                "client_key":    settings.TIKTOK_CLIENT_KEY,
                "client_secret": settings.TIKTOK_CLIENT_SECRET,
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            _save_token(data)
            logger.info("TikTok: token refreshed.")
            return data
    except Exception as e:
        logger.error(f"TikTok token refresh failed: {e}")
    return None

def get_access_token() -> str | None:
    """Return a valid access token, refreshing if needed."""
    token_data = _load_token()
    if not token_data:
        return None

    token = token_data.get("access_token")
    if not token:
        return None

    # Check expiry if we have it
    expires_at = token_data.get("expires_at", 0)
    if expires_at and time.time() > expires_at - 60:
        refresh = token_data.get("refresh_token")
        if refresh:
            new_data = _refresh_token(refresh)
            if new_data:
                return new_data.get("access_token")
        return None

    return token

def is_authenticated() -> bool:
    return bool(get_access_token())

def save_token_from_settings(access_token: str, refresh_token: str = "", expires_in: int = 0):
    """Save manually entered tokens from the Settings page."""
    data = {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "expires_at":    int(time.time()) + expires_in if expires_in else 0,
    }
    _save_token(data)

def get_oauth_url() -> str:
    """Generate TikTok OAuth URL for the user to visit."""
    if not settings.TIKTOK_CLIENT_KEY:
        raise ValueError("TIKTOK_CLIENT_KEY not set. Add it in Settings.")
    params = (
        f"client_key={settings.TIKTOK_CLIENT_KEY}"
        f"&scope=video.publish"
        f"&response_type=code"
        f"&redirect_uri=http://localhost:5000/api/auth/tiktok/callback"
    )
    return f"https://www.tiktok.com/v2/auth/authorize/?{params}"

def exchange_code_for_token(code: str) -> dict:
    """Exchange OAuth code for access + refresh tokens."""
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key":    settings.TIKTOK_CLIENT_KEY,
            "client_secret": settings.TIKTOK_CLIENT_SECRET,
            "code":          code,
            "grant_type":    "authorization_code",
            "redirect_uri":  "http://localhost:5000/api/auth/tiktok/callback",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("access_token"):
        data["expires_at"] = int(time.time()) + data.get("expires_in", 86400)
        _save_token(data)
    return data


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_video(video_path: str, title: str, description: str = "", tags: list = None) -> str:
    """
    Upload a video to TikTok using the Content Posting API.
    Returns the TikTok publish_id on success. Raises on failure.

    Flow:
      1. Init upload  → get upload_url + publish_id
      2. PUT video    → upload the file bytes
      3. Return publish_id (TikTok processes async)
    """
    token = get_access_token()
    if not token:
        raise RuntimeError(
            "TikTok is not authenticated. "
            "Add your Access Token in Settings."
        )

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    file_size = os.path.getsize(video_path)
    headers   = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json; charset=UTF-8",
    }

    # Build caption with tags
    tag_str  = " ".join(tags or [])
    caption  = f"{title}\n\n{description}\n\n{tag_str}".strip()[:2200]

    # ── Step 1: Init upload ───────────────────────────────────────────────
    init_payload = {
        "post_info": {
            "title":         caption,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet":  False,
            "disable_stitch":False,
            "disable_comment":False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source":          "FILE_UPLOAD",
            "video_size":      file_size,
            "chunk_size":      file_size,
            "total_chunk_count": 1,
        },
    }

    init_resp = requests.post(
        f"{API_BASE}/post/publish/video/init/",
        headers=headers,
        json=init_payload,
        timeout=30,
    )

    if init_resp.status_code != 200:
        raise RuntimeError(
            f"TikTok init failed ({init_resp.status_code}): {init_resp.text[:300]}"
        )

    init_data  = init_resp.json().get("data", {})
    publish_id = init_data.get("publish_id")
    upload_url = init_data.get("upload_url")

    if not publish_id or not upload_url:
        raise RuntimeError(f"TikTok init response missing fields: {init_resp.text[:300]}")

    # ── Step 2: Upload file ───────────────────────────────────────────────
    with open(video_path, "rb") as vf:
        video_bytes = vf.read()

    upload_headers = {
        "Content-Type":   "video/mp4",
        "Content-Length": str(file_size),
        "Content-Range":  f"bytes 0-{file_size - 1}/{file_size}",
    }

    upload_resp = requests.put(
        upload_url,
        headers=upload_headers,
        data=video_bytes,
        timeout=300,
    )

    if upload_resp.status_code not in (200, 201, 206):
        raise RuntimeError(
            f"TikTok file upload failed ({upload_resp.status_code}): {upload_resp.text[:300]}"
        )

    logger.info(f"TikTok: video uploaded, publish_id={publish_id}")
    return publish_id


def check_publish_status(publish_id: str) -> dict:
    """Check the processing status of a TikTok upload."""
    token = get_access_token()
    if not token:
        return {"status": "unknown", "error": "Not authenticated"}

    resp = requests.post(
        f"{API_BASE}/post/publish/status/fetch/",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json().get("data", {})
    return {"status": "error", "error": resp.text[:200]}
