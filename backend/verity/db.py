from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config

config.ensure_dirs()

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401

    models.Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
