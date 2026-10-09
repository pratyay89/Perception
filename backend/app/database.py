import warnings
from datetime import datetime, timezone

from sqlalchemy import DateTime, event
from sqlalchemy.exc import SAWarning
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import TypeDecorator

from app.config import settings


def normalize_database_url(url: str) -> str:
    """Accept the common URL spellings and return one an async driver understands."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("sqlite://"):
        url = "sqlite+aiosqlite://" + url[len("sqlite://") :]
    if url.startswith("postgresql+asyncpg://") and "sslmode=" in url:
        # asyncpg calls the option "ssl", libpq calls it "sslmode"
        url = url.replace("sslmode=", "ssl=")
    return url


db_url = normalize_database_url(settings.DATABASE_URL)
IS_SQLITE = db_url.startswith("sqlite")

engine_kwargs: dict = {"echo": settings.DATABASE_ECHO}
if not IS_SQLITE:
    engine_kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=10)

engine = create_async_engine(db_url, **engine_kwargs)

if IS_SQLITE:
    # SQLite stores NUMERIC as floating point. Marks are rounded to 2 decimals
    # everywhere, so the precision warning is not relevant here.
    warnings.filterwarnings(
        "ignore",
        message=".*does \\*not\\* support Decimal objects natively.*",
        category=SAWarning,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_enable_foreign_keys(dbapi_connection, _record):
        # SQLite ignores foreign keys (and ON DELETE CASCADE) unless asked.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class UTCDateTime(TypeDecorator):
    """A timezone-aware datetime that is always UTC when read back.

    PostgreSQL keeps the timezone, SQLite drops it. This makes both behave the
    same, so the API always returns timestamps with an explicit offset.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def init_models() -> None:
    """Create all tables that do not exist yet."""
    import app.auth.model  # noqa: F401
    import app.papers.model  # noqa: F401
    import app.submissions.model  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
