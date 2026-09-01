"""Low-level HTTP client for LinkedIn's private Voyager API.

The Voyager API is the same endpoint the web app calls internally. It requires:

* a valid LinkedIn session cookie set (see scripts/get_cookies.py), and
* a ``csrf-token`` header equal to the ``JSESSIONID`` cookie value.

All calls go through ``requests.Session`` which keeps cookies/headers consistent
and lets us retry on transient failures.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com"
VOYAGER_API = f"{BASE_URL}/voyager/api"

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "x-restli-protocol-version": "2.0.0",
    "x-li-lang": "en_US",
}


class LinkedInAuthError(RuntimeError):
    """Raised when the session is expired or the cookies are invalid."""


class LinkedInRateLimitError(RuntimeError):
    """Raised when LinkedIn throttles requests."""


def _normalize_cookie_data(data: Any) -> List[Dict[str, Any]]:
    """Normalize cookie data into a list of ``{"name", "value"}`` dicts.

    Accepts either a flat ``{name: value}`` map or a list of cookie dicts.
    """
    if isinstance(data, dict):
        return [{"name": k, "value": v} for k, v in data.items()]

    cookies: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and "name" in item and "value" in item:
            cookies.append({"name": item["name"], "value": item["value"]})
    return cookies


def load_cookies(path: str | Path) -> List[Dict[str, Any]]:
    """Load cookies from a JSON file.

    Accepts either a list of cookie dicts (``{"name": ..., "value": ...}``)
    as produced by ``get_cookies.py`` / Selenium, or a flat ``{name: value}`` map.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return _normalize_cookie_data(data)


def load_cookies_json(raw: str) -> List[Dict[str, Any]]:
    """Load cookies from a raw JSON string (e.g. an environment variable)."""
    return _normalize_cookie_data(json.loads(raw))


def build_cookie_header(cookies: List[Dict[str, Any]]) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def find_cookie(cookies: List[Dict[str, Any]], name: str) -> Optional[str]:
    for c in cookies:
        if c["name"] == name:
            return c["value"]
    return None


class LinkedInVoyagerClient:
    """Authenticated client for the LinkedIn Voyager API."""

    def __init__(
        self,
        cookies_path: str | Path,
        *,
        cookies_json: str = "",
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        timeout: int = 30,
    ) -> None:
        self.cookies_path = Path(cookies_path)
        self.cookies_json = cookies_json
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.csrf_token: str = ""
        self._reload_cookies()

    def _reload_cookies(self) -> None:
        if self.cookies_json:
            cookies = load_cookies_json(self.cookies_json)
            source = "COOKIES_JSON env var"
        else:
            cookies = load_cookies(self.cookies_path)
            source = str(self.cookies_path)

        if not cookies:
            raise LinkedInAuthError(
                f"No cookies found ({source}). "
                "Run `python scripts/get_cookies.py` first, or set COOKIES_JSON."
            )

        self.session.headers["Cookie"] = build_cookie_header(cookies)
        self.csrf_token = find_cookie(cookies, "JSESSIONID") or ""
        if self.csrf_token:
            self.session.headers["csrf-token"] = self.csrf_token
        logger.debug("Loaded %d cookies (%s); csrf token %s", len(cookies), source, bool(self.csrf_token))

    def reload_cookies(self) -> None:
        """Re-read cookies from disk (call after refreshing them)."""
        self._reload_cookies()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Perform an HTTP request with retries and error mapping."""
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.request(
                    method, url, params=params, headers=headers, timeout=self.timeout, **kwargs
                )
                if resp.status_code == 429:
                    raise LinkedInRateLimitError("Rate limited by LinkedIn.")
                if resp.status_code in (401, 403):
                    body = resp.text[:200]
                    raise LinkedInAuthError(
                        f"LinkedIn rejected the request ({resp.status_code}): {body}"
                    )
                if resp.status_code >= 500:
                    resp.raise_for_status()
                return resp
            except LinkedInAuthError:
                raise
            except LinkedInRateLimitError:
                raise
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("Request failed (attempt %d/%d): %s", attempt + 1, self.max_retries, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_backoff * (attempt + 1))
        raise RuntimeError(f"Request to {url} failed after retries") from last_exc

    def get(self, path: str, *, params: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{VOYAGER_API}{path}"
        return self.request("GET", url, params=params, **kwargs)

    def get_json(self, path: str, *, params: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Any:
        resp = self.get(path, params=params, **kwargs)
        resp.raise_for_status()
        return resp.json()
