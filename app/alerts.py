"""Background polling loop that finds new jobs and sends alerts."""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional, Set

from .client import LinkedInVoyagerClient
from .config import Settings
from .models import Job
from .notifier import send_jobs_email
from .search import search_jobs
from .store import SeenJobs

logger = logging.getLogger(__name__)


def _is_blacklisted(job: Job, blacklist: List[str]) -> bool:
    company = job.company.lower()
    return any(b.lower() in company for b in blacklist)


def title_matches(title: str, title_keywords: List[str]) -> bool:
    """Return True if the title contains any of the configured substrings.

    Empty ``title_keywords`` disables the filter (keep everything).
    """
    if not title_keywords:
        return True
    t = title.lower()
    return any(k.lower() in t for k in title_keywords)


def apply_filters(
    jobs: List[Job],
    blacklist: List[str],
    max_age_minutes: Optional[int] = None,
    title_keywords: Optional[List[str]] = None,
) -> List[Job]:
    """Apply blacklist, max-age and title filters.

    This is the shared filter used by the alert loop, the CLI ``search`` command
    and the ``/jobs`` endpoint, so behaviour is consistent everywhere.
    """
    out: List[Job] = []
    for job in jobs:
        if _is_blacklisted(job, blacklist):
            continue
        if max_age_minutes and not job.is_recent(max_age_minutes):
            continue
        if title_keywords and not title_matches(job.title, title_keywords):
            continue
        out.append(job)
    return out


def _filter_new(
    jobs: List[Job],
    seen: SeenJobs,
    blacklist: List[str],
    max_age_minutes: Optional[int],
    title_keywords: Optional[List[str]],
) -> List[Job]:
    new_jobs: List[Job] = []
    for job in apply_filters(jobs, blacklist, max_age_minutes, title_keywords):
        if seen.is_new(job.id):
            new_jobs.append(job)
            seen.mark(job.id)
    return new_jobs


def scan_once(settings: Settings, client: LinkedInVoyagerClient, seen: SeenJobs) -> List[Job]:
    """Run a single pass over all configured keywords and return new jobs."""
    all_new: List[Job] = []
    for keyword in settings.keywords:
        try:
            result = search_jobs(
                client,
                keywords=keyword,
                geo_id=settings.geo_id,
                time_posted_range=settings.time_posted_range,
                sort_by=settings.sort_by,
                count=settings.count,
                decoration_id=settings.decoration_id,
                experience_levels=settings.experience_levels,
            )
            new_jobs = _filter_new(
                result.jobs,
                seen,
                settings.blacklisted_companies,
                settings.max_age_minutes,
                settings.title_keywords,
            )
            if new_jobs:
                logger.info("Found %d new job(s) for '%s'", len(new_jobs), keyword)
                all_new.extend(new_jobs)
        except Exception as exc:
            logger.error("Search failed for '%s': %s", keyword, exc)
    return all_new


def run_alert_loop(
    settings: Settings,
    *,
    client_factory: Optional[Callable[[], LinkedInVoyagerClient]] = None,
    stop_event=None,
    on_new_jobs: Optional[Callable[[List[Job]], None]] = None,
) -> None:
    """Run the alert loop forever (until ``stop_event`` is set)."""
    client = (
        client_factory()
        if client_factory
        else LinkedInVoyagerClient(settings.cookies_path, cookies_json=settings.cookies_json)
    )
    seen = SeenJobs(settings.sent_jobs_file, retention_days=settings.dedup_retention_days)
    logger.info("Alert loop started. Keywords: %s", settings.keywords)

    while stop_event is None or not stop_event.is_set():
        try:
            seen.prune()
            new_jobs = scan_once(settings, client, seen)
            if new_jobs:
                seen.save()
                if on_new_jobs:
                    on_new_jobs(new_jobs)
                if settings.email_configured:
                    send_jobs_email(
                        new_jobs,
                        settings.sender_email,
                        settings.receiver_email,
                        client_id=settings.gmail_client_id,
                        client_secret=settings.gmail_client_secret,
                        refresh_token=settings.gmail_refresh_token,
                    )
            else:
                logger.info("No new jobs this cycle.")
        except Exception as exc:
            logger.exception("Error in alert loop: %s", exc)

        time.sleep(settings.poll_interval_seconds)
