import json
import os
import sqlite3
import threading
import time
import logging
from typing import Any, Callable, Dict, List, Optional

from src.domain.events.event_envelope import CCTVEventEnvelopeV1

logger = logging.getLogger(__name__)


class WebhookOutbox:
    """
    로컬 영속 Outbox + Dead Letter Queue (SQLite 기반, 무설정 동작).
    - FMS 웹훅 발송 실패 시(네트워크 순단/FMS 재시작) 로컬 디스크 큐에 안전 보관
    - 지수 백오프(base_backoff_sec * 2^(attempts-1))로 재시도
    - max_attempts 초과 시 'dlq' 상태로 전환하여 유실 없이 감사/수동 재처리 지원
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        max_attempts: int = 5,
        base_backoff_sec: float = 5.0,
    ):
        if not db_path:
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            )
            outbox_dir = os.path.join(base_dir, "captures", "outbox")
            os.makedirs(outbox_dir, exist_ok=True)
            db_path = os.path.join(outbox_dir, "webhook_outbox.sqlite3")
        else:
            parent = os.path.dirname(os.path.abspath(db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)

        self.db_path = db_path
        self.max_attempts = max_attempts
        self.base_backoff_sec = base_backoff_sec
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_outbox (
                    event_id TEXT PRIMARY KEY,
                    farm_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outbox_status_retry ON webhook_outbox(status, next_retry_at)"
            )
            conn.commit()

    def enqueue(self, envelope: CCTVEventEnvelopeV1, error: str = "", initial_attempts: int = 1) -> None:
        """실패한 이벤트를 Outbox에 적재하거나 기존 레코드의 재시도 횟수를 갱신."""
        now = time.time()
        status = "dlq" if initial_attempts >= self.max_attempts else "pending"
        delay = self.base_backoff_sec * (2 ** max(initial_attempts - 1, 0))
        next_retry = now + delay
        payload_str = json.dumps(envelope.model_dump(), ensure_ascii=False)

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO webhook_outbox (
                    event_id, farm_id, camera_id, event_type, payload_json,
                    status, attempts, next_retry_at, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    status = excluded.status,
                    attempts = excluded.attempts,
                    next_retry_at = excluded.next_retry_at,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    envelope.event_id,
                    envelope.farm_id,
                    envelope.camera_id,
                    envelope.event_type,
                    payload_str,
                    status,
                    initial_attempts,
                    next_retry,
                    error,
                    now,
                    now,
                ),
            )
            conn.commit()

    def fetch_due(self, limit: int = 20, now: Optional[float] = None) -> List[Dict[str, Any]]:
        current = now if now is not None else time.time()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM webhook_outbox
                WHERE status = 'pending' AND next_retry_at <= ?
                ORDER BY next_retry_at ASC
                LIMIT ?
                """,
                (current, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_delivered(self, event_id: str) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE webhook_outbox SET status = 'delivered', updated_at = ? WHERE event_id = ?",
                (now, event_id),
            )
            conn.commit()

    def mark_failed(self, event_id: str, error: str) -> str:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT attempts FROM webhook_outbox WHERE event_id = ?", (event_id,)
            ).fetchone()
            if not row:
                return "not_found"
            attempts = int(row["attempts"]) + 1
            if attempts >= self.max_attempts:
                new_status = "dlq"
                next_retry = now
            else:
                new_status = "pending"
                delay = self.base_backoff_sec * (2 ** max(attempts - 1, 0))
                next_retry = now + delay
            conn.execute(
                """
                UPDATE webhook_outbox
                SET status = ?, attempts = ?, next_retry_at = ?, last_error = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (new_status, attempts, next_retry, error, now, event_id),
            )
            conn.commit()
            return new_status

    def requeue_dlq(self, limit: int = 50) -> int:
        """DLQ에 격리된 이벤트를 pending 상태로 되돌려 재처리를 예약합니다."""
        now = time.time()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE webhook_outbox
                SET status = 'pending', attempts = 0, next_retry_at = ?, updated_at = ?
                WHERE event_id IN (
                    SELECT event_id FROM webhook_outbox WHERE status = 'dlq' LIMIT ?
                )
                """,
                (now, now, limit),
            )
            conn.commit()
            return cur.rowcount

    def process_due(
        self,
        sender: Callable[[CCTVEventEnvelopeV1], str],
        limit: int = 20,
        now: Optional[float] = None,
    ) -> Dict[str, int]:
        """만기 도래한 pending 이벤트를 순회하며 재전송을 수행합니다."""
        due_items = self.fetch_due(limit=limit, now=now)
        delivered = 0
        retried = 0
        dlq_count = 0

        for item in due_items:
            event_id = item["event_id"]
            try:
                data = json.loads(item["payload_json"])
                envelope = CCTVEventEnvelopeV1.model_validate(data)
                res = sender(envelope)
                if "success" in res:
                    self.mark_delivered(event_id)
                    delivered += 1
                else:
                    new_state = self.mark_failed(event_id, res)
                    if new_state == "dlq":
                        dlq_count += 1
                    else:
                        retried += 1
            except Exception as e:
                new_state = self.mark_failed(event_id, str(e))
                if new_state == "dlq":
                    dlq_count += 1
                else:
                    retried += 1

        return {
            "processed": len(due_items),
            "delivered": delivered,
            "retried": retried,
            "dlq": dlq_count,
        }

    def get_stats(self) -> Dict[str, int]:
        counts = {"pending": 0, "delivered": 0, "dlq": 0}
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM webhook_outbox GROUP BY status"
            ).fetchall()
            for r in rows:
                st = r["status"]
                if st in counts:
                    counts[st] = int(r["cnt"])
        return counts
