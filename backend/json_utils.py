from __future__ import annotations

import json


def parse_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model response")

    # First try direct JSON parse.
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Handle fenced code block outputs.
    if "```" in raw:
        chunks = raw.split("```")
        for chunk in chunks:
            candidate = chunk.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except Exception:
                continue

    # Last resort: parse from first '{' to last '}'.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1]
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data

    raise ValueError("Model response did not contain a valid JSON object")


def repair_json_with_model(client, *, model: str, raw_text: str) -> dict:
    msg = client.messages.create(
        model=model,
        max_tokens=1200,
        system=(
            "You convert malformed model output into one valid JSON object.\n"
            "Return ONLY JSON. No markdown fences. No commentary."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    "Convert the following text to a single valid JSON object while preserving intent.\n\n"
                    f"{raw_text}"
                ),
            }
        ],
    )

    text = ""
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            text += block.text
    return parse_json_object(text)

