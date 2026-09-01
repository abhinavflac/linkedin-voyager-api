"""FastAPI app and CLI entry point.

Usage:
    python -m app.main search "Data Analyst" --max-age 60
    python -m app.main loop
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import argparse
import logging
import threading
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .alerts import apply_filters, run_alert_loop, scan_once
from .client import LinkedInVoyagerClient
from .config import Settings
from .models import Job
from .search import search_jobs
from .store import SeenJobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

settings = Settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.keywords:
        thread = threading.Thread(
            target=run_alert_loop,
            args=(settings,),
            kwargs={"client_factory": get_client},
            daemon=True,
        )
        thread.start()
    yield


app = FastAPI(title="LinkedIn Voyager Job Alert API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client: Optional[LinkedInVoyagerClient] = None


def get_client() -> LinkedInVoyagerClient:
    global client
    if client is None:
        client = LinkedInVoyagerClient(
            settings.cookies_path, cookies_json=settings.cookies_json
        )
    return client


@app.api_route("/", methods=["GET", "HEAD"])
def read_root() -> dict:
    return {"message": "LinkedIn Voyager Job Alert API is running"}


@app.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict:
    """Liveness probe for uptime monitors (UptimeRobot etc.)."""
    return {"status": "ok"}


@app.get("/jobs", response_model=List[Job])
def get_jobs(
    keywords: str = Query(..., description="Comma-separated keywords"),
    geo_id: Optional[int] = None,
    time_posted_range: Optional[str] = None,
    max_age_minutes: Optional[int] = None,
    count: int = 25,
) -> List[Job]:
    jobs: List[Job] = []
    for keyword in [k.strip() for k in keywords.split(",") if k.strip()]:
        result = search_jobs(
            get_client(),
            keywords=keyword,
            geo_id=geo_id or settings.geo_id,
            time_posted_range=time_posted_range or settings.time_posted_range,
            sort_by=settings.sort_by,
            count=count,
            decoration_id=settings.decoration_id,
            experience_levels=settings.experience_levels,
        )
        for job in apply_filters(
            result.jobs,
            settings.blacklisted_companies,
            max_age_minutes,
            settings.title_keywords,
        ):
            jobs.append(job)
    return jobs


@app.get("/scan", response_model=List[Job])
def scan() -> List[Job]:
    seen = SeenJobs(settings.sent_jobs_file, retention_days=settings.dedup_retention_days)
    new_jobs = scan_once(settings, get_client(), seen)
    seen.save()
    return new_jobs


def _cmd_search(args: argparse.Namespace) -> None:
    c = LinkedInVoyagerClient(settings.cookies_path, cookies_json=settings.cookies_json)
    result = search_jobs(
        c,
        keywords=args.keywords,
        geo_id=args.geo_id or settings.geo_id,
        time_posted_range=args.time_posted_range or settings.time_posted_range,
        sort_by=settings.sort_by,
        count=args.count,
        decoration_id=settings.decoration_id,
        experience_levels=settings.experience_levels,
    )
    print(f"Total results: {result.total}")
    filtered = apply_filters(
        result.jobs,
        settings.blacklisted_companies,
        args.max_age,
        settings.title_keywords,
    )
    if len(filtered) != len(result.jobs):
        print(f"Filtered: showing {len(filtered)} of {len(result.jobs)} (blacklist + max-age + title).")
    for job in filtered:
        posted = job.listed_at.strftime("%Y-%m-%d %H:%M UTC") if job.listed_at else "?"
        print(f"- [{posted}] {job.title} @ {job.company} | {job.location} | {job.url}")
        print(f"    {job.metadata_text}")


def _cmd_loop(_: argparse.Namespace) -> None:
    run_alert_loop(settings)


def main() -> None:
    parser = argparse.ArgumentParser(prog="linkedin-voyager-api")
    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", help="Search jobs once")
    p_search.add_argument("keywords")
    p_search.add_argument("--geo-id", type=int, default=None)
    p_search.add_argument("--time-posted-range", default=None, help="e.g. r86400")
    p_search.add_argument("--max-age", type=int, default=None, help="only jobs newer than N minutes")
    p_search.add_argument("--count", type=int, default=25)
    p_search.set_defaults(func=_cmd_search)

    p_loop = sub.add_parser("loop", help="Run the alert loop")
    p_loop.set_defaults(func=_cmd_loop)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
