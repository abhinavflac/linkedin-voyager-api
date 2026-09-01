"""One-time helper to obtain a Gmail API refresh token (OAuth).

Run this ONCE locally to get the long-lived refresh token that the app uses to
send emails via the Gmail API (no SMTP).

Usage:
    pip install -r requirements-dev.txt
    python scripts/get_gmail_token.py path/to/client_secret.json

The browser opens, you authorize your Gmail account, and the script prints the
three values to copy into your environment (`.env` locally / Render env vars).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main(client_secret_path: Path) -> None:
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    print("\n" + "=" * 64)
    print("COPY THESE INTO .env (local) / RENDER ENV VARS:")
    print("=" * 64)
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 64)
    print("SENDER_EMAIL = the Gmail address you just authorized.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get a Gmail API refresh token")
    parser.add_argument(
        "client_secret",
        help="Path to the downloaded OAuth client JSON (client_secret_*.json)",
    )
    args = parser.parse_args()
    main(Path(args.client_secret))
