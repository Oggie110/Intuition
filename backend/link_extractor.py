from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

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


def _is_private_or_local_target(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return True

    if parsed.scheme not in {"http", "https"}:
        return True

    host = parsed.hostname
    if not host:
        return True

    # Reject obvious local hostnames.
    lowered_host = host.lower()
    if lowered_host in {"localhost", "localhost.localdomain"} or lowered_host.endswith(".local"):
        return True

    # If host is an IP literal, validate directly.
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        pass

    # Resolve DNS and reject if any resolved address is private/local.
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except Exception:
        # Fail closed for unknown/unresolvable hosts.
        return True

    for info in infos:
        sockaddr = info[4]
        resolved_ip_str = sockaddr[0]
        try:
            resolved_ip = ipaddress.ip_address(resolved_ip_str)
        except ValueError:
            continue
        if (
            resolved_ip.is_private
            or resolved_ip.is_loopback
            or resolved_ip.is_link_local
            or resolved_ip.is_multicast
            or resolved_ip.is_reserved
            or resolved_ip.is_unspecified
        ):
            return True
    return False


def fetch_and_extract(url: str, max_chars: int = 5000) -> LinkedContent:
    if _is_private_or_local_target(url):
        return LinkedContent(linked_url=url, linked_title=None, linked_content="")
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

