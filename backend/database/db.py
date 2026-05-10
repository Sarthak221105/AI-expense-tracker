"""SQLAlchemy engine, session factory, and dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Session:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they don't exist."""
    from backend.database.models import User, Statement, Transaction, MonthlySummary  # noqa: F401
    Base.metadata.create_all(bind=engine)
