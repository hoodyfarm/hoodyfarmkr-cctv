from datetime import datetime, timezone
from typing import Optional, List, Any
from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CCTVDevice(Base):
    """CCTV camera device metadata table (multi-farm aware)."""
    __tablename__ = "cctv_devices"
    __table_args__ = (
        Index("ix_cctv_devices_farm_camera", "farm_id", "camera_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, default="cam_01")
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="SmartLife CCTV")
    host: Mapped[str] = mapped_column(String(50), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=80)
    rtsp_url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    # Relationships
    frames: Mapped[List["FrameLog"]] = relationship("FrameLog", back_populates="device", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<CCTVDevice(id={self.id}, name='{self.name}', host='{self.host}')>"


class FrameLog(Base):
    """Captured frame metadata log table."""
    __tablename__ = "frame_logs"
    __table_args__ = (
        Index("ix_frame_logs_farm_captured", "farm_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, default="cam_01")
    device_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cctv_devices.id"), nullable=True)
    frame_path_oci: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    motion_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_keyframe: Mapped[bool] = mapped_column(Boolean, default=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    # Relationships
    device: Mapped[Optional["CCTVDevice"]] = relationship("CCTVDevice", back_populates="frames")
    analysis_results: Mapped[List["AIAnalysisResult"]] = relationship("AIAnalysisResult", back_populates="frame_log", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FrameLog(id={self.id}, motion_score={self.motion_score:.2f}, captured_at='{self.captured_at}')>"


class AIAnalysisResult(Base):
    """Gemini 2.5 Flash AI Structured Analysis Result table."""
    __tablename__ = "ai_analysis_results"
    __table_args__ = (
        Index("ix_ai_analysis_farm_event", "farm_id", "event_type", "analyzed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, default="cam_01")
    frame_log_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("frame_logs.id"), nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str] = mapped_column(String(50), default="normal")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    detected_objects: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    # Relationships
    frame_log: Mapped[Optional["FrameLog"]] = relationship("FrameLog", back_populates="analysis_results")
    alerts: Mapped[List["AlertEvent"]] = relationship("AlertEvent", back_populates="analysis_result", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AIAnalysisResult(id={self.id}, event_type='{self.event_type}', is_anomaly={self.is_anomaly})>"


class AlertEvent(Base):
    """FMS Webhook Notification & Alert Event table."""
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_farm_created", "farm_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    analysis_result_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_analysis_results.id"), nullable=True)
    alert_level: Mapped[str] = mapped_column(String(20), default="INFO")
    webhook_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    # Relationships
    analysis_result: Mapped[Optional["AIAnalysisResult"]] = relationship("AIAnalysisResult", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<AlertEvent(id={self.id}, level='{self.alert_level}', webhook_sent={self.webhook_sent})>"
