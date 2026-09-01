"""Job search over the LinkedIn Voyager API and response parsing."""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from .client import LinkedInVoyagerClient, VOYAGER_API
from .models import Job, SearchResult, _ms_to_datetime

logger = logging.getLogger(__name__)

JOB_CARDS_PATH = "/voyagerJobsDashJobCards"
LISTED_DATE_TYPE = "LISTED_DATE"
JOB_ID_RE = re.compile(r"fsd_jobPosting:(\d+)")
JOB_URL_TEMPLATE = "https://www.linkedin.com/jobs/view/{job_id}/"


def build_search_query(
    keywords: str,
    geo_id: int,
    time_posted_range: str = "r86400",
    sort_by: str = "DD",
    experience_levels: Optional[List[str]] = None,
) -> str:
    """Build the Rest.li ``query`` string LinkedIn's frontend sends.

    Spaces are ``%20``-encoded; parentheses/commas/colons stay literal to match
    the exact format the web app uses.

    ``experience_levels`` maps to the "Experience level" facet ("1"=Internship,
    "2"=Entry level, ...) and is applied server-side.
    """
    kw = urllib.parse.quote(keywords)
    filters = [f"sortBy:List({sort_by})", f"timePostedRange:List({time_posted_range})"]
    if experience_levels:
        filters.append(f"experience:List({','.join(experience_levels)})")
    return (
        f"(origin:JOB_SEARCH_PAGE_JOB_FILTER,"
        f"keywords:{kw},"
        f"locationUnion:(geoId:{geo_id}),"
        f"selectedFilters:({','.join(filters)}),"
        f"spellCorrectionEnabled:true)"
    )


def _text(value: Any) -> str:
    """Extract the text from a Voyager TextViewModelV2 dict."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _extract_logo(logo: Any) -> str:
    """Best-effort extraction of the company logo URL."""
    try:
        vec = logo["attributes"][0]["detailData"]["companyLogo"]["logo"]["vectorImage"]
        root = vec["rootUrl"]
        artifacts = vec.get("artifacts") or []
        if artifacts:
            return root + artifacts[0].get("fileIdentifyingUrlPathSegment", "")
        return root
    except (KeyError, IndexError, TypeError):
        return ""


def _extract_footer(footer_items: Any) -> tuple[Optional[int], List[str]]:
    """Return (listed_at_ms, [metadata strings]) from footerItems."""
    listed_at_ms: Optional[int] = None
    metadata: List[str] = []
    for item in footer_items or []:
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        if itype == LISTED_DATE_TYPE:
            listed_at_ms = item.get("timeAt") or listed_at_ms
            continue
        text = _text(item.get("text") or item.get("title") or item.get("content"))
        if text:
            metadata.append(text)
    return listed_at_ms, metadata


def _parse_job(card: Dict[str, Any]) -> Optional[Job]:
    try:
        title = _text(card.get("title"))
        if not title:
            return None

        company = _text(card.get("primaryDescription")) or "Unknown"
        location = _text(card.get("secondaryDescription")) or "Unknown"
        logo_url = _extract_logo(card.get("logo"))

        urn = card.get("jobPostingUrn") or card.get("entityUrn") or ""
        match = JOB_ID_RE.search(urn)
        job_id = match.group(1) if match else title
        url = JOB_URL_TEMPLATE.format(job_id=job_id)

        listed_at_ms, metadata = _extract_footer(card.get("footerItems"))

        return Job(
            id=job_id,
            title=title,
            company=company,
            location=location,
            url=url,
            logo_url=logo_url,
            listed_at=_ms_to_datetime(listed_at_ms),
            listed_at_ms=listed_at_ms,
            metadata=metadata,
            metadata_text=" · ".join(metadata),
        )
    except Exception as exc:  # never let one bad card break the whole page
        logger.debug("Failed to parse a job card: %s", exc)
        return None


def parse_job_cards(data: Dict[str, Any]) -> SearchResult:
    """Parse a ``voyagerJobsDashJobCards`` JSON response."""
    elements = data.get("elements") or []
    jobs: List[Job] = []
    for element in elements:
        union = element.get("jobCardUnion") or {}
        card = union.get("jobPostingCard") or {}
        job = _parse_job(card)
        if job:
            jobs.append(job)

    paging = data.get("paging") or {}
    return SearchResult(
        jobs=jobs,
        total=paging.get("total", len(jobs)),
        start=paging.get("start", 0),
        count=paging.get("count", len(jobs)),
    )


def search_jobs(
    client: LinkedInVoyagerClient,
    keywords: str,
    geo_id: int,
    time_posted_range: str = "r86400",
    sort_by: str = "DD",
    count: int = 25,
    start: int = 0,
    decoration_id: Optional[str] = None,
    experience_levels: Optional[List[str]] = None,
) -> SearchResult:
    """Search jobs and return a page of results.

    The URL is built manually (rather than via a ``params`` dict) so that the
    Rest.li query keeps its literal ``()``/``:``/``,`` characters, which is the
    exact format LinkedIn's frontend sends. Re-encoding them returns HTTP 400.
    """
    query = build_search_query(
        keywords, geo_id, time_posted_range, sort_by, experience_levels
    )
    deco = decoration_id or (
        "com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollection-220"
    )
    url = (
        f"{VOYAGER_API}{JOB_CARDS_PATH}"
        f"?decorationId={deco}&count={count}&q=jobSearch&query={query}&start={start}"
    )
    data = client.get_json(url)
    return parse_job_cards(data)
