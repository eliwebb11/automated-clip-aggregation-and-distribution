from flask import Flask, render_template, jsonify, request
import os, threading, logging

import webview
import scheduler as sched
from config import settings
from database import init_db, SessionLocal, Clip, AppConfig, UploadLog, get_config, set_config
from fetchers import twitch as twitch_fetcher
from fetchers import kick   as kick_fetcher
from uploaders import youtube as yt_uploader
from uploaders import tiktok  as tt_uploader
from uploaders import x       as x_uploader
from downloader import download_clip, cleanup_clip

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Init ──────────────────────────────────────────────────────────────────────
init_db()

def _start_scheduler_from_db():
    db = SessionLocal()
    try:
        enabled  = get_config(db, "scheduler_enabled", "false") == "true"
        interval = int(get_config(db, "schedule_hours", "6"))
    finally:
        db.close()
    if enabled:
        sched.start(interval)
        logger.info(f"Scheduler auto-started: every {interval}h")

_start_scheduler_from_db()

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_stats():
    db = SessionLocal()
    try:
        return {
            "clips_fetched":  db.query(Clip).count(),
            "pending_review": db.query(Clip).filter(Clip.status == "pending").count(),
            "uploaded_today": db.query(Clip).filter(Clip.status == "done").count(),
            "total_uploads":  db.query(Clip).filter(Clip.status == "done").count(),
        }
    finally:
        db.close()

def save_clips_to_db(clips: list) -> int:
    db    = SessionLocal()
    added = 0
    try:
        for c in clips:
            if not db.query(Clip).filter_by(clip_id=c["clip_id"]).first():
                db.add(Clip(**{k: v for k, v in c.items() if k in [
                    "source","clip_id","title","streamer","game",
                    "view_count","duration","clip_url","download_url","thumbnail_url"
                ]}))
                added += 1
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Duplicate clip skipped: {e}")
    finally:
        db.close()
    return added

def save_keys_to_env(prefix: str, keys: dict):
    """Write key=value pairs to .env, removing old lines with the same prefix."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    lines    = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = [l for l in f.readlines() if not l.startswith(prefix)]
    for k, v in keys.items():
        lines.append(f"{k}={v}\n")
    with open(env_path, "w") as f:
        f.writelines(lines)
    from dotenv import load_dotenv
    load_dotenv(override=True)

# ── Page routes ───────────────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    twitch_ok = bool(settings.TWITCH_CLIENT_ID and settings.TWITCH_CLIENT_SECRET)
    if request.headers.get("X-Partial"):
        return jsonify({
            "active":         "dashboard",
            "page_title":     "Dashboard",
            "content":        render_template("partials/dashboard.html", stats=get_stats(), twitch_ok=twitch_ok),
            "topbar_actions": render_template("partials/topbar_dashboard.html"),
        })
    return render_template("index.html", stats=get_stats(), active="dashboard", twitch_ok=twitch_ok)

@app.route("/clips")
def clips():
    db = SessionLocal()
    try:
        all_clips = db.query(Clip).order_by(Clip.view_count.desc()).all()
        if request.headers.get("X-Partial"):
            return jsonify({
                "active":         "clips",
                "page_title":     "Clips",
                "content":        render_template("partials/clips.html", clips=all_clips),
                "topbar_actions": render_template("partials/topbar_clips.html"),
            })
        return render_template("clips.html", clips=all_clips, active="clips")
    finally:
        db.close()

@app.route("/queue")
def queue():
    db = SessionLocal()
    try:
        queued = db.query(Clip).filter(Clip.status == "approved").all()
        if request.headers.get("X-Partial"):
            return jsonify({
                "active":         "queue",
                "page_title":     "Upload Queue",
                "content":        render_template("partials/queue.html", queue=queued),
                "topbar_actions": render_template("partials/topbar_queue.html", queue=queued),
            })
        return render_template("queue.html", queue=queued, active="queue")
    finally:
        db.close()

@app.route("/history")
def history():
    db = SessionLocal()
    try:
        done = db.query(Clip).filter(Clip.status == "done").order_by(Clip.fetched_at.desc()).all()
        if request.headers.get("X-Partial"):
            return jsonify({
                "active":         "history",
                "page_title":     "Upload History",
                "content":        render_template("partials/history.html", history=done),
                "topbar_actions": "",
            })
        return render_template("history.html", history=done, active="history")
    finally:
        db.close()

@app.route("/settings")
def settings_page():
    db = SessionLocal()
    try:
        cfg = {row.key: row.value for row in db.query(AppConfig).all()}
        if request.headers.get("X-Partial"):
            return jsonify({
                "active":         "settings",
                "page_title":     "Settings",
                "content":        render_template("partials/settings.html", cfg=cfg),
                "topbar_actions": render_template("partials/topbar_settings.html"),
            })
        return render_template("settings.html", cfg=cfg, active="settings")
    finally:
        db.close()

# ── Stats ─────────────────────────────────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())

# ── Fetch clips ───────────────────────────────────────────────────────────────
@app.route("/api/fetch-clips", methods=["POST"])
def api_fetch_clips():
    db = SessionLocal()
    try:
        period          = get_config(db, "twitch_period",    "week")
        limit           = int(get_config(db, "max_clips_per_run", "20"))
        twitch_games    = [g for g in get_config(db, "twitch_games",    "").split(",") if g.strip()]
        kick_categories = [c for c in get_config(db, "kick_categories", "").split(",") if c.strip()]
    finally:
        db.close()

    new_clips, errors = 0, []

    if twitch_games:
        try:
            new_clips += save_clips_to_db(twitch_fetcher.fetch_top_clips(twitch_games, period=period, limit=limit))
        except Exception as e:
            errors.append(f"Twitch: {e}")

    if kick_categories:
        try:
            new_clips += save_clips_to_db(kick_fetcher.fetch_top_clips(kick_categories, period=period, limit=limit))
        except Exception as e:
            errors.append(f"Kick: {e}")

    return jsonify({"success": not errors, "new_clips": new_clips, "errors": errors, "stats": get_stats()})

# ── Clip management ───────────────────────────────────────────────────────────
@app.route("/api/clip/<int:clip_id>/approve", methods=["POST"])
def api_approve_clip(clip_id):
    db = SessionLocal()
    try:
        clip = db.query(Clip).get(clip_id)
        if not clip: return jsonify({"error": "Not found"}), 404
        clip.status = "approved"
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/clip/<int:clip_id>/reject", methods=["POST"])
def api_reject_clip(clip_id):
    db = SessionLocal()
    try:
        clip = db.query(Clip).get(clip_id)
        if not clip: return jsonify({"error": "Not found"}), 404
        clip.status = "skipped"
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/clip/<int:clip_id>/metadata", methods=["POST"])
def api_update_metadata(clip_id):
    data = request.get_json()
    db   = SessionLocal()
    try:
        clip = db.query(Clip).get(clip_id)
        if not clip: return jsonify({"error": "Not found"}), 404
        if "upload_title"       in data: clip.upload_title       = data["upload_title"]
        if "upload_description" in data: clip.upload_description = data["upload_description"]
        if "upload_tags"        in data: clip.upload_tags        = data["upload_tags"]
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/clip/<int:clip_id>/remove-queue", methods=["POST"])
def api_remove_from_queue(clip_id):
    db = SessionLocal()
    try:
        clip = db.query(Clip).get(clip_id)
        if not clip: return jsonify({"error": "Not found"}), 404
        clip.status = "pending"
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/queue/clear", methods=["POST"])
def api_clear_queue():
    db = SessionLocal()
    try:
        clips = db.query(Clip).filter(Clip.status == "approved").all()
        for c in clips: c.status = "pending"
        db.commit()
        return jsonify({"success": True, "cleared": len(clips)})
    finally:
        db.close()

# ── Settings ──────────────────────────────────────────────────────────────────
@app.route("/api/save-settings", methods=["POST"])
def api_save_settings():
    data = request.get_json()
    db   = SessionLocal()
    try:
        allowed = {
            "twitch_games","kick_categories","twitch_period",
            "max_clips_per_run","clip_max_duration",
            "upload_youtube","upload_tiktok","upload_twitter",
            "clip_title_template",
        }
        for key, value in data.items():
            if key in allowed:
                set_config(db, key, str(value))

        # Save Twitch keys to .env if provided
        twitch_id     = data.get("twitch_client_id", "").strip()
        twitch_secret = data.get("twitch_client_secret", "").strip()
        if twitch_id and twitch_secret:
            save_keys_to_env("TWITCH_", {
                "TWITCH_CLIENT_ID":     twitch_id,
                "TWITCH_CLIENT_SECRET": twitch_secret,
            })
            settings.TWITCH_CLIENT_ID     = twitch_id
            settings.TWITCH_CLIENT_SECRET = twitch_secret

        # Save Kick keys to .env if provided
        kick_id     = data.get("kick_client_id", "").strip()
        kick_secret = data.get("kick_client_secret", "").strip()
        if kick_id and kick_secret:
            save_keys_to_env("KICK_", {
                "KICK_CLIENT_ID":     kick_id,
                "KICK_CLIENT_SECRET": kick_secret,
            })
            settings.KICK_CLIENT_ID     = kick_id
            settings.KICK_CLIENT_SECRET = kick_secret
            if os.path.exists("kick_token.json"):
                os.remove("kick_token.json")

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()

# ── YouTube ───────────────────────────────────────────────────────────────────
@app.route("/api/auth/youtube", methods=["POST"])
def api_youtube_auth():
    try:
        return jsonify({"success": True, "message": yt_uploader.start_oauth_flow()})
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/auth/youtube/status")
def api_youtube_status():
    return jsonify({"authenticated": yt_uploader.is_authenticated()})

@app.route("/api/upload/youtube/<int:clip_id>", methods=["POST"])
def api_upload_youtube(clip_id):
    db = SessionLocal()
    try:
        clip = db.query(Clip).get(clip_id)
        if not clip: return jsonify({"error": "Not found"}), 404
        if not yt_uploader.is_authenticated(): return jsonify({"error": "YouTube not authenticated"}), 401
        clip.status = "uploading"; db.commit()
    finally:
        db.close()

    local_path = download_clip(clip.clip_url, clip.clip_id)
    if not local_path:
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        clip.status = "failed"; clip.error = "Download failed"; db.commit(); db.close()
        return jsonify({"error": "Download failed"}), 500

    try:
        title    = clip.upload_title or clip.title
        tags     = [t.strip().lstrip("#") for t in (clip.upload_tags or "").split() if t.strip()]
        video_id = yt_uploader.upload_video(local_path, title, clip.upload_description or "", tags)
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        db.add(UploadLog(clip_id=clip_id, destination="youtube", status="success", upload_id=video_id))
        clip.status = "done"; db.commit(); db.close()
        cleanup_clip(local_path)
        return jsonify({"success": True, "video_id": video_id, "url": f"https://youtube.com/shorts/{video_id}"})
    except Exception as e:
        cleanup_clip(local_path)
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        clip.status = "failed"; clip.error = str(e)
        db.add(UploadLog(clip_id=clip_id, destination="youtube", status="failed", error=str(e)))
        db.commit(); db.close()
        return jsonify({"error": str(e)}), 500

@app.route("/api/upload/youtube/all", methods=["POST"])
def api_upload_youtube_all():
    db = SessionLocal()
    try:
        ids = [c.id for c in db.query(Clip).filter(Clip.status == "approved").all()]
    finally:
        db.close()
    results = {"success": [], "failed": []}
    for cid in ids:
        res  = api_upload_youtube(cid)
        data = res.get_json() if hasattr(res, "get_json") else {}
        if data.get("success"): results["success"].append(cid)
        else: results["failed"].append({"id": cid, "error": data.get("error", "unknown")})
    return jsonify({"uploaded": len(results["success"]), "failed": len(results["failed"]), "details": results})

# ── TikTok ────────────────────────────────────────────────────────────────────
@app.route("/api/auth/tiktok/url")
def api_tiktok_oauth_url():
    try:
        return jsonify({"success": True, "url": tt_uploader.get_oauth_url()})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/auth/tiktok/callback")
def api_tiktok_callback():
    code = request.args.get("code")
    if not code: return "<h2>Error: no code from TikTok</h2>", 400
    try:
        tt_uploader.exchange_code_for_token(code)
        return "<html><body style='background:#080809;color:#53fc18;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh'><h2>✓ TikTok Connected! Close this tab.</h2></body></html>"
    except Exception as e:
        return f"<h2>Error: {e}</h2>", 500

@app.route("/api/auth/tiktok/token", methods=["POST"])
def api_tiktok_save_token():
    data         = request.get_json()
    access_token = data.get("access_token", "").strip()
    if not access_token: return jsonify({"success": False, "error": "Access token required"}), 400
    tt_uploader.save_token_from_settings(access_token, data.get("refresh_token", "").strip())
    return jsonify({"success": True})

@app.route("/api/auth/tiktok/status")
def api_tiktok_status():
    return jsonify({"authenticated": tt_uploader.is_authenticated()})

@app.route("/api/upload/tiktok/<int:clip_id>", methods=["POST"])
def api_upload_tiktok(clip_id):
    db = SessionLocal()
    try:
        clip = db.query(Clip).get(clip_id)
        if not clip: return jsonify({"error": "Not found"}), 404
        if not tt_uploader.is_authenticated(): return jsonify({"error": "TikTok not authenticated"}), 401
        clip.status = "uploading"; db.commit()
    finally:
        db.close()

    local_path = clip.local_path if (clip.local_path and os.path.exists(clip.local_path)) else download_clip(clip.clip_url, clip.clip_id)
    if not local_path:
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        clip.status = "failed"; clip.error = "Download failed"; db.commit(); db.close()
        return jsonify({"error": "Download failed"}), 500

    try:
        tags       = [t.strip() for t in (clip.upload_tags or "").split() if t.strip()]
        publish_id = tt_uploader.upload_video(local_path, clip.upload_title or clip.title, clip.upload_description or "", tags)
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        db.add(UploadLog(clip_id=clip_id, destination="tiktok", status="success", upload_id=publish_id))
        clip.status = "done"; db.commit(); db.close()
        cleanup_clip(local_path)
        return jsonify({"success": True, "publish_id": publish_id})
    except Exception as e:
        cleanup_clip(local_path)
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        clip.status = "failed"; clip.error = str(e)
        db.add(UploadLog(clip_id=clip_id, destination="tiktok", status="failed", error=str(e)))
        db.commit(); db.close()
        return jsonify({"error": str(e)}), 500

# ── X (Twitter) ───────────────────────────────────────────────────────────────
@app.route("/api/auth/x/status")
def api_x_status():
    return jsonify({"authenticated": x_uploader.is_authenticated()})

@app.route("/api/auth/x/save", methods=["POST"])
def api_x_save_keys():
    data = request.get_json()
    for key in ["api_key","api_secret","access_token","access_token_secret"]:
        if not data.get(key, "").strip():
            return jsonify({"success": False, "error": f"'{key}' is required"}), 400
    save_keys_to_env("TWITTER_", {
        "TWITTER_API_KEY":              data["api_key"],
        "TWITTER_API_SECRET":           data["api_secret"],
        "TWITTER_ACCESS_TOKEN":         data["access_token"],
        "TWITTER_ACCESS_TOKEN_SECRET":  data["access_token_secret"],
    })
    settings.TWITTER_API_KEY             = data["api_key"]
    settings.TWITTER_API_SECRET          = data["api_secret"]
    settings.TWITTER_ACCESS_TOKEN        = data["access_token"]
    settings.TWITTER_ACCESS_TOKEN_SECRET = data["access_token_secret"]
    return jsonify({"success": True})

@app.route("/api/upload/x/<int:clip_id>", methods=["POST"])
def api_upload_x(clip_id):
    db = SessionLocal()
    try:
        clip = db.query(Clip).get(clip_id)
        if not clip: return jsonify({"error": "Not found"}), 404
        if not x_uploader.is_authenticated(): return jsonify({"error": "X not authenticated"}), 401
        clip.status = "uploading"; db.commit()
    finally:
        db.close()

    local_path = clip.local_path if (clip.local_path and os.path.exists(clip.local_path)) else download_clip(clip.clip_url, clip.clip_id)
    if not local_path:
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        clip.status = "failed"; clip.error = "Download failed"; db.commit(); db.close()
        return jsonify({"error": "Download failed"}), 500

    try:
        tags     = [t.strip() for t in (clip.upload_tags or "").split() if t.strip()]
        tweet_id = x_uploader.upload_video(local_path, clip.upload_title or clip.title, clip.upload_description or "", tags)
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        db.add(UploadLog(clip_id=clip_id, destination="twitter", status="success", upload_id=tweet_id))
        clip.status = "done"; db.commit(); db.close()
        cleanup_clip(local_path)
        return jsonify({"success": True, "tweet_id": tweet_id, "url": f"https://x.com/i/status/{tweet_id}"})
    except Exception as e:
        cleanup_clip(local_path)
        db = SessionLocal(); clip = db.query(Clip).get(clip_id)
        clip.status = "failed"; clip.error = str(e)
        db.add(UploadLog(clip_id=clip_id, destination="twitter", status="failed", error=str(e)))
        db.commit(); db.close()
        return jsonify({"error": str(e)}), 500

# ── Kick auth ─────────────────────────────────────────────────────────────────
@app.route("/api/auth/kick/status")
def api_kick_status():
    return jsonify({"authenticated": kick_fetcher.is_authenticated()})

# ── Scheduler ─────────────────────────────────────────────────────────────────
@app.route("/api/scheduler/status")
def api_scheduler_status():
    return jsonify(sched.get_status())

@app.route("/api/scheduler/start", methods=["POST"])
def api_scheduler_start():
    data     = request.get_json() or {}
    interval = int(data.get("interval_hours", 6))
    db = SessionLocal()
    set_config(db, "scheduler_enabled", "true")
    set_config(db, "schedule_hours",    str(interval))
    db.close()
    return jsonify(sched.start(interval))

@app.route("/api/scheduler/stop", methods=["POST"])
def api_scheduler_stop():
    db = SessionLocal()
    set_config(db, "scheduler_enabled", "false")
    db.close()
    return jsonify(sched.stop())

@app.route("/api/scheduler/run-now", methods=["POST"])
def api_scheduler_run_now():
    return jsonify(sched.run_now())

@app.route("/api/scheduler/log")
def api_scheduler_log():
    return jsonify(sched.get_log())

# ── Entry point ───────────────────────────────────────────────────────────────
def run_flask():
    app.run(debug=False, port=5000, use_reloader=False)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    webview.create_window(
        title="ClipSlop",
        url="http://localhost:5000",
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
    )
    webview.start()
    sched.shutdown()
