from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Clip(Base):
    __tablename__ = "clips"

    id                 = Column(Integer, primary_key=True, index=True)
    source             = Column(String, nullable=False)
    clip_id            = Column(String, unique=True, index=True)
    title              = Column(String)
    streamer           = Column(String)
    game               = Column(String)
    view_count         = Column(Integer, default=0)
    duration           = Column(Float, default=0)
    clip_url           = Column(String)
    download_url       = Column(String)
    thumbnail_url      = Column(String)
    local_path         = Column(String, nullable=True)
    status             = Column(String, default="pending")
    error              = Column(Text, nullable=True)
    fetched_at         = Column(DateTime, default=datetime.utcnow)
    upload_title       = Column(String, nullable=True)
    upload_description = Column(Text, nullable=True)
    upload_tags        = Column(String, nullable=True)

    uploads = relationship("UploadLog", back_populates="clip")


class UploadLog(Base):
    __tablename__ = "upload_logs"

    id          = Column(Integer, primary_key=True, index=True)
    clip_id     = Column(Integer, ForeignKey("clips.id"))
    destination = Column(String)
    status      = Column(String)
    upload_id   = Column(String, nullable=True)
    error       = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    clip = relationship("Clip", back_populates="uploads")


class AppConfig(Base):
    __tablename__ = "app_config"

    id    = Column(Integer, primary_key=True)
    key   = Column(String, unique=True, index=True)
    value = Column(Text)


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    defaults = {
        "twitch_games":       "Just Chatting, IRL",
        "kick_categories":    "slots, just-chatting, irl",
        "schedule_hours":     str(settings.SCHEDULE_HOURS),
        "max_clips_per_run":  str(settings.MAX_CLIPS_PER_RUN),
        "clip_max_duration":  str(settings.CLIP_MAX_DURATION),
        "upload_youtube":     "true",
        "upload_tiktok":      "true",
        "upload_twitter":     "true",
        "twitch_period":      "week",
        "scheduler_enabled":  "false",
        "clip_title_template": "{title} | {streamer} #Shorts #Gaming",
    }
    for k, v in defaults.items():
        if not db.query(AppConfig).filter_by(key=k).first():
            db.add(AppConfig(key=k, value=v))
    db.commit()
    db.close()


def get_config(db, key: str, fallback: str = "") -> str:
    row = db.query(AppConfig).filter_by(key=key).first()
    return row.value if row else fallback


def set_config(db, key: str, value: str):
    row = db.query(AppConfig).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.add(AppConfig(key=key, value=value))
    db.commit()
