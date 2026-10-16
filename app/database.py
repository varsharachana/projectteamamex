import re
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


def normalize_database_url(database_url: str) -> str:
    if not database_url.startswith("sqlite"):
        return database_url

    if database_url == "sqlite:///:memory:":
        return database_url

    candidate = database_url.removeprefix("sqlite:///")
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", candidate):
        return database_url

    candidate = candidate.removeprefix("./")
    project_root = Path(__file__).resolve().parent.parent
    resolved_path = (project_root / candidate).resolve()
    return f"sqlite:///{resolved_path.as_posix()}"


def create_database_engine():
    database_url = normalize_database_url(settings.database_url)
    if database_url.startswith("sqlite"):
        return create_engine(database_url, connect_args={"check_same_thread": False})

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return engine
    except Exception:
        fallback_url = "sqlite:///./app.db"
        fallback_engine = create_engine(normalize_database_url(fallback_url), connect_args={"check_same_thread": False})
        return fallback_engine


engine = create_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_database_schema() -> None:
    with engine.begin() as connection:
        users_table = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        ).fetchone()
        if not users_table:
            return

        columns = connection.execute(text("PRAGMA table_info(users)")).fetchall()
        column_names = {column[1] for column in columns}

        if "name" not in column_names and "full_name" in column_names:
            connection.execute(text("ALTER TABLE users RENAME COLUMN full_name TO name"))
        if "last_login" not in column_names:
            connection.execute(text("ALTER TABLE users ADD COLUMN last_login DATETIME"))


ensure_database_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
