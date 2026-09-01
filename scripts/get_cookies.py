"""Capture a full LinkedIn session cookie set for the Voyager API.

Why this exists (and why it differs from a plain ``driver.get_cookies()``):

The Voyager API's CSRF check rejects requests that only carry the ~10 cookies
returned by ``driver.get_cookies()``. The browser actually holds ~45 cookies for
``linkedin.com`` (Cloudflare ``__cf_bm``, Adobe ``AMCV*``, ``_guid``, ``li_sugr``,
etc.), several of which are required for the API to accept direct HTTP calls.

This script uses the Chrome DevTools Protocol (``Network.getAllCookies``) to dump
*every* cookie the browser holds, including HttpOnly ones, in the exact
``name=value`` form the browser would send.

Usage:
    python scripts/get_cookies.py [--output cookies.json]

A Chrome window opens. Log in manually (solve any captcha / 2FA), then wait.
The script writes the cookies once it detects a logged-in session.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

WAIT_SECONDS = 300  # 5 minutes to log in


def _is_logged_in(driver: webdriver.Chrome) -> bool:
    if "Feed" in driver.title or "My Network" in driver.title:
        return True
    try:
        return len(driver.find_elements(By.CSS_SELECTOR, ".global-nav__me-photo")) > 0
    except Exception:
        return False


def main(output: Path) -> None:
    options = Options()
    # Keep the automation switches off so the browser looks like a normal one.
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.maximize_window()
    driver.get("https://www.linkedin.com/login")

    print("\n" + "=" * 60)
    print("PLEASE LOG IN TO LINKEDIN IN THE OPENED BROWSER WINDOW.")
    print("Solve any captchas or 2FA if prompted.")
    print(f"Waiting up to {WAIT_SECONDS} seconds for you to log in...")
    print("=" * 60 + "\n")

    logged_in = False
    for _ in range(WAIT_SECONDS):
        time.sleep(1)
        if _is_logged_in(driver):
            logged_in = True
            print("Login detected.")
            break

    if not logged_in:
        print("Timed out waiting for login.")
        driver.quit()
        return

    # Visit a job-search page so any lazy/domain-specific cookies get set too.
    print("Warming up cookies on the jobs search page...")
    driver.get("https://www.linkedin.com/jobs/search/")
    time.sleep(6)

    print("Collecting all cookies via CDP...")
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass
    cookies = driver.execute_cdp_cmd("Network.getAllCookies", {})["cookies"]

    output.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    print(f"Saved {len(cookies)} cookies to {output}")
    print("You can now run: python -m app.main search \"Data Analyst\"")

    driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture LinkedIn cookies for the Voyager API")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cookies.json"),
        help="Output path (default: cookies.json in the current directory)",
    )
    args = parser.parse_args()
    main(args.output)
