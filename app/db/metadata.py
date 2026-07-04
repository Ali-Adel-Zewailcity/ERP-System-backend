"""
Shared SQLAlchemy MetaData object.

All schema files import this single MetaData instance so that
`metadata.create_all()` and Alembic's autogenerate both see the complete
set of tables in one place.
"""

from sqlalchemy import MetaData

# Naming convention makes Alembic generate deterministic constraint names,
# which is required for reliable ALTER TABLE migrations in PostgreSQL.
NAMING_CONVENTION: dict = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
