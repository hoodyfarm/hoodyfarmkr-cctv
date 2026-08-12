from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.base import Base

class CCTVDevice(Base):
    """CCTV camera device metadata table."""
    __tablename__ = "cctv_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="SmartLife CCTV")
    host: Mapped[str] = mapped_column(String(50), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=80)
    rtsp_url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    frames: Mapped[List["FrameLog"]] = relationship("FrameLog", back_populates="device", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<CCTVDevice(id={self.id}, name='{self.name}', host='{self.host}')>"


class FrameLog(Base):
    """Captured frame metadata log table."""
    __tablename__ = "frame_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cctv_devices.id"), nullable=True)
    frame_path_oci: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    motion_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_keyframe: Mapped[bool] = mapped_column(Boolean, default=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    device: Mapped[Optional["CCTVDevice"]] = relationship("CCTVDevice", back_populates="frames")
    analysis_results: Mapped[List["AIAnalysisResult"]] = relationship("AIAnalysisResult", back_populates="frame_log", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FrameLog(id={self.id}, motion_score={self.motion_score:.2f}, captured_at='{self.captured_at}')>"


class AIAnalysisResult(Base):
    """Gemini 2.5 Flash AI Structured Analysis Result table."""
    __tablename__ = "ai_analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    frame_log_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("frame_logs.id"), nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str] = mapped_column(String(50), default="normal")  # normal, intrusion, motion_alert, etc.
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    detected_objects: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # JSON objects / labels
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    frame_log: Mapped[Optional["FrameLog"]] = relationship("FrameLog", back_populates="analysis_results")
    alerts: Mapped[List["AlertEvent"]] = relationship("AlertEvent", back_populates="analysis_result", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AIAnalysisResult(id={self.id}, event_type='{self.event_type}', is_anomaly={self.is_anomaly})>"


class AlertEvent(Base):
    """FMS Webhook Notification & Alert Event table."""
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_result_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_analysis_results.id"), nullable=True)
    alert_level: Mapped[str] = mapped_column(String(20), default="INFO")  # INFO, WARNING, CRITICAL
    webhook_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    analysis_result: Mapped[Optional["AIAnalysisResult"]] = relationship("AIAnalysisResult", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<AlertEvent(id={self.id}, level='{self.alert_level}', webhook_sent={self.webhook_sent})>"
