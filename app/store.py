"""Deduplication of already-seen job IDs with time-based retention."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)


class SeenJobs:
    """A thread-safe store of already-alerted job IDs.

    Each ID is kept with the time it was first seen, so stale entries can be
    pruned. The store lives in memory and is mirrored to a JSON file for local
    convenience. On platforms with ephemeral storage (e.g. Render free) it simply
    resets on redeploy — accepted by design.
    """

    def __init__(self, path: str | Path, retention_days: Optional[int] = None) -> None:
        self.path = Path(path)
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._seen: Dict[str, float] = self._load()
        if self.retention_days:
            self.prune()

    def _load(self) -> Dict[str, float]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read %s; starting fresh.", self.path)
            return {}

        if isinstance(data, dict):
            return {k: float(v) for k, v in data.items()}

        # Legacy format: a plain list of job IDs.
        now = time.time()
        return {str(x): now for x in data}

    def save(self) -> None:
        with self._lock:
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(self._seen, f)

    def is_new(self, job_id: str) -> bool:
        with self._lock:
            return job_id not in self._seen

    def mark(self, job_id: str) -> None:
        with self._lock:
            self._seen[job_id] = time.time()

    def mark_many(self, job_ids: Iterable[str]) -> None:
        now = time.time()
        with self._lock:
            for job_id in job_ids:
                self._seen[job_id] = now

    def prune(self) -> int:
        """Remove entries older than ``retention_days``.

        Returns the number of entries removed. No-op if ``retention_days`` is unset.
        """
        if not self.retention_days:
            return 0
        cutoff = time.time() - self.retention_days * 86400
        with self._lock:
            before = len(self._seen)
            self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}
            removed = before - len(self._seen)
        if removed:
            logger.debug("Pruned %d stale job IDs from the dedup store.", removed)
        return removed

    def __contains__(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._seen

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)
