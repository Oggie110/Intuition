"""Utilities for parsing and summarising email messages."""
from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import Optional


@dataclass
class ParsedEmail:
    message_id: str
    sender: Optional[str]
    subject: Optional[str]
    received_at: Optional[str]
    snippet: str
    raw_path: Path


def parse_email_file(path: Path) -> ParsedEmail:
    """Parse an .eml file and return a lightweight summary."""
    with path.open("rb") as fp:
        message: EmailMessage = BytesParser(policy=policy.default).parse(fp)

    message_id = message.get("Message-Id") or f"local-{path.stem}"
    sender = message.get("From")
    subject = message.get("Subject")
    received_at = message.get("Date")

    snippet = _extract_snippet(message)

    return ParsedEmail(
        message_id=message_id.strip(),
        sender=sender.strip() if sender else None,
        subject=subject.strip() if subject else None,
        received_at=received_at.strip() if received_at else None,
        snippet=snippet,
        raw_path=path,
    )


def _extract_snippet(message: EmailMessage, max_length: int = 200) -> str:
    """Get a short snippet from the email body for display."""
    text_parts = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                try:
                    text_parts.append(part.get_content())
                except Exception:  # pragma: no cover - defensive
                    continue
    else:
        try:
            text_parts.append(message.get_content())
        except Exception:  # pragma: no cover - defensive
            pass

    body_text = "\n".join(filter(None, text_parts)).strip()
    if not body_text:
        return ""
    cleaned = " ".join(body_text.split())
    if len(cleaned) > max_length:
        return cleaned[: max_length - 1] + "…"
    return cleaned
