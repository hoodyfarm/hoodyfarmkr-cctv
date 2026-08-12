import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.config import settings
from src.db.base import Base

logger = logging.getLogger(__name__)

# Database URL retrieval from Settings
DATABASE_URL = settings.get_database_url

# Create Async SQLAlchemy Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set True for SQL query debugging
    future=True,
    pool_pre_ping=True
)

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def init_db() -> bool:
    """
    Initialize database schemas and create tables asynchronously if they don't exist.
    """
    try:
        logger.info(f"Initializing PostgreSQL database tables via asyncpg...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ PostgreSQL database tables created/verified successfully!")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize PostgreSQL tables ({e}). (Ensure PostgreSQL container/server is running)")
        return False

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency injection yields async session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()
