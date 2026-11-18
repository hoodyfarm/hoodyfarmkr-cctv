import pytest
import os
import time
from unittest.mock import patch
from src.services.storage_cleaner import StorageCleaner, DiskStorageGuard

def test_storage_cleaner_spool_and_events_retention(tmp_path):
    base_dir = str(tmp_path)
    cleaner = StorageCleaner(base_dir, spool_retention_minutes=1, event_retention_days=1, max_total_mb=1)
    
    os.makedirs(cleaner.spool_dir, exist_ok=True)
    os.makedirs(cleaner.events_dir, exist_ok=True)
    
    # Create old spool file
    old_spool = os.path.join(cleaner.spool_dir, "old_spool.jpg")
    with open(old_spool, "w") as f:
        f.write("dummy")
    # artificially set mtime to 2 minutes ago
    past_time = time.time() - 120
    os.utime(old_spool, (past_time, past_time))
    
    # Create fresh event file
    fresh_event = os.path.join(cleaner.events_dir, "event_1.jpg")
    with open(fresh_event, "w") as f:
        f.write("event_content")
        
    result = cleaner.run_cleanup_cycle()
    
    assert result["deleted_spool"] == 1
    assert not os.path.exists(old_spool)
    assert os.path.exists(fresh_event)

def test_storage_cleaner_root_spool_ttl_and_fifo_quota(tmp_path):
    base_dir = str(tmp_path)
    cleaner = DiskStorageGuard(base_dir, spool_retention_minutes=1, event_retention_days=7, max_total_mb=1)
    
    os.makedirs(cleaner.root_spool_dir, exist_ok=True)
    os.makedirs(cleaner.clips_dir, exist_ok=True)
    
    # Create root spool file
    root_spool = os.path.join(cleaner.root_spool_dir, "spool_frame.jpg")
    with open(root_spool, "wb") as f:
        f.write(b"x" * (400 * 1024))  # 400KB
    past_time = time.time() - 120
    os.utime(root_spool, (past_time, past_time))

    # Create 2 clips exceeding 1MB total
    clip1 = os.path.join(cleaner.clips_dir, "clip1.mp4")
    with open(clip1, "wb") as f:
        f.write(b"c" * (700 * 1024))  # 700KB
    t1 = time.time() - 60
    os.utime(clip1, (t1, t1))

    clip2 = os.path.join(cleaner.clips_dir, "clip2.mp4")
    with open(clip2, "wb") as f:
        f.write(b"c" * (700 * 1024))  # 700KB
    t2 = time.time()
    os.utime(clip2, (t2, t2))

    res = cleaner.run_cleanup_cycle()
    # root_spool should be deleted by TTL
    assert not os.path.exists(root_spool)
    # Total size was 1400KB > 1024KB max_total_mb, older clip1 should be purged by quota
    assert not os.path.exists(clip1)
    assert os.path.exists(clip2)
    assert res["deleted_by_quota"] >= 1

def test_disk_guard_emergency_fifo_cleanup(tmp_path):
    base_dir = str(tmp_path)
    cleaner = StorageCleaner(base_dir, min_free_percent=20.0, max_total_mb=100)

    os.makedirs(cleaner.spool_dir, exist_ok=True)
    os.makedirs(cleaner.events_dir, exist_ok=True)

    spool_file = os.path.join(cleaner.spool_dir, "spool.jpg")
    with open(spool_file, "w") as f:
        f.write("data")

    event_file = os.path.join(cleaner.events_dir, "event.jpg")
    with open(event_file, "w") as f:
        f.write("event_data")

    # Mock low disk space condition (5% free < 20% min threshold)
    # Then after 1 deletion, simulate disk space restored to 25%
    call_counts = 0
    def mock_free_percentage(*args, **kwargs):
        nonlocal call_counts
        call_counts += 1
        if call_counts == 1:
            return 5.0  # triggers guard
        elif call_counts == 2:
            return 8.0  # still below threshold, delete next
        return 25.0    # restored

    with patch.object(cleaner, "get_disk_free_percentage", side_effect=mock_free_percentage):
        del_guard = cleaner.enforce_disk_guard()
        assert del_guard >= 1
