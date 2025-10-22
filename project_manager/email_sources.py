"""Email source abstraction for fetching emails from Gmail."""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Optional

from .config import HOME_DIR

# Gmail API imports (optional dependencies)
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False


@dataclass
class RawEmail:
    """Represents a raw email fetched from an email source."""
    message_id: str
    sender: Optional[str]
    subject: Optional[str]
    received_at: Optional[str]
    body_text: str
    raw_content: bytes  # raw RFC822 email content
    source_id: str  # provider-specific ID (for marking as read, etc.)
    source_type: str  # 'gmail'


class EmailSource(ABC):
    """Abstract base class for email sources."""

    @abstractmethod
    def fetch_unread(self, max_results: int = 10) -> list[RawEmail]:
        """Fetch unread emails from the source."""
        pass

    @abstractmethod
    def mark_as_processed(self, source_id: str) -> None:
        """Mark an email as processed in the source (e.g., add label, mark read)."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this source is properly configured and ready to use."""
        pass


# ============================================================================
# Gmail Source Implementation
# ============================================================================

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
GMAIL_TOKEN_PATH = HOME_DIR / 'gmail_token.json'
GMAIL_CREDENTIALS_PATH = HOME_DIR / 'gmail_credentials.json'


class GmailSource(EmailSource):
    """Email source for Gmail using the Gmail API."""

    def __init__(self):
        if not GMAIL_AVAILABLE:
            raise ImportError(
                "Gmail API dependencies not installed. "
                "Install with: pip install google-auth google-auth-oauthlib "
                "google-auth-httplib2 google-api-python-client"
            )
        self.service = None

    def is_configured(self) -> bool:
        """Check if Gmail credentials are configured."""
        return GMAIL_CREDENTIALS_PATH.exists() or GMAIL_TOKEN_PATH.exists()

    def authenticate(self) -> None:
        """Authenticate with Gmail API using OAuth2."""
        creds = None

        # Load existing token if available
        if GMAIL_TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_PATH), GMAIL_SCOPES)

        # If no valid credentials, initiate OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not GMAIL_CREDENTIALS_PATH.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials not found at {GMAIL_CREDENTIALS_PATH}. "
                        f"Please download OAuth2 credentials from Google Cloud Console "
                        f"and save them to this location."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(GMAIL_CREDENTIALS_PATH), GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            GMAIL_TOKEN_PATH.write_text(creds.to_json())

        self.service = build('gmail', 'v1', credentials=creds)

    def fetch_unread(self, max_results: int = 10) -> list[RawEmail]:
        """Fetch unread emails from Gmail inbox."""
        if not self.service:
            self.authenticate()

        # Query for unread messages in inbox
        results = self.service.users().messages().list(
            userId='me',
            q='is:unread in:inbox',
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        raw_emails = []

        for msg in messages:
            # Fetch full message content
            message = self.service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='raw'
            ).execute()

            # Decode the raw message
            raw_content = base64.urlsafe_b64decode(message['raw'])

            # Parse the email
            email_msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(raw_content)

            # Extract fields
            message_id = email_msg.get('Message-Id', '').strip() or f"gmail-{msg['id']}"
            sender = email_msg.get('From', '').strip()
            subject = email_msg.get('Subject', '').strip()
            received_at = email_msg.get('Date', '').strip()

            # Extract body text
            body_text = self._extract_body(email_msg)

            raw_emails.append(RawEmail(
                message_id=message_id,
                sender=sender or None,
                subject=subject or None,
                received_at=received_at or None,
                body_text=body_text,
                raw_content=raw_content,
                source_id=msg['id'],
                source_type='gmail'
            ))

        return raw_emails

    def mark_as_processed(self, source_id: str) -> None:
        """Mark email as read and add 'PROCESSED' label in Gmail."""
        if not self.service:
            self.authenticate()

        # Mark as read
        self.service.users().messages().modify(
            userId='me',
            id=source_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()

    @staticmethod
    def _extract_body(message: EmailMessage) -> str:
        """Extract plain text body from email message."""
        text_parts = []
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == 'text/plain':
                    try:
                        text_parts.append(part.get_content())
                    except Exception:
                        continue
        else:
            try:
                text_parts.append(message.get_content())
            except Exception:
                pass

        return '\n'.join(filter(None, text_parts)).strip()


# ============================================================================
# Factory function
# ============================================================================

def get_available_sources() -> list[EmailSource]:
    """Get list of configured and available email sources."""
    sources = []

    # Try Gmail
    if GMAIL_AVAILABLE:
        gmail = GmailSource()
        if gmail.is_configured():
            sources.append(gmail)

    return sources
