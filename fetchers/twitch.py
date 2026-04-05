"""
Twitch clip fetcher using the Helix API.
Docs: https://dev.twitch.tv/docs/api/reference/#get-clips
"""
import logging, requests
from config import settings

logger = logging.getLogger(__name__)

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_BASE = "https://api.twitch.tv/helix"
_bearer_token   = None


def _get_bearer_token() -> str:
    global _bearer_token
    if _bearer_token:
        return _bearer_token
    resp = requests.post(TWITCH_AUTH_URL, params={
        "client_id":     settings.TWITCH_CLIENT_ID,
        "client_secret": settings.TWITCH_CLIENT_SECRET,
        "grant_type":    "client_credentials",
    }, timeout=10)
    resp.raise_for_status()
    _bearer_token = resp.json()["access_token"]
    return _bearer_token


def _get_game_id(game_name: str, headers: dict):
    resp = requests.get(
        f"{TWITCH_API_BASE}/games",
        headers=headers,
        params={"name": game_name},
        timeout=10,
    )
    data = resp.json().get("data", [])
    return data[0]["id"] if data else None


def fetch_top_clips(games: list, period: str = "week", limit: int = 20) -> list:
    if not settings.TWITCH_CLIENT_ID or not settings.TWITCH_CLIENT_SECRET:
        logger.warning("Twitch credentials not configured — skipping.")
        return []
    try:
        token = _get_bearer_token()
    except Exception as e:
        logger.error(f"Could not get Twitch token: {e}")
        return []

    headers = {
        "Client-Id":     settings.TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    clips = []
    for game_name in games:
        game_name = game_name.strip()
        try:
            game_id = _get_game_id(game_name, headers)
        except Exception as e:
            logger.warning(f"Twitch game lookup failed for '{game_name}': {e}")
            continue
        if not game_id:
            logger.warning(f"Twitch game not found: {game_name}")
            continue
        try:
            resp = requests.get(
                f"{TWITCH_API_BASE}/clips",
                headers=headers,
                params={
                    "game_id":    game_id,
                    "first":      min(limit, 20),
                    "started_at": _period_to_rfc3339(period),
                },
                timeout=15,
            )
        except Exception as e:
            logger.error(f"Twitch clips request failed: {e}")
            continue
        if resp.status_code != 200:
            logger.error(f"Twitch API {resp.status_code}: {resp.text[:200]}")
            continue
        for c in resp.json().get("data", []):
            clips.append({
                "source":        "twitch",
                "clip_id":       f"twitch_{c['id']}",
                "title":         c["title"],
                "streamer":      c["broadcaster_name"],
                "game":          game_name,
                "view_count":    c["view_count"],
                "duration":      c["duration"],
                "clip_url":      c["url"],
                "download_url":  c["url"],
                "thumbnail_url": c["thumbnail_url"],
            })

    logger.info(f"Twitch: fetched {len(clips)} clips across {len(games)} game(s).")
    return clips


def _period_to_rfc3339(period: str) -> str:
    from datetime import datetime, timedelta, timezone
    now   = datetime.now(timezone.utc)
    delta = {"day": 1, "week": 7, "month": 30, "all": 3650}.get(period, 7)
    return (now - timedelta(days=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")
