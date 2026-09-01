<div align="center">

# LinkedIn Voyager API — Personal Job Alerts

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/) [![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/) [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/) [![Render](https://img.shields.io/badge/Render-9747FF?style=for-the-badge&logo=render&logoColor=white)](https://render.com/) [![UptimeRobot](https://img.shields.io/badge/UptimeRobot-7DBE3C?style=for-the-badge&logo=uptimerobot&logoColor=1E1E2E)](https://uptimerobot.com/) [![Gmail](https://img.shields.io/badge/Gmail-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](https://mail.google.com/)

</div>

> [!TIP]
> **Built with curiosity** — this project is a love letter to how the web really works
> under the hood: a modern SPA, its private REST API, and a tiny Python client that
> replaces a whole headless browser. Every layer is tuned for one thing — surfacing the
> right job, the moment it's posted, with zero noise.

A **browser-free** LinkedIn job alert bot that talks directly to LinkedIn's private
**Voyager API** (the exact endpoints the website calls internally), returning structured
JSON with **exact posting timestamps** so you can get *only* the freshest, most relevant
jobs — without Selenium, without scraping HTML, and without the broken public "semantic
search" UI.

<div align="center">

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://dashboard.render.com/web/new?onboarding=active)

<sub>Deploy in one click — or follow the [manual setup](#deploying-to-render-free-tier).</sub>

</div>

---

## Features

- **Browser-free** — talks straight to LinkedIn's private Voyager API. No Selenium, no Chrome, no HTML scraping.
- **Exact timestamps** — every job carries its precise posting time down to the millisecond.
- **3-layer filtering** — experience level (API) → title / blacklist / age (client) → dedup.
- **Fresher / intern / trainee aware** — `experience:List(1,2)` keeps only entry-level roles.
- **HTML email alerts** — title, company, location, logo, and posted time.
- **Dedup** — never emails the same job twice; keeps a rolling 7-day memory of sent IDs.
- **API + CLI** — FastAPI server, a one-off `search`, or a background `loop`.
- **Render-ready** — deploy as a free web service + UptimeRobot keep-alive.

## Quick Start

```bash
# 1. env + deps
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt

# 2. configure
copy .env.example .env

# 3. capture cookies (log in once in the Chrome window that opens)
python scripts/get_cookies.py

# 4. run a search
python -m app.main search "Data Analyst" --max-age 60
```

---

## Table of Contents

1. [Why this project exists](#why-this-project-exists)
2. [The Voyager API — how LinkedIn's backend actually works](#the-voyager-api--how-linkedins-backend-actually-works)
3. [Every filter the API exposes](#every-filter-the-api-exposes)
4. [Project architecture](#project-architecture)
5. [The filtering pipeline (3 layers)](#the-filtering-pipeline-3-layers)
6. [Setup](#setup)
7. [Capturing cookies](#capturing-cookies)
8. [Email setup (Gmail API)](#email-setup-gmail-api)
9. [`.env` configuration — every variable](#env-configuration--every-variable)
10. [Usage](#usage)
11. [How to change things](#how-to-change-things)
12. [Deploying to Render (free tier)](#deploying-to-render-free-tier)
13. [Under the hood — request & response flow](#under-the-hood--request--response-flow)
14. [Tests](#tests)
15. [Troubleshooting](#troubleshooting)
16. [Educational purpose](#educational-purpose)

---

## Why this project exists

LinkedIn has **two different job-search systems**:

| Route | What it is | Time filtering |
|---|---|---|
| `/jobs/search/` | "classic" search — calls the Voyager API | ✅ works correctly |
| `/jobs/search-results/` | new "AI-powered" / semantic search (SDUi) | ❌ broken/incomplete |

The semantic search treats `"Data Analyst jobs posted within 1 hour"` as a *literal
text query*, not a filter, so it returns 99+ results including old jobs. The classic
route's backend API (`voyagerJobsDashJobCards`) honors time filters **and** returns the
exact listing timestamp of every job. This project uses that API directly.

---

## The Voyager API — how LinkedIn's backend actually works

### What "Voyager" is

Voyager is LinkedIn's internal REST/GraphQL API. When you visit `linkedin.com/jobs/search/`
in a browser, the page (rendered in React) fetches job data from
`https://www.linkedin.com/voyager/api/...`. It is not documented publicly and can change
without notice.

### The main endpoint

```
GET https://www.linkedin.com/voyager/api/voyagerJobsDashJobCards
    ?decorationId=com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollection-220
    &count=25
    &q=jobSearch
    &query=(...)
    &start=0
```

| Param | Meaning |
|---|---|
| `decorationId` | which "shape" of data the client wants (field selection). Changes over time; configurable in the project. |
| `count` | results per page (**max 25**) |
| `q` | query type — always `jobSearch` here |
| `query` | the search expression (see below) |
| `start` | pagination offset (0, 25, 50, …) |

### The `query` expression (Rest.li format)

The `query` value is a compact string. Spaces are `%20`-encoded; `(`, `)`, `,`, `:` stay
literal. Structure:

```
(origin:JOB_SEARCH_PAGE_JOB_FILTER,
 keywords:Data%20Analyst,
 locationUnion:(geoId:102713980),
 selectedFilters:(sortBy:List(DD),timePostedRange:List(r86400),experience:List(1,2)),
 spellCorrectionEnabled:true)
```

- `origin` — where the search came from (`JOB_SEARCH_PAGE_JOB_FILTER` for classic).
- `keywords` — the search text (fuzzy/semantic matching — see "Fuzzy matching" below).
- `locationUnion:(geoId:<id>)` — location.
- `selectedFilters:(...)` — the facets (sort, time, experience, etc.). Each is
  `name:List(value1,value2)`.
- `spellCorrectionEnabled` — whether LinkedIn may auto-correct typos.

### Authentication (CSRF + cookies)

The API rejects requests unless:

1. A valid **session cookie set** is present, and
2. The **`csrf-token` header equals the `JSESSIONID` cookie value**.

The minimal cookie set that works is:

```
JSESSIONID=<ajax:...>   ← used as the csrf-token
li_at=<...>             ← the actual login session token
bcookie=<...>
bscookie=<...>
lidc=<...>
lang=<...>
```

> [!IMPORTANT]
> A partial cookie set (e.g. 10 cookies from a naive `driver.get_cookies()`) fails with
> `403 CSRF check failed`. The `get_cookies.py` script captures the full set (~45 cookies)
> via the Chrome DevTools Protocol, which is why direct HTTP requests succeed.

The `li_at` cookie expires after days-to-weeks; when it does, every request returns
`401/403` and you must re-run `get_cookies.py`.

### Response shape

```jsonc
{
  "metadata": { "keywords": "Data Analyst", "geoUrn": "urn:li:fsd_geo:102713980", ... },
  "elements": [
    {
      "jobCardUnion": {
        "jobPostingCard": {
          "title":              { "text": "Data Analyst" },
          "primaryDescription": { "text": "Acme Corp" },      // company
          "secondaryDescription": { "text": "India (Remote)" }, // location
          "logo": { /* nested company logo URL */ },
          "jobPostingUrn": "urn:li:fsd_jobPosting:4459259957",
          "footerItems": [
            { "type": "LISTED_DATE", "timeAt": 1788236557000 },   // exact post time (ms)
            { "type": "EASY_APPLY_TEXT", "text": "Easy Apply" }
          ],
          "relevanceInsight": { "text": "1 connection works here" }
        }
      }
    }
  ],
  "paging": { "total": 279, "count": 25, "start": 0 }
}
```

Key fields the project extracts:

| Field | Source | Used for |
|---|---|---|
| `id` | `jobPostingUrn` → `urn:li:fsd_jobPosting:4459259957` → `4459259957` | dedup key |
| `title` | `title.text` | display + title filter |
| `company` | `primaryDescription.text` | display + blacklist |
| `location` | `secondaryDescription.text` | display |
| `listed_at` | `footerItems[type=LISTED_DATE].timeAt` (ms) | "latest only" / max-age filter |
| `logo_url` | `logo.attributes[0].detailData.companyLogo.logo.vectorImage` | email |
| `metadata` | `footerItems` (e.g. `EASY_APPLY_TEXT`) | display |

### Pagination

Offset-based. `count` is per page (max 25); increment `start` by `count` until
`start >= paging.total`. **This project fetches only page 1** on purpose — with
`sortBy=DD` (newest first), page 1 is always the newest 25 jobs, which is all you need
for "latest only" alerts.

### Fuzzy keyword matching (important gotcha)

`keywords` does **semantic/fuzzy** matching, not exact-string. Searching `"Data Analyst"`
also returns `Data Scientist`, `Research Analyst`, `Business Intelligence Consultant`,
`Data Engineer`, even `AI Engineer` and `Physicist` — because LinkedIn's search treats
them as related. The API exposes **no** `matchType`/`relevanceScore`/`sponsored` flag to
distinguish them (verified by inspecting raw responses). That's why the project applies a
**client-side title filter** as a final safety net (see the pipeline below).

---

## Every filter the API exposes

These were discovered by querying LinkedIn's filter-clusters endpoint
(`voyagerJobsDashSearchFilterClustersResource`). All go inside `selectedFilters` as
`name:List(value1,value2)`.

| Filter (`parameterName`) | Values | Notes |
|---|---|---|
| `sortBy` | `DD` = most recent, `R` = most relevant | single select |
| `timePostedRange` | `r2592000` (month), `r604800` (week), `r86400` (24h), or any `r<seconds>` | **used by the project** |
| `experience` | `1`=Internship, `2`=Entry, `3`=Associate, `4`=Mid-Senior, `5`=Director, `6`=Executive | **used by the project** — the "fresher/intern/trainee" filter |
| `company` | numeric company ID (e.g. `11448` = Citi) | |
| `jobType` | `F`=Full-time, `P`=Part-time, `C`=Contract, `T`=Temporary, `I`=Internship, `O`=Other | |
| `workplaceType` | `1`=On-site, `2`=Remote, `3`=Hybrid | |
| `applyWithLinkedin` | `true` | "Easy Apply" only |
| `verifiedJob` | `true` | has verifications |
| `populatedPlace` | numeric place ID (e.g. `105214831` = Bengaluru) | |
| `industry` | numeric ID (e.g. `4` = Software Development) | |
| `function` | `it`, `eng`, `rsch`, `anls`, `sale`, `fin`, `bd`, `cnsl`, `othr`, `prdm` | |
| `title` | numeric standardized-title ID (e.g. `340` = "Data Analyst") | unreliable — see below |
| `earlyApplicant` | `true` | "Under 10 applicants" |
| `jobInYourNetwork` | `true` | in your network |
| `fairChanceEmployer` | `true` | |
| `benefits` | `1`–`12` (medical, vision, dental, 401(k), …) | |
| `commitments` | `1`–`5` (DEI, sustainability, …) | |

### Notes on specific filters

- **`title` filter is unreliable.** `"Data Analyst"` maps to standardized ID `340`, but
  passing `title:List(340)` was silently ignored (returned everything) and URN formats
  (`urn:li:fsd_title:340`) errored. We therefore do title filtering **client-side**
  instead (the `TITLE_KEYWORDS` setting).
- **`experience` is the reliable API-level lever** for fresher/intern/trainee.
- **`timePostedRange` values below `r86400`** (e.g. `r3600`, `r5000`) are honored by the
  backend but clamp to a ~1-hour minimum bucket. The exact-millisecond `listed_at` in the
  response is what gives you true "last N minutes" precision client-side.

---

## Project architecture

```
linkedin-voyager-api/
├── app/
│   ├── config.py     # Settings — reads .env (pydantic-settings)
│   ├── models.py     # Job / SearchQuery / SearchResult (pydantic)
│   ├── client.py     # LinkedInVoyagerClient — cookies, CSRF, retries, HTTP
│   ├── search.py     # query building + raw response parsing
│   ├── store.py      # SeenJobs — JSON-backed dedup of sent job IDs
│   ├── notifier.py   # Gmail API email alerts
│   ├── alerts.py     # polling loop + shared filters (blacklist/age/title)
│   └── main.py       # FastAPI app + CLI entry point
├── scripts/
│   └── get_cookies.py  # one-time browser login → full cookie capture (CDP)
├── tests/
│   └── test_search.py  # unit tests (query building, parsing, filters)
├── .env.example
├── .gitignore
├── conftest.py
├── pyproject.toml
└── requirements.txt
```

| Module | Responsibility |
|---|---|
| `client.py` | Holds a `requests.Session`; loads cookies from disk, sets `csrf-token` + `Cookie` headers; retries; maps 401/403 → `LinkedInAuthError`, 429 → rate-limit. |
| `search.py` | `build_search_query()` builds the Rest.li string; `search_jobs()` calls the endpoint; `parse_job_cards()` turns raw JSON into `Job` models. |
| `alerts.py` | `apply_filters()` (shared filter), `scan_once()` (one pass over keywords), `run_alert_loop()` (infinite poll). |
| `store.py` | `SeenJobs` — persistent set of already-alerted job IDs (`sent_jobs.json`). |
| `notifier.py` | Builds + sends the HTML email. |
| `main.py` | FastAPI endpoints + CLI (`search`, `loop`). |

---

## The filtering pipeline (3 layers)

Jobs pass through three gates before they reach your inbox/CLI output:

### Layer 1 — API-side (server does the work)

Set in `search.py` `build_search_query()`:

- **`experience:List(1,2)`** (`EXPERIENCE_LEVELS`) → only internship + entry level.
  Removes all "Senior"/"5–8 yrs" roles server-side.
- **`timePostedRange:List(r86400)`** (`TIME_POSTED_RANGE`) → time window.
- **`sortBy:List(DD)`** (`SORT_BY`) → newest first.

### Layer 2 — client-side filters (in `alerts.py` `apply_filters()`)

Applied to every job *after* it's parsed:

1. **Blacklist** (`BLACKLISTED_COMPANIES`) — skip if any blacklisted string appears in the
   company name (case-insensitive substring).
2. **Max age** (`MAX_AGE_MINUTES`) — keep only jobs listed within N minutes (uses the
   exact `listed_at` timestamp).
3. **Title** (`TITLE_KEYWORDS`) — keep only jobs whose title contains any of the tokens
   (case-insensitive substring).

### Layer 3 — dedup (`store.py` `SeenJobs`)

A job is marked "seen" (by numeric ID, with a timestamp) before emailing, so it's never
sent twice. The store lives **in memory**, mirrored to `sent_jobs.json`, and is pruned
automatically — IDs older than `DEDUP_RETENTION_DAYS` (default 7) are dropped, so memory
stays small and bounded forever. On ephemeral hosting (Render free) it simply resets on
redeploy, which is accepted by design.

The **same** `apply_filters()` is used by the alert loop, the CLI `search`, and the
`/jobs` endpoint, so behaviour is consistent everywhere.

---

## Setup

### 1. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate            # Windows
# macOS/Linux: source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Dependencies: `fastapi`, `uvicorn`, `requests`, `pydantic`, `pydantic-settings`,
`python-dotenv`.

> [!NOTE]
> Capturing cookies (`scripts/get_cookies.py`) additionally needs **Selenium** + a local
> Chrome browser. Install it once with:
> ```bash
> pip install -r requirements-dev.txt
> ```
> It is *not* needed to run the app, the CLI, or the Render deployment.

### 3. Configure `.env`

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
```

Then edit `.env` (see the [full variable reference](#env-configuration--every-variable)).

### 4. Capture cookies

```bash
python scripts/get_cookies.py
```

A Chrome window opens — log in manually and wait. The script saves a **complete** cookie
set to `cookies.json` (see [Capturing cookies](#capturing-cookies)).

### 5. Run

```bash
python -m app.main search "Data Analyst" --max-age 60   # one-off search
python -m app.main loop                                  # poll + email alerts
uvicorn app.main:app --reload                            # run as an API server
```

---

## Capturing cookies

> [!NOTE]
> This step needs `selenium` and a local Chrome browser — install once with
> `pip install -r requirements-dev.txt` before running `get_cookies.py`.

### Why a special script?

`driver.get_cookies()` (plain Selenium) returns only ~10 cookies for the current page.
The Voyager API's CSRF check **rejects** that partial set. The browser actually holds
~45 cookies for `linkedin.com` (Cloudflare `__cf_bm`, Adobe `AMCV*`, `_guid`, `li_sugr`,
quoted `bcookie`/`bscookie`/`lidc`, etc.). `scripts/get_cookies.py` uses the Chrome
DevTools Protocol (`Network.getAllCookies`) to dump **every** cookie the browser holds —
including HttpOnly and third-party ones — in the exact `name=value` form the browser
sends.

### Steps

1. Run `python scripts/get_cookies.py [--output cookies.json]`.
2. A Chrome window opens at `linkedin.com/login`.
3. Log in manually (solve captcha / 2FA if asked).
4. The script detects the login, visits `/jobs/search/` to warm up any lazy cookies,
   then writes `cookies.json`.
5. Done. Re-run it whenever the API starts returning `401`/`403` (cookies expired).

### Cookie lifetime

- `li_at` (the session token) lasts days-to-weeks.
- When expired, the API returns `401/403` and the loop just logs errors — re-run
  `get_cookies.py`.

---

## Email setup (Gmail API)

Emails are sent via the **Gmail REST API** over HTTPS (not SMTP), because Render blocks
outbound SMTP ports. This is a one-time setup to get an OAuth **refresh token**.

### 1. Create a Google Cloud project & enable the Gmail API

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with the
   Gmail account you want to send from.
2. **Create a project** (e.g. `job-alerts`).
3. **APIs & Services → Library** → search **Gmail API** → **Enable**.

### 2. Configure the OAuth consent screen

1. **APIs & Services → OAuth consent screen**.
2. User type: **External** → **Create**.
3. App name: `Job Alerts`; user support email: your Gmail.
4. **Add scope:** `https://www.googleapis.com/auth/gmail.send`.
5. **Test users:** add your own Gmail address.
6. **Publish the app** (set to **In production**) so the refresh token doesn't expire after
   7 days. (You'll see an "unverified app" warning during the next step — click
   **Advanced → Continue**, that's normal for a personal app.)

### 3. Create OAuth client & download its JSON

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**.
3. Click **Download JSON** (saves `client_secret_*.json`).

### 4. Get the refresh token

```bash
pip install -r requirements-dev.txt
python scripts/get_gmail_token.py path/to/client_secret_*.json
```

A browser opens → authorize your Gmail → the script prints three values:
`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`.

### 5. Fill in `.env` (or Render env vars)

```dotenv
SENDER_EMAIL=<your Gmail>
RECEIVER_EMAIL=<destination>
GMAIL_CLIENT_ID=<from script>
GMAIL_CLIENT_SECRET=<from script>
GMAIL_REFRESH_TOKEN=<from script>
```

---

## `.env` configuration — every variable

| Variable | Type | Default | Description |
|---|---|---|---|
| `COOKIES_PATH` | str | `cookies.json` | Path to the cookie file from `get_cookies.py`. |
| `COOKIES_JSON` | str | *(empty)* | Raw cookie JSON as a string (alternative to the file, for Render/Heroku). Takes precedence over `COOKIES_PATH`. |
| `KEYWORDS` | JSON list | `["Data Analyst","Data Analytics","Data Scientist","Business Analyst"]` | Search terms, one API call each. |
| `GEO_ID` | int | `102713980` | LinkedIn location ID (`102713980`=India, `103644278`=US). |
| `TIME_POSTED_RANGE` | str | `r86400` | API time window (`r86400`=24h, `r604800`=week, `r2592000`=month, or `r<seconds>`). |
| `SORT_BY` | str | `DD` | `DD`=most recent, `R`=most relevant. |
| `COUNT` | int | `25` | Results per page (max 25). |
| `MAX_AGE_MINUTES` | int or empty | *(empty)* | Client-side "latest only" cutoff (exact `listed_at`). Empty = disabled. |
| `EXPERIENCE_LEVELS` | JSON list | `["1","2"]` | API experience filter: `1`=Internship, `2`=Entry, `3`=Associate, `4`=Mid-Senior, `5`=Director, `6`=Executive. Empty `[]` disables. |
| `TITLE_KEYWORDS` | JSON list | `["analyst","analytics","data science","data scientist"]` | Client-side title filter — keep job if title contains **any** token (case-insensitive substring). Empty `[]` disables. |
| `DECORATION_ID` | str | *(long Voyager ID)* | Voyager field-selection ID. Rarely needs changing. |
| `POLL_INTERVAL_SECONDS` | int | `300` | Seconds between alert-loop cycles. |
| `BLACKLISTED_COMPANIES` | JSON list | *(several)* | Company names to skip (case-insensitive substring). Overrides the code default. |
| `SENT_JOBS_FILE` | str | `sent_jobs.json` | Where the dedup record is stored (local dev only). |
| `DEDUP_RETENTION_DAYS` | int | `7` | How many days to keep seen job IDs before pruning (bounds memory). |
| `SENDER_EMAIL` | str | *(empty)* | Gmail address sending alerts. |
| `RECEIVER_EMAIL` | str | *(empty)* | Destination address (comma-separated for multiple). |
| `GMAIL_CLIENT_ID` | str | *(empty)* | OAuth client ID (from `scripts/get_gmail_token.py`). |
| `GMAIL_CLIENT_SECRET` | str | *(empty)* | OAuth client secret. |
| `GMAIL_REFRESH_TOKEN` | str | *(empty)* | Long-lived OAuth refresh token. |

> [!NOTE]
> Empty-string gotcha: `MAX_AGE_MINUTES=` and empty JSON lists are handled gracefully
> (treated as "unset" / empty). `EXPERIENCE_LEVELS=[]` and `TITLE_KEYWORDS=[]` disable
> those filters.

---

## Usage

### CLI

```bash
# Search one keyword, show results after all filters
python -m app.main search "Data Analyst"

# Only jobs posted in the last 60 minutes
python -m app.main search "Data Analyst" --max-age 60

# Override the time range
python -m app.main search "Data Analyst" --time-posted-range r5000

# Different location
python -m app.main search "Data Analyst" --geo-id 103644278

# Run the alert loop (poll + email)
python -m app.main loop
```

### HTTP API (FastAPI)

| Endpoint | Description |
|---|---|
| `GET /` | root message |
| `GET /health` | liveness probe (for UptimeRobot) |
| `GET /jobs?keywords=Data%20Analyst&max_age_minutes=60` | search + filters |
| `GET /scan` | run one scan, return new jobs |

```bash
uvicorn app.main:app --reload
curl "http://localhost:8000/jobs?keywords=Data%20Analyst&max_age_minutes=60"
```

---

## How to change things

### Change search keywords / roles

Edit `KEYWORDS` in `.env`:

```dotenv
KEYWORDS=["Data Analyst","Data Analytics","Data Scientist","Business Analyst"]
```

For "fresher/intern/trainee only", keep `EXPERIENCE_LEVELS=["1","2"]`.

### Change which titles are kept (title filter)

Edit `TITLE_KEYWORDS` in `.env`. It's **substring** matching on any token:

```dotenv
TITLE_KEYWORDS=["analyst","analytics","data science","data scientist"]
```

- `Python Analyst Data` → contains `analyst` → **kept**
- `AI Engineer` → none of the tokens → **cut**
- `Physicist (BSc/MSc/PhD)` → **cut**
- Set `TITLE_KEYWORDS=[]` to disable entirely.

### Change experience level

Edit `EXPERIENCE_LEVELS`:

```dotenv
EXPERIENCE_LEVELS=["1"]           # internship only
EXPERIENCE_LEVELS=["1","2"]       # intern + entry (freshers)
EXPERIENCE_LEVELS=["2","3"]       # entry + associate
EXPERIENCE_LEVELS=[]              # no level filter (all seniorities)
```

### Block companies

Edit `BLACKLISTED_COMPANIES` in `.env` (JSON list). Matching is case-insensitive
substring, so `"internmo"` also catches `"InternMo"`.

### Change how often it polls

`POLL_INTERVAL_SECONDS=60` → every minute.

### Change dedup retention

`DEDUP_RETENTION_DAYS=7` → keep seen job IDs for 7 days, then prune. Lower it to save
memory, raise it if you (rarely) redeploy and want to shrink the duplicate burst.

### Add a new API-level filter

Any filter from the [filter table](#every-filter-the-api-exposes) can be added to
`build_search_query()` in `app/search.py` (then plumbed through `search_jobs()`). The
three already wired in (`sortBy`, `timePostedRange`, `experience`) are a template for the
others (e.g. add `jobType:List(I)` for internships, or `workplaceType:List(2)` for
remote-only).

---

## Deploying to Render (free tier)

Render's **free** plan is enough for this project — it's a lightweight Python app (no
Chrome/Selenium), using ~100–150 MB RAM and near-zero CPU.

### Manual deploy

1. Push the project to a GitHub/GitLab repo (public **or** private — Render connects via
   your account and can access private repos).
2. In the Render dashboard → **New +** → **Web Service** → connect the repo.
3. Use these settings:
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check path:** `/health`
   - **Plan:** Free
4. Add the environment variables (below) and click **Create Web Service**.

### Environment variables on Render

The app has sensible defaults for everything except the **secrets**. The six you **must**
set manually:

| Variable | What to put |
|---|---|
| `COOKIES_JSON` | The **entire contents** of your `cookies.json` file, pasted as one string. Render has no persistent filesystem, so cookies must be an env var, not a file. |
| `SENDER_EMAIL` | your Gmail address |
| `RECEIVER_EMAIL` | destination inbox (comma-separated for multiple) |
| `GMAIL_CLIENT_ID` | from `scripts/get_gmail_token.py` |
| `GMAIL_CLIENT_SECRET` | from `scripts/get_gmail_token.py` |
| `GMAIL_REFRESH_TOKEN` | from `scripts/get_gmail_token.py` |

The rest (`KEYWORDS`, `EXPERIENCE_LEVELS`, `TITLE_KEYWORDS`, `POLL_INTERVAL_SECONDS`,
etc.) are optional — leave them unset to use the defaults, or set them to override. See the
[`.env` reference](#env-configuration--every-variable).

**How to get `COOKIES_JSON`:** run `python scripts/get_cookies.py` locally, open the
generated `cookies.json`, copy the whole thing, and paste it into the Render env var
(Render env vars can hold a few KB, and a full cookie set is ~5–10 KB, so it fits).

**How to get the Gmail OAuth values:** see [Email setup (Gmail API)](#email-setup-gmail-api).

> [!WARNING]
> When you later update cookies locally, you must **update the `COOKIES_JSON` env var on
> Render and redeploy** — the deployed copy does not auto-refresh.

### Keeping it awake (UptimeRobot, free plan)

Render's free web services **sleep after 15 minutes with no incoming HTTP requests**. Your
background polling loop makes *outgoing* requests only, which do **not** count — so you
need an external ping:

1. Create a free account at [uptimerobot.com](https://uptimerobot.com).
2. **+ Create monitor** → type **HTTP(s)**.
3. **URL:** `https://<your-app-name>.onrender.com/health`
4. **Monitoring interval:** 5 minutes (free plan default).
5. Save.

UptimeRobot pings `/health` every 5 minutes, so the service never hits the 15-minute sleep
threshold. The `/health` endpoint exists specifically for this (returns `{"status":"ok"}`).

**About "bypassing the runtime":** the 5-minute ping only prevents *sleep*. It does **not**
bypass the **750 free instance-hours/month** limit. One free service running 24/7 ≈ one
full month, so a single service is fine — but a second free service would exceed the
monthly allowance.

### Important caveats for Render free

1. **Ephemeral filesystem / RAM** — the dedup record lives in memory and is reset on every
   deploy/restart. After a restart you'll get one burst of **duplicate emails** (only jobs
   still inside the 24h window), then it re-primes. This is accepted by design for a
   personal tool; the 7-day retention keeps memory small and the impact of a reset bounded.
2. **Cookies expire** — `li_at` lasts days-to-weeks. When it dies, the loop logs 401/403
   until you paste a fresh `COOKIES_JSON` and redeploy.
3. **LinkedIn ToS** — polling from a datacenter IP is more likely to be flagged than from
   your home IP. Keep `POLL_INTERVAL_SECONDS` conservative (≥ 300s recommended).

## Under the hood — request & response flow

```
run_alert_loop()
 └─ scan_once()                       (one keyword at a time)
     └─ search_jobs()
         ├─ build_search_query()      → "(origin:...,keywords:...,selectedFilters:(...))"
         └─ client.get_json(url)      → GET /voyager/api/voyagerJobsDashJobCards
             └─ requests.Session      → sends Cookie + csrf-token + x-restli-protocol-version
     └─ parse_job_cards()             → raw JSON → List[Job]
     └─ _filter_new()                 → apply_filters() + dedup
         ├─ blacklist (company)
         ├─ max-age (listed_at)
         └─ title (TITLE_KEYWORDS)
 └─ send_jobs_email() + seen.save()
```

Key implementation details:

- The request URL is **built manually** (not via a `params` dict) so the Rest.li query
  keeps literal `( ) : ,` — re-encoding them makes the API return HTTP 400.
- `csrf-token` is read from the `JSESSIONID` cookie value (`ajax:…`).
- Parsing is defensive: a single malformed card never breaks the whole page.

---

## Tests

```bash
python -m pytest
```

Covers: query building (with/without experience), response parsing, logo/footer
extraction, `is_recent`, `title_matches` (including the `Python Analyst - Data` edge
case), and combined `apply_filters` (blacklist + title).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 CSRF check failed` | stale/partial cookies | re-run `python scripts/get_cookies.py` |
| `401` / `403` after some days | `li_at` expired | re-run `get_cookies.py` |
| `429` | rate limited | increase `POLL_INTERVAL_SECONDS` |
| HTTP `400` | query re-encoded wrongly | don't double-encode the `query` param |
| irrelevant jobs still appear | fuzzy keyword matching | tighten `TITLE_KEYWORDS` / `KEYWORDS` |
| `MAX_AGE_MINUTES=` error | empty env value | it's now handled as "unset"; leave blank or set a number |
| no email sent | missing/invalid Gmail OAuth | set `SENDER_EMAIL` + `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN` + `RECEIVER_EMAIL` |

---

## Educational purpose

> [!NOTE]
> **For learning & personal job-hunting only.** This project exists to explore how web
> APIs really work — LinkedIn's private "Voyager" endpoints are a fascinating real-world
> study of a REST API powering a modern app. It's a personal convenience for your own job
> search, not a data-mining or reselling tool, and it isn't affiliated with or endorsed by
> LinkedIn.
>
> A gentle nudge: keep the polling interval generous, keep your cookies to yourself, and if
> you ever need something production-grade, LinkedIn's own job-alert emails are the
> friendlier path.
