import os
import time
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StorageCleaner:
    """
    3500X 관리사 PC 디스크 용량 폭주 방지 롤링 청소기.
    - captures/spool/ (임시 프레임 대기소): 기본 30분 이상 경과 시 자동 삭제
    - captures/events/ 및 clips/: 최대 보관 기간 (기본 7일) 초과 시 자동 정리
    - 폴더 총 용량이 max_total_mb (기본 2GB) 초과 시 가장 오래된 파일부터 FIFO 삭제
    """

    def __init__(
        self,
        base_dir: str,
        spool_retention_minutes: int = 30,
        event_retention_days: int = 7,
        max_total_mb: int = 2048
    ):
        self.base_dir = base_dir
        self.spool_dir = os.path.join(base_dir, "captures", "spool")
        self.events_dir = os.path.join(base_dir, "captures", "events")
        self.clips_dir = os.path.join(base_dir, "captures", "clips")
        self.frames_dir = os.path.join(base_dir, "captures", "frames")  # 레거시 폴더 호환
        
        self.spool_ttl_sec = spool_retention_minutes * 60
        self.event_ttl_sec = event_retention_days * 86400
        self.max_bytes = max_total_mb * 1024 * 1024

    def clean_spool(self) -> int:
        """임시 spool 폴더에서 TTL 경과된 파일 삭제"""
        return self._clean_dir_by_age(self.spool_dir, self.spool_ttl_sec)

    def clean_legacy_frames(self) -> int:
        """기존 frames 폴더에서 1시간 이상 된 파일 정리"""
        return self._clean_dir_by_age(self.frames_dir, 3600)

    def clean_events(self) -> int:
        """중요 events 및 clips 폴더에서 보관 기간 경과된 파일 삭제"""
        deleted = 0
        deleted += self._clean_dir_by_age(self.events_dir, self.event_ttl_sec)
        deleted += self._clean_dir_by_age(self.clips_dir, self.event_ttl_sec)
        return deleted

    def enforce_size_limit(self) -> int:
        """전체 captures 용량 점검 및 초과 시 오래된 파일 선입선출(FIFO) 정리"""
        all_files = []
        total_size = 0

        for d in [self.spool_dir, self.frames_dir, self.clips_dir, self.events_dir]:
            if not os.path.exists(d):
                continue
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    try:
                        st = os.stat(p)
                        all_files.append((p, st.st_size, st.st_mtime))
                        total_size += st.st_size
                    except OSError:
                        pass

        if total_size <= self.max_bytes:
            return 0

        # 오래된 순으로 정렬 (mtime 오름차순)
        # 단, events/ 폴더 파일은 우선순위를 뒤로 미룸 (spool/frames 우선 삭제)
        def sort_priority(item):
            path, size, mtime = item
            is_event = "events" in path
            return (1 if is_event else 0, mtime)

        all_files.sort(key=sort_priority)

        deleted_count = 0
        for p, size, _ in all_files:
            if total_size <= self.max_bytes:
                break
            try:
                os.remove(p)
                total_size -= size
                deleted_count += 1
            except OSError:
                pass

        if deleted_count > 0:
            logger.info(f"StorageCleaner: Size limit exceeded. Purged {deleted_count} oldest files.")
        return deleted_count

    def run_cleanup_cycle(self) -> Dict[str, Any]:
        """주기적 종합 청소 사이클 실행"""
        del_spool = self.clean_spool()
        del_legacy = self.clean_legacy_frames()
        del_events = self.clean_events()
        del_limit = self.enforce_size_limit()
        
        total_deleted = del_spool + del_legacy + del_events + del_limit
        if total_deleted > 0:
            logger.info(f"StorageCleaner: Cleaned {total_deleted} files (spool: {del_spool}, legacy: {del_legacy}, events: {del_events}, quota: {del_limit})")

        return {
            "deleted_spool": del_spool,
            "deleted_legacy": del_legacy,
            "deleted_events": del_events,
            "deleted_by_quota": del_limit,
            "total_deleted": total_deleted
        }

    def _clean_dir_by_age(self, target_dir: str, ttl_sec: float) -> int:
        if not os.path.exists(target_dir):
            return 0
        now = time.time()
        deleted = 0
        for f in os.listdir(target_dir):
            p = os.path.join(target_dir, f)
            if os.path.isfile(p):
                try:
                    if now - os.path.getmtime(p) > ttl_sec:
                        os.remove(p)
                        deleted += 1
                except OSError:
                    pass
        return deleted
