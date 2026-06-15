from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from openai import AsyncOpenAI
from pydantic import ValidationError

from ..config import settings
from ..schemas import DeckSpec
from ..styles import StyleInfo
from .job_store import append_log


MAX_SOURCE_CHARS = 60_000


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])

    if not isinstance(data, dict):
        raise ValueError("DeepSeek response must be a JSON object")
    return data


def _validate_deck_spec(data: dict[str, Any], *, expected_page_count: int) -> DeckSpec:
    spec = DeckSpec.model_validate(data)
    if len(spec.slides) != expected_page_count:
        raise ValueError(
            f"Expected {expected_page_count} slides, got {len(spec.slides)} slides"
        )
    indexes = [slide.index for slide in spec.slides]
    expected = list(range(1, expected_page_count + 1))
    if indexes != expected:
        raise ValueError(f"Slide indexes must be continuous: expected {expected}, got {indexes}")
    return spec


def _system_prompt() -> str:
    return (
        "You are a senior presentation planner. "
        "Return strict JSON only. Do not wrap the JSON in Markdown. "
        "The JSON must match the requested schema exactly."
    )


def _planning_prompt(
    *,
    source_text: str,
    style_info: StyleInfo,
    style_reference: str,
    language: str,
    page_count: int,
    title: Optional[str],
) -> str:
    source = source_text[:MAX_SOURCE_CHARS]
    title_requirement = title or "Generate a concise title from the source content."
    return f"""
Create an image-based PPT deck specification.

Requirements:
- Output language: {language}
- Slide count: exactly {page_count}
- Title requirement: {title_requirement}
- Style id: {style_info.id}
- Style name: {style_info.name}
- Every slide will be generated as one full 16:9 image by gpt-image-2.
- Each image_prompt must be a detailed visual prompt for one complete 16:9 presentation slide.
- Keep slide text concise and readable. Avoid dense paragraphs.
- Do not include page numbers unless the content requires them.
- Speaker notes should be useful for presenting the slide.

Style reference:
{style_reference}

Return JSON in this shape:
{{
  "title": "Deck title",
  "language": "{language}",
  "style": "{style_info.id}",
  "slides": [
    {{
      "index": 1,
      "title": "Slide title",
      "key_points": ["Point A", "Point B"],
      "image_prompt": "A detailed full-slide 16:9 image prompt...",
      "speaker_note": "Speaker note for this slide."
    }}
  ]
}}

Source content:
{source}
""".strip()


def _repair_prompt(raw: str, error: str, expected_page_count: int) -> str:
    return f"""
The previous response was invalid.

Validation error:
{error}

Fix the response and return strict JSON only.

Rules:
- The JSON must contain exactly {expected_page_count} slides.
- Slide indexes must be continuous from 1 to {expected_page_count}.
- Every slide must include index, title, key_points, image_prompt, and speaker_note.
- Do not include Markdown fences.

Previous response:
{raw}
""".strip()


async def plan_deck(
    *,
    job_id: str,
    source_text: str,
    style_info: StyleInfo,
    style_reference: str,
    language: str,
    page_count: int,
    title: Optional[str],
    output_path: Path,
) -> DeckSpec:
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set")

    if len(source_text) > MAX_SOURCE_CHARS:
        append_log(job_id, f"source text truncated from {len(source_text)} to {MAX_SOURCE_CHARS} chars")

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": _planning_prompt(
                source_text=source_text,
                style_info=style_info,
                style_reference=style_reference,
                language=language,
                page_count=page_count,
                title=title,
            ),
        },
    ]

    raw = ""
    last_error = ""
    for attempt in range(1, 4):
        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        try:
            data = _extract_json_object(raw)
            spec = _validate_deck_spec(data, expected_page_count=page_count)
            output_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
            append_log(job_id, f"DeepSeek planning succeeded on attempt {attempt}")
            return spec
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)
            append_log(job_id, f"DeepSeek planning attempt {attempt} invalid: {last_error}")
            messages = [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _repair_prompt(raw, last_error, page_count)},
            ]

    raise ValueError(f"DeepSeek returned invalid deck JSON after retries: {last_error}")
