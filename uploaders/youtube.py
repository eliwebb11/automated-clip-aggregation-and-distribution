"""
YouTube Shorts uploader using the YouTube Data API v3.
Requires OAuth 2.0 credentials (client_secrets.json from Google Cloud Console).
Scopes: https://www.googleapis.com/auth/youtube.upload
"""
import os, json, logging
from config import settings

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

SCOPES      = ["https://www.googleapis.com/auth/youtube.upload"]
API_NAME    = "youtube"
API_VERSION = "v3"


def _get_credentials() -> Credentials | None:
    creds      = None
    token_file = settings.YOUTUBE_TOKEN_FILE

    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
        except Exception as e:
            logger.warning(f"YouTube: could not load token: {e}")
            return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            logger.error(f"YouTube: token refresh failed: {e}")
            return None

    return creds if (creds and creds.valid) else None


def is_authenticated() -> bool:
    return _get_credentials() is not None


def start_oauth_flow() -> str:
    """
    Launches the local-server OAuth flow. Opens a browser tab for the user
    to grant permission, then saves youtube_token.json.
    Returns a success message.
    """
    secrets_file = settings.YOUTUBE_CLIENT_SECRETS_FILE
    if not os.path.exists(secrets_file):
        raise FileNotFoundError(
            f"'{secrets_file}' not found. Download it from "
            "Google Cloud Console → APIs & Services → Credentials."
        )
    flow  = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
    creds = flow.run_local_server(port=8090, open_browser=True)
    with open(settings.YOUTUBE_TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    logger.info("YouTube: OAuth complete. Token saved.")
    return "YouTube connected successfully!"


def upload_video(video_path: str, title: str, description: str = "", tags: list = None) -> str:
    """
    Upload a local MP4 as a YouTube Short.
    Returns the YouTube video ID on success. Raises on failure.
    """
    creds = _get_credentials()
    if not creds:
        raise RuntimeError(
            "YouTube is not authenticated. "
            "Go to Settings and click 'Connect YouTube'."
        )

    youtube = build(API_NAME, API_VERSION, credentials=creds, cache_discovery=False)

    # Ensure #Shorts in title for Shorts eligibility
    if "#Shorts" not in title and "#shorts" not in title:
        title = f"{title} #Shorts"

    tag_list = (tags or []) + ["Shorts", "Gaming", "Clips", "Twitch", "Kick"]

    body = {
        "snippet": {
            "title":       title[:100],
            "description": description or f"{title}\n\n#Shorts #Gaming #Clips",
            "tags":        tag_list,
            "categoryId":  "20",   # Gaming
        },
        "status": {
            "privacyStatus":           "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media    = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    inserter = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = inserter.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            logger.info(f"YouTube upload progress: {pct}%")

    video_id = response["id"]
    logger.info(f"YouTube: uploaded → https://youtube.com/shorts/{video_id}")
    return video_id
