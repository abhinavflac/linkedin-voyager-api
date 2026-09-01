"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Authentication ---
    cookies_path: str = "cookies.json"
    # Alternative to cookies_path: the raw cookie JSON as a string. Useful on
    # Render/Heroku where there is no persistent filesystem to hold cookies.json.
    # Takes precedence over cookies_path when set.
    cookies_json: str = ""

    # --- Search ---
    keywords: List[str] = Field(
        default_factory=lambda: [
            "Data Analyst",
            "Data Analytics",
            "Data Scientist",
            "Business Analyst",
        ]
    )
    geo_id: int = 102713980  # India
    time_posted_range: str = "r86400"  # past 24 hours
    sort_by: str = "DD"  # date descending (newest first)
    count: int = 25  # results per page (LinkedIn max is 25)
    max_age_minutes: Optional[int] = None  # client-side "latest only" filter

    # Experience level filter (API-level). "1"=Internship, "2"=Entry level.
    # Empty list disables the filter.
    experience_levels: List[str] = Field(default_factory=lambda: ["1", "2"])

    # Client-side title filter. A job is kept only if its title contains ANY of
    # these substrings (case-insensitive). Empty list disables the filter.
    title_keywords: List[str] = Field(
        default_factory=lambda: ["analyst", "analytics", "data science", "data scientist"]
    )

    # --- Voyager API ---
    decoration_id: str = (
        "com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollection-220"
    )

    # --- Polling / alerts ---
    poll_interval_seconds: int = 300
    blacklisted_companies: List[str] = Field(
        default_factory=lambda: [
            "Skillzenloop",
            "Zenithbyte",
            "Wake Up Whistle",
            "SportsBUZZ",
            "Webs X UM",
            "WEBBOOST SOLUTION IT SERVICES",
            "Webs IT Solution",
            "Unified Mentor",
            "F6IT Fintech & IT Solutions",
            "internmo",
            "Dexter's Tech",
            "ArGo Intern",
        ]
    )

    # --- Storage ---
    sent_jobs_file: str = "sent_jobs.json"
    # Keep seen job IDs for this many days before pruning (bounds memory growth).
    dedup_retention_days: int = 7

    # --- Email (Gmail API via OAuth) ---
    sender_email: str = ""
    receiver_email: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    @field_validator("max_age_minutes", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        """Treat an empty env value (``MAX_AGE_MINUTES=``) as unset."""
        if value is None or value == "":
            return None
        return value

    @field_validator("experience_levels", "title_keywords", mode="before")
    @classmethod
    def _empty_list_to_empty(cls, value):
        """Treat an empty env value (``EXPERIENCE_LEVELS=``) as an empty list."""
        if value is None or value == "":
            return []
        return value

    @field_validator("dedup_retention_days", mode="before")
    @classmethod
    def _empty_retention_to_default(cls, value):
        """Treat an empty env value (``DEDUP_RETENTION_DAYS=``) as the default (7)."""
        if value is None or value == "":
            return 7
        return value

    @property
    def email_configured(self) -> bool:
        return bool(
            self.sender_email
            and self.gmail_client_id
            and self.gmail_client_secret
            and self.gmail_refresh_token
            and self.receiver_email
        )
