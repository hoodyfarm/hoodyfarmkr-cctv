import logging
from typing import Callable, List

logger = logging.getLogger(__name__)

class PipelineScheduler:
    """
    Background Task Scheduler for periodic CCTV sampling,
    OCI sync, and Gemini dataset extraction.
    """
    def __init__(self):
        self._running = False
        self._tasks: List[Callable] = []

    def add_task(self, task_func: Callable):
        self._tasks.append(task_func)

    def start(self):
        self._running = True
        logger.info("Pipeline scheduler started.")

    def stop(self):
        self._running = False
        logger.info("Pipeline scheduler stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

scheduler = PipelineScheduler()
