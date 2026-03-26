from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional


SEPARATOR = "──────────────────────────────────────────────────"


class BirdError(RuntimeError):
    pass


@dataclass(frozen=True)
class BirdIdentity:
    username: str
    display_name: str


@dataclass(frozen=True)
class ParsedBookmark:
    tweet_id: str
    author_username: str
    author_name: str
    body: str
    tweet_date: str  # ISO-8601
    url: str
    media: list[str]
    raw_output: str


def default_bird_path() -> Path:
    return Path.home() / "bin" / "bird"


def is_installed(bird_path: Optional[Path] = None) -> bool:
    return (bird_path or default_bird_path()).exists()


def _run(bird_path: Path, args: list[str], timeout_s: int) -> str:
    try:
        proc = subprocess.run(
            [str(bird_path), *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as e:
        raise BirdError(f"Bird CLI not found at {bird_path}") from e
    except subprocess.TimeoutExpired as e:
        raise BirdError(f"Bird CLI timed out after {timeout_s}s") from e

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise BirdError(stderr or f"Bird CLI failed with exit code {proc.returncode}")
    return proc.stdout


def whoami(bird_path: Optional[Path] = None, timeout_s: int = 10) -> BirdIdentity:
    bp = bird_path or default_bird_path()
    out = _run(bp, ["whoami"], timeout_s=timeout_s).strip()
    # Example: "🙋 @username (Display Name)"
    m = re.search(r"@(?P<user>[A-Za-z0-9_]+)\s+\((?P<name>.+)\)\s*$", out)
    if not m:
        raise BirdError("Could not parse 'bird whoami' output")
    return BirdIdentity(username=m.group("user"), display_name=m.group("name"))


def fetch_bookmarks_raw(
    limit: int = 50, bird_path: Optional[Path] = None, timeout_s: int = 60
) -> str:
    bp = bird_path or default_bird_path()
    return _run(bp, ["bookmarks", "-n", str(limit)], timeout_s=timeout_s)


def parse_bookmarks(raw: str) -> list[ParsedBookmark]:
    blocks = [b.strip("\n") for b in raw.split(SEPARATOR)]
    blocks = [b.strip() for b in blocks if b.strip()]
    parsed: list[ParsedBookmark] = []
    for block in blocks:
        bm = _parse_block(block)
        if bm:
            parsed.append(bm)
    return parsed


def _parse_block(block: str) -> Optional[ParsedBookmark]:
    lines = [ln.rstrip("\n") for ln in block.splitlines() if ln.strip() != ""]
    if len(lines) < 3:
        return None

    header = lines[0].strip()
    m = re.match(r"^@(?P<user>[A-Za-z0-9_]+)\s+\((?P<name>.+)\):\s*$", header)
    if not m:
        return None
    author_username = m.group("user")
    author_name = m.group("name")

    media: list[str] = []
    body_lines: list[str] = []
    tweet_date_raw: Optional[str] = None
    url: Optional[str] = None

    for ln in lines[1:]:
        s = ln.strip()
        if s.startswith("📅 "):
            tweet_date_raw = s[len("📅 ") :].strip()
            continue
        if s.startswith("🔗 "):
            url = s[len("🔗 ") :].strip()
            continue
        if s.startswith("🎬 ") or s.startswith("🖼️ "):
            media.append(s[2:].strip())
            continue
        # Quote tweet ascii art and quoted URL are treated as body context
        body_lines.append(s)

    body = "\n".join(body_lines).strip()
    if not url or not tweet_date_raw:
        return None

    tweet_id = _tweet_id_from_url(url)
    tweet_date_iso = _to_iso8601(tweet_date_raw)

    return ParsedBookmark(
        tweet_id=tweet_id,
        author_username=author_username,
        author_name=author_name,
        body=body,
        tweet_date=tweet_date_iso,
        url=url,
        media=media,
        raw_output=block,
    )


def _tweet_id_from_url(url: str) -> str:
    m = re.search(r"/status/(?P<id>[0-9]+)", url)
    if not m:
        raise BirdError("Could not extract tweet_id from url")
    return m.group("id")


def _to_iso8601(date_str: str) -> str:
    # Example: "Thu Mar 26 03:52:14 +0000 2026"
    dt = parsedate_to_datetime(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

