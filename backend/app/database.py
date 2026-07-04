"""
database.py — Supabase client initialisation.

Provides:
  - get_supabase_client()  → supabase.Client  (for table operations, auth, storage)
  - get_db_engine()        → sqlalchemy.Engine (for raw SQL / pgvector queries)
  - get_db_session()       → SQLAlchemy Session (FastAPI dependency)
"""

from functools import lru_cache
from typing import Generator

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from supabase import Client, create_client

from app.config import get_settings

log = structlog.get_logger(__name__)


# ── Supabase JS-style client (REST + realtime) ────────────────────────────────

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Returns a cached Supabase client using the SERVICE ROLE key.
    Used by agents and services that need full DB access (bypasses RLS).
    """
    settings = get_settings()
    log.info("Initialising Supabase service-role client", url=settings.supabase_url)
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@lru_cache(maxsize=1)
def get_supabase_anon_client() -> Client:
    """
    Returns a cached Supabase client using the ANON (public) key.
    Used for dashboard read-only queries that respect RLS.
    """
    settings = get_settings()
    log.info("Initialising Supabase anon client", url=settings.supabase_url)
    return create_client(settings.supabase_url, settings.supabase_anon_key)


# ── SQLAlchemy engine (direct Postgres / pgvector) ────────────────────────────

@lru_cache(maxsize=1)
def get_db_engine():
    """
    Returns a cached SQLAlchemy engine connected to the Supabase Postgres instance.
    Used for raw SQL, pgvector similarity queries, and bulk inserts.
    """
    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,       # validate connections before use
        pool_size=5,
        max_overflow=10,
        echo=settings.is_development,  # log SQL only in dev
    )
    log.info("SQLAlchemy engine created", database_url=settings.database_url[:40] + "…")
    return engine


@lru_cache(maxsize=1)
def _get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_db_engine(), autocommit=False, autoflush=False)


def get_db_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy session and ensures it is
    closed after the request, even on error.

    Usage:
        @router.get("/example")
        def example(db: Session = Depends(get_db_session)):
            ...
    """
    SessionLocal = _get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Health check helper ───────────────────────────────────────────────────────

def check_db_connection() -> bool:
    """
    Runs a trivial query to verify the Postgres connection is alive.
    Used by the /health endpoint.
    """
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log.error("Database health check failed", error=str(exc))
        return False
