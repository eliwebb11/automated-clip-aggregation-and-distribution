import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Twitch
    TWITCH_CLIENT_ID:     str = os.getenv("TWITCH_CLIENT_ID", "")
    TWITCH_CLIENT_SECRET: str = os.getenv("TWITCH_CLIENT_SECRET", "")

    # YouTube
    YOUTUBE_CLIENT_SECRETS_FILE: str = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
    YOUTUBE_TOKEN_FILE:          str = os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")

    # TikTok
    TIKTOK_CLIENT_KEY:    str = os.getenv("TIKTOK_CLIENT_KEY", "")
    TIKTOK_CLIENT_SECRET: str = os.getenv("TIKTOK_CLIENT_SECRET", "")
    TIKTOK_ACCESS_TOKEN:  str = os.getenv("TIKTOK_ACCESS_TOKEN", "")

    # Twitter / X
    TWITTER_API_KEY:              str = os.getenv("TWITTER_API_KEY", "")
    TWITTER_API_SECRET:           str = os.getenv("TWITTER_API_SECRET", "")
    TWITTER_ACCESS_TOKEN:         str = os.getenv("TWITTER_ACCESS_TOKEN", "")
    TWITTER_ACCESS_TOKEN_SECRET:  str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

    # Pipeline
    SCHEDULE_HOURS:      int = int(os.getenv("SCHEDULE_HOURS", "6"))
    MAX_CLIPS_PER_RUN:   int = int(os.getenv("MAX_CLIPS_PER_RUN", "10"))
    CLIP_MAX_DURATION:   int = int(os.getenv("CLIP_MAX_DURATION", "60"))
    DOWNLOADS_DIR:       str = os.getenv("DOWNLOADS_DIR", "downloads")
    DATABASE_URL:        str = os.getenv("DATABASE_URL", "sqlite:///clips.db")

    UPLOAD_YOUTUBE: bool = os.getenv("UPLOAD_YOUTUBE", "true").lower() == "true"
    UPLOAD_TIKTOK:  bool = os.getenv("UPLOAD_TIKTOK",  "true").lower() == "true"
    UPLOAD_TWITTER: bool = os.getenv("UPLOAD_TWITTER", "true").lower() == "true"

settings = Settings()
