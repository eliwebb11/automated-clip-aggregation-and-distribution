"""
Kick clip fetcher using the unofficial v2 API with tls-client to bypass Cloudflare.
No auth required — public clip data.

Settings field format:
  - Category slug:  just-chatting, slots, gambling
  - Specific streamer: @xqc, @trainwreckstv
"""
import logging
try:
    import tls_client
    HAS_TLS_CLIENT = True
except ImportError:
    import requests
    HAS_TLS_CLIENT = False

logger = logging.getLogger(__name__)

BASE = "https://kick.com/api/v2"
HEADERS = {
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://kick.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


def _get_session():
    if HAS_TLS_CLIENT:
        return tls_client.Session(
            client_identifier="chrome_122",
            random_tls_extension_order=True,
        ), True
    return None, False


def _get(session, using_tls, url, params=None):
    """Unified GET that works with both tls_client and requests."""
    if using_tls:
        resp = session.get(url, headers=HEADERS, params=params)
    else:
        import requests as req
        resp = req.get(url, headers=HEADERS, params=params, timeout=15)
    return resp

def fetch_top_clips(targets: list, period: str = "week", limit: int = 20) -> list:
    """
    Fetch top clips from Kick.
    targets: list of strings — prefix with @ for streamer, plain slug for category.
    e.g. ["just-chatting", "slots", "@xqc", "@trainwreckstv"]
    """
    session, using_tls = _get_session()
    if not using_tls:
        logger.warning("tls-client not installed — Kick requests may be blocked by Cloudflare. Run: pip install tls-client")

    clips = []

    for target in targets:
        target = target.strip()
        is_streamer = target.startswith("@")
        slug        = target.lstrip("@")

        if is_streamer:
            url    = f"{BASE}/channels/{slug}/clips"
            label  = f"streamer @{slug}"
        else:
            url    = f"{BASE}/categories/{slug}/clips"
            label  = f"category '{slug}'"

        params = {
            "time":     period,
            "page":     1,
            "per_page": min(limit, 20),
        }

        try:
            resp   = _get(session, using_tls, url, params)
            status = resp.status_code

            if status == 403:
                logger.error(f"Kick: Cloudflare blocked request for {label}. Make sure tls-client is installed.")
                continue
            if status != 200:
                logger.error(f"Kick API {status} for {label}: {resp.text[:200]}")
                continue

            try:
                data = resp.json()
            except Exception:
                logger.error(f"Kick: non-JSON response for {label}: {resp.text[:200]}")
                continue

            clip_list = data.get("clips", data) if isinstance(data, dict) else data
            if not isinstance(clip_list, list):
                logger.error(f"Kick: unexpected response shape for {label}: {str(data)[:200]}")
                continue

            fetched = 0
            for c in clip_list[:limit]:
                channel      = c.get("channel") or c.get("user") or {}
                streamer     = channel.get("username") or channel.get("slug") or slug
                download_url = c.get("clip_url") or c.get("video_url") or c.get("url") or ""
                clips.append({
                    "source":        "kick",
                    "clip_id":       f"kick_{c.get('id', c.get('uuid', ''))}",
                    "title":         c.get("title", "Untitled"),
                    "streamer":      streamer,
                    "game":          c.get("category", {}).get("name", slug) if isinstance(c.get("category"), dict) else slug,
                    "view_count":    c.get("views", c.get("view_count", 0)),
                    "duration":      c.get("duration", 0),
                    "clip_url":      c.get("clip_url") or download_url,
                    "download_url":  download_url,
                    "thumbnail_url": c.get("thumbnail_url", ""),
                })
                fetched += 1
            logger.info(f"Kick: fetched {fetched} clips for {label}")

        except Exception as e:
            logger.error(f"Kick fetch error for {label}: {e}")

    logger.info(f"Kick: {len(clips)} total clips across {len(targets)} target(s).")
    return clips