import pytest
import os
import time
from src.services.storage_cleaner import StorageCleaner

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
