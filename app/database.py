from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


def create_database_engine():
    database_url = settings.database_url
    if database_url.startswith("sqlite"):
        return create_engine(database_url, connect_args={"check_same_thread": False})

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return engine
    except Exception:
        fallback_url = "sqlite:///./credit_card_agent.db"
        return create_engine(fallback_url, connect_args={"check_same_thread": False})


engine = create_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
