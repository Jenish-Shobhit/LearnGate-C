from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from learngate.config import settings
from learngate.models import Base  # noqa: F401 — re-exported for convenience

__all__ = ["Base", "async_engine", "AsyncSessionLocal"]

async_engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=5)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)
