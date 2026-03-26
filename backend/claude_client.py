from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from anthropic import Anthropic

from backend.json_utils import parse_json_object, repair_json_with_model


class ClaudeError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrichmentResult:
    summary: str
    key_insights: list[str]
    tags: list[dict[str, str]]  # {name, kind}
    category: str


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def model_name() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def enrich_bookmark(payload: dict[str, Any]) -> EnrichmentResult:
    if not is_configured():
        raise ClaudeError("ANTHROPIC_API_KEY is not set")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system = (
        "You are an information extraction and tagging engine.\n"
        "Return ONLY valid JSON that matches the provided schema.\n"
        "Do not include markdown fences, comments, or any extra keys."
    )
    user = (
        "You will enrich a social bookmark.\n\n"
        "## Bookmark\n"
        f"tweet_id: {payload.get('tweet_id')}\n"
        f"author: @{payload.get('author_username')} ({payload.get('author_name')})\n"
        f"tweet_date: {payload.get('tweet_date')}\n"
        f"tweet_url: {payload.get('url')}\n\n"
        "tweet_text:\n"
        f"{payload.get('body')}\n\n"
        f"media_urls: {json.dumps(payload.get('media') or [], ensure_ascii=False)}\n\n"
        "## Linked page (if any)\n"
        f"linked_url: {payload.get('linked_url')}\n"
        f"linked_title: {payload.get('linked_title')}\n"
        "linked_text_excerpt (may be truncated to 5000 chars):\n"
        f"{payload.get('linked_content') or ''}\n\n"
        "## Task\n"
        "Produce:\n"
        "- a concise 2–3 sentence summary capturing the key idea and why it matters\n"
        "- 3–7 key insights (short bullets)\n"
        "- 3–5 topic tags (short noun phrases)\n"
        '- exactly one category from: ["dev-tools","music","business","research","misc"]\n\n'
        "## Output JSON schema\n"
        '{\n'
        '  "summary": string,\n'
        '  "key_insights": string[],\n'
        '  "tags": { "name": string, "kind": "topic"|"technology"|"person"|"company"|"concept"|"other" }[],\n'
        '  "category": "dev-tools"|"music"|"business"|"research"|"misc"\n'
        "}\n"
    )

    data = None
    last_err: Exception | None = None
    last_text = ""
    for attempt in range(2):
        retry_hint = (
            "\n\nIMPORTANT: Your previous response was not valid JSON. Return ONLY one valid JSON object."
            if attempt == 1
            else ""
        )
        try:
            msg = client.messages.create(
                model=model_name(),
                max_tokens=800,
                system=system,
                messages=[{"role": "user", "content": user + retry_hint}],
            )
        except Exception as e:
            last_err = e
            continue

        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        text = text.strip()
        last_text = text
        try:
            data = parse_json_object(text)
            break
        except Exception as e:
            last_err = e

    if data is None and last_text:
        try:
            data = repair_json_with_model(client, model=model_name(), raw_text=last_text)
        except Exception as e:
            last_err = e

    if data is None:
        if last_err and "authentication" in str(last_err).lower():
            raise ClaudeError("Anthropic authentication failed. Check ANTHROPIC_API_KEY in .env") from last_err
        raise ClaudeError("Claude did not return valid JSON") from last_err

    return _validate(data)


def _validate(data: dict[str, Any]) -> EnrichmentResult:
    summary = str(data.get("summary") or "").strip()
    key_insights = data.get("key_insights") or []
    tags = data.get("tags") or []
    category = str(data.get("category") or "").strip()

    if not summary:
        raise ClaudeError("Missing summary")
    if not isinstance(key_insights, list):
        raise ClaudeError("key_insights must be a list")
    key_insights = [str(x).strip() for x in key_insights if str(x).strip()]
    if not key_insights:
        raise ClaudeError("Missing key_insights")

    if not isinstance(tags, list):
        raise ClaudeError("tags must be a list")
    norm_tags: list[dict[str, str]] = []
    seen: set[str] = set()
    for t in tags:
        if isinstance(t, str):
            name = t.strip()
            kind = "topic"
        else:
            name = str((t or {}).get("name") or "").strip()
            kind = str((t or {}).get("kind") or "topic").strip()
        if not name:
            continue
        k = name.lower()
        if k in seen:
            continue
        seen.add(k)
        norm_tags.append({"name": name, "kind": kind or "topic"})

    if category not in {"dev-tools", "music", "business", "research", "misc"}:
        raise ClaudeError("Invalid category")

    return EnrichmentResult(summary=summary, key_insights=key_insights, tags=norm_tags, category=category)

