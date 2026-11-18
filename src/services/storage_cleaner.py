import os
import shutil
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class StorageCleaner:
    """
    3500X 관리사 PC 디스크 용량 폭주 방지 롤링 청소기 및 DiskStorageGuard.
    - captures/spool/ 및 root spool/: 기본 30분(또는 설정치) 이상 경과 시 자동 회수
    - captures/events/ 및 clips/: 최대 보관 기간 (기본 7일) 초과 시 자동 정리
    - captures/frames/ (레거시): 1시간 이상 경과 시 자동 정리
    - 폴더 총 용량이 max_total_mb (기본 2GB) 초과 시 가장 오래된 파일부터 FIFO 삭제
    - 시스템 디스크 여유 공간이 min_free_percent (기본 10%) 미만 도달 시 오래된 미디어부터 FIFO 긴급 회수
    """

    def __init__(
        self,
        base_dir: str,
        spool_retention_minutes: int = 30,
        event_retention_days: int = 7,
        max_total_mb: int = 2048,
        min_free_percent: float = 10.0,
    ):
        self.base_dir = base_dir
        self.spool_dir = os.path.join(base_dir, "captures", "spool")
        self.root_spool_dir = os.path.join(base_dir, "spool")
        self.events_dir = os.path.join(base_dir, "captures", "events")
        self.clips_dir = os.path.join(base_dir, "captures", "clips")
        self.frames_dir = os.path.join(base_dir, "captures", "frames")  # 레거시 폴더 호환
        
        self.spool_ttl_sec = spool_retention_minutes * 60
        self.event_ttl_sec = event_retention_days * 86400
        self.max_bytes = max_total_mb * 1024 * 1024
        self.min_free_percent = min_free_percent

    def get_disk_free_percentage(self, path: Optional[str] = None) -> float:
        """지정 경로 또는 base_dir이 속한 파일 시스템의 남은 디스크 용량 비율(%) 반환"""
        target = path or self.base_dir
        try:
            usage = shutil.disk_usage(target)
            if usage.total == 0:
                return 100.0
            return (usage.free / usage.total) * 100.0
        except OSError as e:
            logger.warning(f"StorageCleaner: Could not read disk usage for '{target}': {e}")
            return 100.0

    def clean_spool(self) -> int:
        """임시 spool 폴더에서 TTL 경과된 파일 삭제"""
        deleted = self._clean_dir_by_age(self.spool_dir, self.spool_ttl_sec)
        deleted += self._clean_dir_by_age(self.root_spool_dir, self.spool_ttl_sec)
        return deleted

    def clean_legacy_frames(self) -> int:
        """기존 frames 폴더에서 1시간 이상 된 파일 정리"""
        return self._clean_dir_by_age(self.frames_dir, 3600)

    def clean_events(self) -> int:
        """중요 events 및 clips 폴더에서 보관 기간 경과된 파일 삭제"""
        deleted = 0
        deleted += self._clean_dir_by_age(self.events_dir, self.event_ttl_sec)
        deleted += self._clean_dir_by_age(self.clips_dir, self.event_ttl_sec)
        return deleted

    def _collect_managed_files(self):
        """정리 대상 디렉터리의 모든 파일 목록 및 크기 수집"""
        all_files = []
        total_size = 0
        target_dirs = [
            self.spool_dir,
            self.root_spool_dir,
            self.frames_dir,
            self.clips_dir,
            self.events_dir,
        ]

        for d in target_dirs:
            if not os.path.exists(d):
                continue
            for root, _, files in os.walk(d):
                for f in files:
                    p = os.path.join(root, f)
                    if os.path.isfile(p):
                        try:
                            st = os.stat(p)
                            all_files.append((p, st.st_size, st.st_mtime))
                            total_size += st.st_size
                        except OSError:
                            pass

        # 오래된 순으로 정렬 (mtime 오름차순)
        # spool, frames 폴더를 events/clips보다 우선 삭제하도록 가중치 적용
        def sort_priority(item):
            path, size, mtime = item
            is_important = ("events" in path) or ("clips" in path)
            return (1 if is_important else 0, mtime)

        all_files.sort(key=sort_priority)
        return all_files, total_size

    def enforce_size_limit(self) -> int:
        """전체 captures 및 spool 용량 점검 및 max_total_mb 초과 시 선입선출(FIFO) 정리"""
        all_files, total_size = self._collect_managed_files()

        if total_size <= self.max_bytes:
            return 0

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

    def enforce_disk_guard(self) -> int:
        """디스크 잔여 용량 %가 min_free_percent 미만일 때 오래된 파일 긴급 FIFO 정리"""
        free_pct = self.get_disk_free_percentage()
        if free_pct >= self.min_free_percent:
            return 0

        logger.warning(
            f"StorageCleaner: Low disk space detected ({free_pct:.1f}% free < {self.min_free_percent}% threshold). "
            f"Enforcing DiskStorageGuard FIFO purge."
        )

        all_files, _ = self._collect_managed_files()
        deleted_count = 0

        for p, _, _ in all_files:
            if self.get_disk_free_percentage() >= self.min_free_percent:
                break
            try:
                os.remove(p)
                deleted_count += 1
            except OSError:
                pass

        if deleted_count > 0:
            logger.info(f"StorageCleaner: DiskStorageGuard freed {deleted_count} files to restore disk threshold.")
        return deleted_count

    def run_cleanup_cycle(self) -> Dict[str, Any]:
        """주기적 종합 청소 사이클 실행"""
        del_spool = self.clean_spool()
        del_legacy = self.clean_legacy_frames()
        del_events = self.clean_events()
        del_limit = self.enforce_size_limit()
        del_disk_guard = self.enforce_disk_guard()
        
        total_deleted = del_spool + del_legacy + del_events + del_limit + del_disk_guard
        free_pct = self.get_disk_free_percentage()
        if total_deleted > 0:
            logger.info(
                f"StorageCleaner: Cleaned {total_deleted} files "
                f"(spool: {del_spool}, legacy: {del_legacy}, events: {del_events}, "
                f"quota: {del_limit}, disk_guard: {del_disk_guard}, free_disk: {free_pct:.1f}%)"
            )

        return {
            "deleted_spool": del_spool,
            "deleted_legacy": del_legacy,
            "deleted_events": del_events,
            "deleted_by_quota": del_limit,
            "deleted_by_disk_guard": del_disk_guard,
            "total_deleted": total_deleted,
            "disk_free_percent": round(free_pct, 2),
        }

    def _clean_dir_by_age(self, target_dir: str, ttl_sec: float) -> int:
        if not os.path.exists(target_dir):
            return 0
        now = time.time()
        deleted = 0
        for root, _, files in os.walk(target_dir):
            for f in files:
                p = os.path.join(root, f)
                if os.path.isfile(p):
                    try:
                        if now - os.path.getmtime(p) > ttl_sec:
                            os.remove(p)
                            deleted += 1
                    except OSError:
                        pass
        return deleted


# Alias to satisfy DiskStorageGuard domain naming
DiskStorageGuard = StorageCleaner
