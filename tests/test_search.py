"""Unit tests for query building and response parsing (no network)."""

from __future__ import annotations

import datetime
import time

from app.models import Job
from app.search import (
    _extract_footer,
    _extract_logo,
    _text,
    build_search_query,
    parse_job_cards,
)
from app.alerts import apply_filters, title_matches
from app.store import SeenJobs


def test_build_search_query():
    q = build_search_query("Data Analyst", 102713980, "r86400", "DD")
    assert "keywords:Data%20Analyst" in q
    assert "geoId:102713980" in q
    assert "sortBy:List(DD)" in q
    assert "timePostedRange:List(r86400)" in q
    # parentheses/commas/colons must stay literal
    assert "selectedFilters:(sortBy:List(DD),timePostedRange:List(r86400))" in q


def test_text_helper():
    assert _text({"text": "  Hello  "}) == "Hello"
    assert _text("plain") == "plain"
    assert _text(None) == ""


def test_extract_logo():
    logo = {
        "attributes": [
            {
                "detailData": {
                    "companyLogo": {
                        "logo": {
                            "vectorImage": {
                                "rootUrl": "https://media.licdn.com/dms/company-logo_",
                                "artifacts": [
                                    {"fileIdentifyingUrlPathSegment": "100_100/foo.png"}
                                ],
                            }
                        }
                    }
                }
            }
        ]
    }
    assert _extract_logo(logo) == "https://media.licdn.com/dms/company-logo_100_100/foo.png"
    assert _extract_logo(None) == ""


def test_extract_footer():
    footer = [
        {"type": "LISTED_DATE", "timeAt": 1788236557000},
        {"type": "EASY_APPLY_TEXT", "text": "Easy Apply"},
    ]
    listed_at_ms, metadata = _extract_footer(footer)
    assert listed_at_ms == 1788236557000
    assert metadata == ["Easy Apply"]


def test_parse_job_cards():
    data = {
        "elements": [
            {
                "jobCardUnion": {
                    "jobPostingCard": {
                        "title": {"text": "Data Analyst"},
                        "primaryDescription": {"text": "Acme Corp"},
                        "secondaryDescription": {"text": "India (Remote)"},
                        "jobPostingUrn": "urn:li:fsd_jobPosting:4459259957",
                        "logo": {
                            "attributes": [
                                {
                                    "detailData": {
                                        "companyLogo": {
                                            "logo": {
                                                "vectorImage": {
                                                    "rootUrl": "https://media.licdn.com/x_",
                                                    "artifacts": [
                                                        {"fileIdentifyingUrlPathSegment": "1.png"}
                                                    ],
                                                }
                                            }
                                        }
                                    }
                                }
                            ]
                        },
                        "footerItems": [
                            {"type": "LISTED_DATE", "timeAt": 1788236557000},
                            {"type": "EASY_APPLY_TEXT", "text": "Easy Apply"},
                        ],
                    }
                }
            }
        ],
        "paging": {"total": 1, "start": 0, "count": 25},
    }
    result = parse_job_cards(data)
    assert result.total == 1
    job = result.jobs[0]
    assert job.id == "4459259957"
    assert job.title == "Data Analyst"
    assert job.company == "Acme Corp"
    assert job.location == "India (Remote)"
    assert job.url == "https://www.linkedin.com/jobs/view/4459259957/"
    assert job.metadata == ["Easy Apply"]
    assert job.listed_at_ms == 1788236557000
    assert isinstance(job.listed_at, datetime.datetime)


def test_job_is_recent():
    now = datetime.datetime.now(datetime.timezone.utc)
    recent = Job(
        id="1",
        title="x",
        listed_at=now - datetime.timedelta(minutes=30),
    )
    old = Job(
        id="2",
        title="y",
        listed_at=now - datetime.timedelta(hours=3),
    )
    assert recent.is_recent(60) is True
    assert old.is_recent(60) is False


def test_build_search_query_with_experience():
    q = build_search_query("Data Analyst", 102713980, "r86400", "DD", ["1", "2"])
    assert "experience:List(1,2)" in q
    assert "selectedFilters:(sortBy:List(DD),timePostedRange:List(r86400),experience:List(1,2))" in q


def test_build_search_query_without_experience():
    q = build_search_query("Data Analyst", 102713980, "r86400", "DD", [])
    assert "experience:" not in q


def test_title_matches():
    kws = ["analyst", "analytics", "data science", "data scientist"]
    assert title_matches("Data Analyst Intern", kws) is True
    assert title_matches("Python Analyst - Data", kws) is True  # has "analyst"
    assert title_matches("Data Analytics Specialist", kws) is True
    assert title_matches("Data Scientist", kws) is True
    assert title_matches("AI Engineer", kws) is False
    assert title_matches("Physicist (BSc/MSc/PhD)", kws) is False
    assert title_matches("Salesforce Marketing Cloud Consultant", kws) is False
    # empty list disables the filter
    assert title_matches("Anything at all", []) is True


def test_apply_filters_title_and_blacklist():
    jobs = [
        Job(id="1", title="Data Analyst", company="Acme"),
        Job(id="2", title="AI Engineer", company="Acme"),
        Job(id="3", title="Data Analyst", company="Wake Up Whistle"),
    ]
    out = apply_filters(
        jobs,
        blacklist=["Wake Up Whistle"],
        title_keywords=["analyst", "data science"],
    )
    assert [j.id for j in out] == ["1"]


def test_seenjobs_retention_prune(tmp_path):
    store = SeenJobs(tmp_path / "sent.json", retention_days=7)
    store.mark("recent-id")
    store._seen["old-id"] = time.time() - 8 * 86400  # 8 days old

    assert store.is_new("recent-id") is False
    assert "old-id" in store

    removed = store.prune()
    assert removed == 1
    assert "old-id" not in store
    assert "recent-id" in store
