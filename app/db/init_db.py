"""
Database initialisation script.

Creates all tables defined in the SQLAlchemy Core metadata against the
configured database (SQLite for development, PostgreSQL for production).

Usage
-----
    python -m app.db.init_db

This script is safe to run multiple times - it uses `checkfirst=True`
so existing tables are never re-created or dropped.

WARNING
-------
  This script is for INITIAL SETUP only.  Once the project reaches a state
  where it has live data, use Alembic migrations instead:
      alembic upgrade head
"""

import asyncio
import logging

import sqlalchemy as sa

from app.core.config import settings
from app.db.metadata import metadata

from app.schema import *

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def _get_sync_engine() -> sa.Engine:
    """
    Build a *synchronous* SQLAlchemy engine from SYNC_DATABASE_URL.

    The `databases` library (used everywhere else in the app) is async-only.
    SQLAlchemy's create_all() is synchronous, so we use the sync engine here
    exclusively for schema creation.
    """
    sync_url = settings.SYNC_DATABASE_URL

    connect_args: dict = {}

    # SQLite-specific: allow the connection to be used across threads
    # (required by some SQLite versions when running create_all).
    if "sqlite" in sync_url:
        connect_args["check_same_thread"] = False

    engine = sa.create_engine(sync_url, connect_args=connect_args, echo=settings.DEBUG)
    return engine


def create_all_tables() -> None:
    """
    Create every table defined in the shared MetaData.

    Uses `checkfirst=True` so the operation is idempotent - safe to run on
    an already-initialised database without destroying data.
    """
    engine = _get_sync_engine()

    log.info("Target database: %s", settings.SYNC_DATABASE_URL)
    log.info("Tables registered in metadata: %s", list(metadata.tables.keys()))

    with engine.begin() as conn:
        metadata.create_all(bind=conn, checkfirst=True)

    table_count = len(metadata.tables)
    log.info("%d table(s) created / already exist.", table_count)

    engine.dispose()


if __name__ == "__main__":
    create_all_tables()
