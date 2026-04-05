"""
X (Twitter) uploader using the Twitter API v2.
Docs: https://developer.twitter.com/en/docs/twitter-api/tweets/manage-tweets

Setup:
  1. Go to https://developer.twitter.com and create a project + app
  2. Enable OAuth 1.0a with Read & Write permissions
  3. Generate Access Token + Secret from the Developer Portal
  4. Paste all 4 keys into ClipSlop Settings

Video upload flow (Twitter chunked media upload):
  1. INIT   — register upload, get media_id
  2. APPEND — upload chunks
  3. FINALIZE — tell Twitter we're done
  4. STATUS  — poll until processing complete
  5. POST   — create tweet with media_id attached
"""
import os, time, math, logging, requests
from requests_oauthlib import OAuth1
from config import settings

logger = logging.getLogger(__name__)

UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_URL  = "https://api.twitter.com/2/tweets"
CHUNK_SIZE = 4 * 1024 * 1024   # 4 MB chunks


def _auth() -> OAuth1:
    return OAuth1(
        settings.TWITTER_API_KEY,
        settings.TWITTER_API_SECRET,
        settings.TWITTER_ACCESS_TOKEN,
        settings.TWITTER_ACCESS_TOKEN_SECRET,
    )

def is_authenticated() -> bool:
    return all([
        settings.TWITTER_API_KEY,
        settings.TWITTER_API_SECRET,
        settings.TWITTER_ACCESS_TOKEN,
        settings.TWITTER_ACCESS_TOKEN_SECRET,
    ])


def _media_upload_init(file_size: int, media_type: str = "video/mp4") -> str:
    """INIT phase — returns media_id_string."""
    resp = requests.post(
        UPLOAD_URL,
        data={
            "command":          "INIT",
            "media_type":       media_type,
            "media_category":   "tweet_video",
            "total_bytes":      file_size,
        },
        auth=_auth(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["media_id_string"]


def _media_upload_append(media_id: str, video_path: str):
    """APPEND phase — upload file in chunks."""
    file_size    = os.path.getsize(video_path)
    chunk_count  = math.ceil(file_size / CHUNK_SIZE)
    with open(video_path, "rb") as f:
        for i in range(chunk_count):
            chunk = f.read(CHUNK_SIZE)
            resp  = requests.post(
                UPLOAD_URL,
                data={
                    "command":       "APPEND",
                    "media_id":      media_id,
                    "segment_index": i,
                },
                files={"media": chunk},
                auth=_auth(),
                timeout=120,
            )
            if resp.status_code not in (200, 204):
                raise RuntimeError(f"X APPEND chunk {i} failed ({resp.status_code}): {resp.text[:200]}")
            logger.info(f"X: uploaded chunk {i+1}/{chunk_count}")


def _media_upload_finalize(media_id: str) -> dict:
    """FINALIZE phase — returns processing info."""
    resp = requests.post(
        UPLOAD_URL,
        data={"command": "FINALIZE", "media_id": media_id},
        auth=_auth(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _wait_for_processing(media_id: str, max_wait: int = 300):
    """Poll STATUS until video processing is complete."""
    waited = 0
    while waited < max_wait:
        resp = requests.get(
            UPLOAD_URL,
            params={"command": "STATUS", "media_id": media_id},
            auth=_auth(),
            timeout=15,
        )
        resp.raise_for_status()
        info  = resp.json().get("processing_info", {})
        state = info.get("state", "succeeded")

        logger.info(f"X processing state: {state} ({info.get('progress_percent', 0)}%)")

        if state == "succeeded":
            return
        if state == "failed":
            raise RuntimeError(f"X media processing failed: {info.get('error', {})}")

        wait = info.get("check_after_secs", 5)
        time.sleep(wait)
        waited += wait

    raise RuntimeError(f"X media processing timed out after {max_wait}s")


def _post_tweet(media_id: str, text: str) -> str:
    """Post a tweet with a video attached. Returns tweet ID."""
    payload = {
        "text":  text[:280],
        "media": {"media_ids": [media_id]},
    }
    resp = requests.post(
        TWEET_URL,
        json=payload,
        auth=_auth(),
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"X tweet post failed ({resp.status_code}): {resp.text[:300]}")
    tweet_id = resp.json()["data"]["id"]
    logger.info(f"X: tweet posted → https://x.com/i/status/{tweet_id}")
    return tweet_id


def upload_video(video_path: str, title: str, description: str = "", tags: list = None) -> str:
    """
    Upload a video to X (Twitter) as a tweet.
    Returns the tweet ID on success. Raises on failure.
    """
    if not is_authenticated():
        raise RuntimeError(
            "X is not authenticated. "
            "Add your API keys in Settings."
        )
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_size = os.path.getsize(video_path)

    # Build tweet text
    tag_str   = " ".join(f"#{t.lstrip('#')}" for t in (tags or []))
    tweet_text = f"{title}\n\n{tag_str}".strip()[:280]

    logger.info(f"X: starting upload for '{title}' ({file_size/1024/1024:.1f} MB)")

    # 1. INIT
    media_id = _media_upload_init(file_size)
    logger.info(f"X: media_id={media_id}")

    # 2. APPEND
    _media_upload_append(media_id, video_path)

    # 3. FINALIZE
    finalize_data = _media_upload_finalize(media_id)
    if "processing_info" in finalize_data:
        _wait_for_processing(media_id)

    # 4. POST tweet
    tweet_id = _post_tweet(media_id, tweet_text)
    return tweet_id
