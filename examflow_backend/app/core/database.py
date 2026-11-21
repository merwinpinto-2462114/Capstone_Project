"""
EXAMFLOW – Async SQLAlchemy engine and session factory.
All database interactions use async sessions for concurrency safety.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ------------------------------------------------------------------ #
# Engine
# ------------------------------------------------------------------ #
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
)

# ------------------------------------------------------------------ #
# Session factory
# ------------------------------------------------------------------ #
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ------------------------------------------------------------------ #
# Declarative base
# ------------------------------------------------------------------ #
class Base(DeclarativeBase):
    """All ORM models inherit from this base."""
    pass


# ------------------------------------------------------------------ #
# Dependency
# ------------------------------------------------------------------ #
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency – yields a transactional async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
