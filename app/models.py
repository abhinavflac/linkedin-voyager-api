"""Pydantic models for jobs and search results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


def _ms_to_datetime(ms: Optional[int]) -> Optional[datetime]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class Job(BaseModel):
    """A single LinkedIn job posting."""

    id: str
    title: str
    company: str = "Unknown"
    location: str = "Unknown"
    url: str = ""
    logo_url: str = ""
    listed_at: Optional[datetime] = None
    listed_at_ms: Optional[int] = None
    metadata: List[str] = Field(default_factory=list)
    metadata_text: str = ""

    def is_recent(self, max_age_minutes: int) -> bool:
        if self.listed_at is None:
            return False
        age = (datetime.now(timezone.utc) - self.listed_at).total_seconds()
        return age <= max_age_minutes * 60


class SearchQuery(BaseModel):
    """Parameters for a job search request."""

    keywords: str
    geo_id: int
    time_posted_range: str = "r86400"
    sort_by: str = "DD"
    count: int = 25
    start: int = 0


class SearchResult(BaseModel):
    """A page of job search results."""

    jobs: List[Job]
    total: int
    start: int
    count: int
