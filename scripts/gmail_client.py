"""Gmail API client — read-only access via OAuth 2.0 (gmail.readonly scope).

Exports:
    authenticate_gmail() - Load/refresh OAuth credentials
    list_inbox_messages() - List inbox message IDs
    fetch_message() - Fetch message metadata + snippet
"""

import os
import subprocess
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


def _open_browser(url: str) -> None:
    """Open URL in Windows Chrome from WSL."""
    chrome_paths = [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            subprocess.Popen([path, url])
            return
    # Fallback: use Windows cmd to open default browser
    subprocess.Popen(["cmd.exe", "/c", "start", url])

# Read-only scope — Google API rejects all writes at credential level (Layer 1)
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_SEI_DIR = Path.home() / ".sei"
_TOKEN_PATH = _SEI_DIR / "gmail_token.json"
_CLIENT_SECRETS_PATH = Path(
    os.environ.get("GMAIL_CLIENT_SECRETS", str(_SEI_DIR / "gmail_credentials.json"))
)


def authenticate_gmail() -> Credentials:
    """Load token from ~/.sei/gmail_token.json; run OAuth flow if missing/expired."""
    _SEI_DIR.mkdir(parents=True, exist_ok=True)
    creds = None

    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CLIENT_SECRETS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail client secrets not found at {_CLIENT_SECRETS_PATH}. "
                    "Download OAuth credentials from Google Cloud Console and place them there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CLIENT_SECRETS_PATH), _SCOPES
            )
            # Monkey-patch webbrowser.open so run_local_server opens Chrome on Windows
            import webbrowser
            webbrowser.open = lambda url, new=0, autoraise=True: _open_browser(url)
            creds = flow.run_local_server(port=0)

        # Save refreshed/new token
        with open(_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def _build_service():
    """Build Gmail API service from authenticated credentials."""
    creds = authenticate_gmail()
    return build("gmail", "v1", credentials=creds)


def list_inbox_messages(max_results: int = 10, label: str = "CATEGORY_PERSONAL") -> list[dict]:
    """List inbox message IDs. Defaults to Primary tab unless label overridden."""
    service = _build_service()
    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX", label], maxResults=max_results)
        .execute()
    )
    return response.get("messages", [])


def search_messages(query: str, max_results: int = 5) -> list[dict]:
    """Search all mail (all labels) using Gmail search query syntax."""
    service = _build_service()
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return response.get("messages", [])


def fetch_message(msg_id: str) -> dict:
    """Fetch message metadata + snippet. Returns dict with sender, subject, timestamp, snippet, id."""
    service = _build_service()
    msg = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        )
        .execute()
    )

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg_id,
        "sender": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "timestamp": headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
    }
