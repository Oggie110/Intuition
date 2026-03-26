from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup


URL_RE = re.compile(r"https?://[^\s)>\"]+")


@dataclass(frozen=True)
class LinkedContent:
    linked_url: Optional[str]
    linked_title: Optional[str]
    linked_content: str


def extract_candidate_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = URL_RE.findall(text)
    # De-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _is_unhelpful_url(url: str) -> bool:
    lowered = url.lower()
    return any(
        host in lowered
        for host in [
            "x.com/",
            "twitter.com/",
            "pbs.twimg.com/",
            "t.co/",
        ]
    )


def pick_link_url(body: str) -> Optional[str]:
    for u in extract_candidate_urls(body):
        if not _is_unhelpful_url(u):
            return u
    return None


def fetch_and_extract(url: str, max_chars: int = 5000) -> LinkedContent:
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=10.0),
            follow_redirects=True,
            headers={"User-Agent": "IntuitionBot/0.1 (+local)"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            final_url = str(resp.url)
            html = resp.text
    except Exception:
        return LinkedContent(linked_url=url, linked_title=None, linked_content="")

    title, text = html_to_text(html)
    if text:
        text = limit_text(text, max_chars=max_chars)
    return LinkedContent(linked_url=final_url, linked_title=title, linked_content=text or "")


def html_to_text(html: str) -> tuple[Optional[str], str]:
    soup = BeautifulSoup(html, "html.parser")

    # Drop non-content elements
    for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe"]):
        tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip() or None

    # Heuristic: prefer <article>, else body text
    container = soup.find("article") or soup.body or soup
    text = container.get_text(separator="\n", strip=True)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


def limit_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"

