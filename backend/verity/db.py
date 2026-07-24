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
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """Add columns introduced after a dev database was first created. SQLite
    only; a hosted Postgres starts fresh with the full schema. Real migrations
    (Alembic) come with hosting."""
    if not config.DATABASE_URL.startswith("sqlite"):
        return
    additions = {
        "source": "VARCHAR(16) DEFAULT 'arxiv'",
        "filename": "TEXT DEFAULT ''",
        "html_content": "TEXT DEFAULT ''",
    }
    # Columns removed from the model. The old html_path was NOT NULL with no DB
    # default, so leaving it would break inserts that no longer supply it.
    removals = ["html_path"]
    with engine.begin() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(documents)")}
        for column, ddl in additions.items():
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE documents ADD COLUMN {column} {ddl}")
        for column in removals:
            if column in existing:
                try:
                    conn.exec_driver_sql(f"ALTER TABLE documents DROP COLUMN {column}")
                except Exception:
                    pass


def get_session() -> Session:
    return SessionLocal()
