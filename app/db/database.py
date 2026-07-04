"""
Async database connection instance.

Uses the `databases` library which provides an async query interface on top
of SQLAlchemy Core.  The same DATABASE_URL works with:
  - aiosqlite   → development (SQLite)
  - asyncpg     → production  (PostgreSQL)

Usage
-----
  from app.db.database import database

  ### In FastAPI lifespan:
  - `await database.connect()`
  - `await database.disconnect()`

  ### In a service / repository:
  - `rows = await database.fetch_all(query)`
  - `row  = await database.fetch_one(query)`
  - `pk   = await database.execute(query)`
"""


from databases import Database
from app.core.config import settings

# ---------------------------------------------------------------------------
# Single shared connection pool for the entire application.
# ---------------------------------------------------------------------------
database = Database(settings.DATABASE_URL)