"""
PostgreSQL Database Package for hoodyfarmkr-cctv.
Uses SQLAlchemy 2.0 (asyncio) and asyncpg.
"""
from src.db.base import Base
from src.db.session import engine, AsyncSessionLocal, init_db, get_db
from src.db.models import CCTVDevice, FrameLog, AIAnalysisResult, AlertEvent

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "init_db",
    "get_db",
    "CCTVDevice",
    "FrameLog",
    "AIAnalysisResult",
    "AlertEvent",
]
