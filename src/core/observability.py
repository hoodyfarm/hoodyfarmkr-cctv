import contextvars
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)


def get_correlation_id() -> str:
    return correlation_id_var.get()


def set_correlation_id(cid: Optional[str] = None) -> str:
    val = cid or f"req_{uuid.uuid4().hex[:12]}"
    correlation_id_var.set(val)
    return val


class StructuredJsonFormatter(logging.Formatter):
    """엔터프라이즈 원격 수집용 JSON 구조화 로그 포매터 (correlation_id 포함)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": get_correlation_id(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def render_prometheus_metrics(telemetry: Dict[str, Any], app_name: str = "hoodyfarmkr-cctv") -> str:
    """
    WorkerManager.get_telemetry() 결과를 Prometheus 텍스트 포맷으로 변환합니다.
    외부 의존성 없이 /metrics 엔드포인트에서 즉시 서빙 가능합니다.
    """
    farm_id = telemetry.get("farm_id", "default")
    ing = telemetry.get("ingestion_worker", {})
    inf = telemetry.get("inference_worker", {})
    evt = telemetry.get("event_worker", {})
    outbox = evt.get("outbox", {})
    cameras = telemetry.get("cameras", {})

    lines = [
        "# HELP cctv_frames_captured_total Total frames captured across cameras",
        "# TYPE cctv_frames_captured_total counter",
        f'cctv_frames_captured_total{{farm_id="{farm_id}"}} {int(ing.get("total_captured", 0))}',
        "# HELP cctv_camera_reconnects_total Total RTSP camera reconnect attempts",
        "# TYPE cctv_camera_reconnects_total counter",
        f'cctv_camera_reconnects_total{{farm_id="{farm_id}"}} {int(ing.get("reconnect_count", 0))}',
        "# HELP cctv_inferences_total Total YOLO inference executions",
        "# TYPE cctv_inferences_total counter",
        f'cctv_inferences_total{{farm_id="{farm_id}"}} {int(inf.get("total_inferences", 0))}',
        "# HELP cctv_events_saved_total Total events promoted from spool",
        "# TYPE cctv_events_saved_total counter",
        f'cctv_events_saved_total{{farm_id="{farm_id}"}} {int(inf.get("event_saved_count", 0))}',
        "# HELP cctv_anomalies_detected_total Total AI anomalies detected",
        "# TYPE cctv_anomalies_detected_total counter",
        f'cctv_anomalies_detected_total{{farm_id="{farm_id}"}} {int(inf.get("anomaly_count", 0))}',
        "# HELP cctv_clips_created_total Total MP4 clips encoded",
        "# TYPE cctv_clips_created_total counter",
        f'cctv_clips_created_total{{farm_id="{farm_id}"}} {int(evt.get("total_clips_created", 0))}',
        "# HELP cctv_webhooks_sent_total Total FMS webhooks delivered",
        "# TYPE cctv_webhooks_sent_total counter",
        f'cctv_webhooks_sent_total{{farm_id="{farm_id}"}} {int(evt.get("total_webhooks_sent", 0))}',
        "# HELP cctv_event_queue_size Current pending events in EventWorker queue",
        "# TYPE cctv_event_queue_size gauge",
        f'cctv_event_queue_size{{farm_id="{farm_id}"}} {int(evt.get("queue_size", 0))}',
        "# HELP cctv_outbox_events Total events in webhook outbox by status",
        "# TYPE cctv_outbox_events gauge",
        f'cctv_outbox_events{{farm_id="{farm_id}",status="pending"}} {int(outbox.get("pending", 0))}',
        f'cctv_outbox_events{{farm_id="{farm_id}",status="delivered"}} {int(outbox.get("delivered", 0))}',
        f'cctv_outbox_events{{farm_id="{farm_id}",status="dlq"}} {int(outbox.get("dlq", 0))}',
    ]

    if cameras:
        lines.append("# HELP cctv_camera_connected Whether each camera RTSP stream is connected (1/0)")
        lines.append("# TYPE cctv_camera_connected gauge")
        for cam_id, cam_data in cameras.items():
            cam_ing = cam_data.get("ingestion_worker", {})
            connected = 1 if cam_ing.get("is_connected") else 0
            lines.append(
                f'cctv_camera_connected{{farm_id="{farm_id}",camera_id="{cam_id}"}} {connected}'
            )

    return "\n".join(lines) + "\n"
