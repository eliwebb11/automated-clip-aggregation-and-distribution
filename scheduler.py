"""
ClipSlop Scheduler — auto-fetch and auto-upload on a configurable interval.
"""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger     = logging.getLogger(__name__)
_scheduler = BackgroundScheduler(timezone="UTC")
_job_log   = []


def _log(event: str, detail: str = "", level: str = "info"):
    _job_log.insert(0, {
        "time":   datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "event":  event,
        "detail": detail,
        "level":  level,
    })
    if len(_job_log) > 50:
        _job_log.pop()
    logger.info(f"[Scheduler] {event}: {detail}")


def get_log() -> list:
    return list(_job_log)


def _save_clips(clips: list) -> int:
    from database import SessionLocal, Clip
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
    finally:
        db.close()
    return added


def run_pipeline():
    from database import SessionLocal, Clip, UploadLog, get_config
    from fetchers  import twitch as twitch_fetcher
    from fetchers  import kick   as kick_fetcher

    _log("Pipeline started", "Fetching clips...")

    db = SessionLocal()
    try:
        period          = get_config(db, "twitch_period",    "week")
        limit           = int(get_config(db, "max_clips_per_run", "10"))
        twitch_games    = [g for g in get_config(db, "twitch_games",    "").split(",") if g.strip()]
        kick_categories = [c for c in get_config(db, "kick_categories", "").split(",") if c.strip()]
        auto_youtube    = get_config(db, "upload_youtube", "true") == "true"
        auto_tiktok     = get_config(db, "upload_tiktok",  "true") == "true"
        auto_twitter    = get_config(db, "upload_twitter", "true") == "true"
    finally:
        db.close()

    new_clips = 0
    for platform, fetcher, categories in [
        ("Twitch", twitch_fetcher, twitch_games),
        ("Kick",   kick_fetcher,   kick_categories),
    ]:
        if not categories:
            continue
        try:
            clips      = fetcher.fetch_top_clips(categories, period=period, limit=limit)
            added      = _save_clips(clips)
            new_clips += added
            _log(f"{platform} fetch", f"{added} new clips added")
        except Exception as e:
            _log(f"{platform} fetch failed", str(e), level="error")

    _log("Fetch complete", f"{new_clips} new clips total")

    if not any([auto_youtube, auto_tiktok, auto_twitter]):
        _log("Auto-upload skipped", "All platforms disabled")
        return

    db = SessionLocal()
    try:
        ids = [c.id for c in db.query(Clip).filter(Clip.status == "approved").all()]
    finally:
        db.close()

    if not ids:
        _log("Auto-upload", "No approved clips in queue")
        return

    from downloader import download_clip, cleanup_clip
    from uploaders  import youtube as yt_uploader
    from uploaders  import tiktok  as tt_uploader
    from uploaders  import x       as x_uploader

    for clip_id in ids:
        db   = SessionLocal()
        clip = db.query(Clip).get(clip_id)
        db.close()
        if not clip:
            continue

        local_path = download_clip(clip.clip_url, clip.clip_id)
        if not local_path:
            _log("Download failed", f"clip #{clip_id}", level="error")
            continue

        title       = clip.upload_title or clip.title
        description = clip.upload_description or ""
        tags        = [t.strip() for t in (clip.upload_tags or "").split() if t.strip()]
        uploaded_to = []

        for platform, enabled, uploader, dest in [
            ("YouTube", auto_youtube, yt_uploader, "youtube"),
            ("TikTok",  auto_tiktok,  tt_uploader, "tiktok"),
            ("X",       auto_twitter, x_uploader,  "twitter"),
        ]:
            if not enabled or not uploader.is_authenticated():
                continue
            try:
                uploader.upload_video(local_path, title, description, tags)
                db = SessionLocal()
                db.add(UploadLog(clip_id=clip_id, destination=dest, status="success"))
                db.commit(); db.close()
                uploaded_to.append(platform)
            except Exception as e:
                db = SessionLocal()
                db.add(UploadLog(clip_id=clip_id, destination=dest, status="failed", error=str(e)))
                db.commit(); db.close()
                _log(f"{platform} upload failed", str(e), level="error")

        cleanup_clip(local_path)
        if uploaded_to:
            db = SessionLocal()
            clip = db.query(Clip).get(clip_id)
            clip.status = "done"
            db.commit(); db.close()
            _log("Uploaded", f"'{title[:40]}' → {', '.join(uploaded_to)}")

    _log("Pipeline complete", f"Processed {len(ids)} clips")


def get_status() -> dict:
    job = _scheduler.get_job("pipeline")
    return {
        "running":    _scheduler.running,
        "job_exists": job is not None,
        "next_run":   job.next_run_time.strftime("%Y-%m-%d %H:%M UTC") if job and job.next_run_time else None,
        "recent_log": get_log(),
    }


def start(interval_hours: int = 6):
    if not _scheduler.running:
        _scheduler.start()
    if _scheduler.get_job("pipeline"):
        _scheduler.remove_job("pipeline")
    _scheduler.add_job(
        run_pipeline,
        trigger=IntervalTrigger(hours=interval_hours),
        id="pipeline",
        replace_existing=True,
        misfire_grace_time=300,
    )
    _log("Scheduler started", f"Every {interval_hours}h")
    return get_status()


def stop():
    if _scheduler.get_job("pipeline"):
        _scheduler.remove_job("pipeline")
        _log("Scheduler stopped")
    return get_status()


def run_now():
    import threading
    threading.Thread(target=run_pipeline, daemon=True).start()
    _log("Manual run triggered")
    return get_status()


def shutdown():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
