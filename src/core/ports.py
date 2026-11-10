from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
import numpy as np

from src.domain.events.detection_event import DetectionEvent
from src.domain.events.event_envelope import CCTVEventEnvelopeV1


@runtime_checkable
class FrameSourcePort(Protocol):
    """카메라 프레임 수집 및 링 버퍼 조회 포트"""
    target_fps: float

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_latest_frame(self, timeout: float = 0.5) -> Optional[np.ndarray]: ...
    def get_buffered_frames_around(
        self, event_time: float, pre_sec: float = 3.0, post_sec: float = 3.0
    ) -> List[np.ndarray]: ...
    def get_recent_frames(self, count: int = 30) -> List[np.ndarray]: ...


@runtime_checkable
class VisionAnalyzerPort(Protocol):
    """멀티모달 AI 비전 정밀 판독 포트 (예: Gemini 2.5 Flash)"""

    def analyze_frame_structured(
        self, image_bytes: bytes, custom_prompt: Optional[str] = None
    ) -> Any: ...


@runtime_checkable
class ClipEncoderPort(Protocol):
    """프레임 시퀀스를 MP4 비디오 클립으로 인코딩하는 포트"""

    def encode_clip(
        self, frames: List[np.ndarray], tag: str = "event", fps: float = 5.0
    ) -> Optional[str]: ...


@runtime_checkable
class ObjectStoragePort(Protocol):
    """클라우드 오브젝트 스토리지(OCI 등) 업로드 포트"""

    def upload_file_to_oci(
        self,
        file_path: str,
        object_name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]: ...


@runtime_checkable
class WorkspaceSinkPort(Protocol):
    """외부 워크스페이스(Google Drive + Sheets 등) 아카이빙 포트"""

    def process_event_record(self, **kwargs: Any) -> Dict[str, Any]: ...


@runtime_checkable
class EventNotifierPort(Protocol):
    """
    FMS 등 외부 시스템으로 정식 이벤트 계약(CCTVEventEnvelopeV1)을 발송하는 포트.
    """

    def notify(self, envelope: CCTVEventEnvelopeV1) -> str: ...


@runtime_checkable
class EventPublisherPort(Protocol):
    """InferenceWorker가 EventWorker로 이벤트를 비동기 발행하는 포트"""

    def publish_event(self, event: DetectionEvent) -> bool: ...
