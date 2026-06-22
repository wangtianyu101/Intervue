from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect, text

from core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


# Lightweight schema migrations for dev/prod tables that already exist when
# a new column is added. Base.metadata.create_all() only creates missing
# tables — it does NOT alter existing ones, so an in-place upgrade path
# needs these explicit ALTERs.
#
# Keep this list flat and append-only. Each entry is (table, column, ddl).
# `applied` is filled at startup time and skipped on subsequent boots.
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("interviews", "is_favorite", "ALTER TABLE interviews ADD COLUMN is_favorite BOOLEAN DEFAULT 0"),
    ("interviews", "deleted_at", "ALTER TABLE interviews ADD COLUMN deleted_at DATETIME NULL"),
    ("reports", "summary", "ALTER TABLE reports ADD COLUMN summary TEXT NULL"),
    ("reports", "overall_score", "ALTER TABLE reports ADD COLUMN overall_score FLOAT NULL"),
]


async def _run_migrations():
    """Run ALTER TABLE migrations for any missing columns on existing tables.

    We don't introspect the schema up front (PRAGMA is SQLite-only, MySQL would
    need INFORMATION_SCHEMA). Instead, run the ALTER and swallow the
    "duplicate column" error — every dialect surfaces that as a clear message.
    """
    import logging
    log = logging.getLogger("codemock.migration")
    for _table, _col, ddl in _MIGRATIONS:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(ddl))
            log.info(f"migration applied: {ddl}")
        except Exception as e:
            msg = str(e).lower()
            # MySQL: 1060 "Duplicate column name"; SQLite: "duplicate column"
            if "duplicate" in msg or "1060" in msg:
                log.debug(f"migration already applied: {_table}.{_col}")
                continue
            log.warning(f"migration {_table}.{_col} failed: {e}")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_migrations()
