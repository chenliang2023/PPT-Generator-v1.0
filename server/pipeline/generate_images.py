from __future__ import annotations

import asyncio
import base64
import re
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from ..config import settings
from ..schemas import DeckSpec, SlideSpec
from .job_store import append_log, update_status


def _extract_retry_after_seconds(exc: Exception) -> Optional[float]:
    for attr in ("retry_after", "retry_after_seconds"):
        val = getattr(exc, attr, None)
        if isinstance(val, (int, float)) and val >= 0:
            return float(val)
    match = re.search(r"retry[- ]after[:= ]+([0-9]+(?:\.[0-9]+)?)", str(exc), re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _is_transient_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    transient_markers = (
        "429",
        "rate limit",
        "too many requests",
        "timeout",
        "timed out",
        "tempor",
        "connection reset",
        "connection error",
        "service unavailable",
        "internal server error",
        "bad gateway",
        "gateway timeout",
        " 500",
        " 502",
        " 503",
        " 504",
    )
    return any(marker in name or marker in message for marker in transient_markers)


def _decode_image_b64(result: object) -> bytes:
    data = getattr(result, "data", None)
    if not data:
        raise ValueError("image API returned no data")

    first = data[0]
    b64 = getattr(first, "b64_json", None)
    if not b64:
        raise ValueError("image API response did not include b64_json")
    return base64.b64decode(b64)


def _validate_image(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"image file does not exist: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"image file is empty: {path}")
    try:
        from PIL import Image

        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        raise ValueError(f"image file cannot be opened by Pillow: {path}: {exc}") from exc


async def _generate_slide_once(client: AsyncOpenAI, slide: SlideSpec, out_path: Path) -> None:
    response = await client.images.generate(
        model=settings.image_model,
        prompt=slide.image_prompt,
        n=1,
        size=settings.image_size,
        quality=settings.image_quality,
        output_format="png",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_decode_image_b64(response))
    _validate_image(out_path)


async def _generate_slide_with_retries(
    *,
    client: AsyncOpenAI,
    job_id: str,
    slide: SlideSpec,
    out_path: Path,
) -> None:
    max_attempts = settings.max_image_retries + 1
    for attempt in range(1, max_attempts + 1):
        try:
            append_log(job_id, f"slide {slide.index}: image generation attempt {attempt}/{max_attempts}")
            await _generate_slide_once(client, slide, out_path)
            append_log(job_id, f"slide {slide.index}: image generated at {out_path.name}")
            return
        except Exception as exc:
            is_last = attempt >= max_attempts
            transient = _is_transient_error(exc) or isinstance(exc, ValueError)
            append_log(
                job_id,
                f"slide {slide.index}: attempt {attempt}/{max_attempts} failed: "
                f"{exc.__class__.__name__}: {exc}",
            )
            if is_last or not transient:
                raise

            retry_after = _extract_retry_after_seconds(exc)
            if retry_after is None:
                retry_after = [2, 5, 10, 20, 40][min(attempt - 1, 4)]
            append_log(job_id, f"slide {slide.index}: retrying in {retry_after:.1f}s")
            await asyncio.sleep(retry_after)


async def generate_slide_images(
    *,
    job_id: str,
    deck_spec: DeckSpec,
    output_dir: Path,
    image_concurrency: int,
) -> None:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    effective_concurrency = min(
        max(2, image_concurrency),
        settings.max_image_concurrency_per_job,
        5,
    )
    append_log(job_id, f"image generation concurrency: {effective_concurrency}")

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
    )
    semaphore = asyncio.Semaphore(effective_concurrency)
    completed = 0
    completed_lock = asyncio.Lock()

    async def run_slide(slide: SlideSpec) -> None:
        nonlocal completed
        out_path = output_dir / f"slide_{slide.index:02d}.png"
        async with semaphore:
            await _generate_slide_with_retries(
                client=client,
                job_id=job_id,
                slide=slide,
                out_path=out_path,
            )
        async with completed_lock:
            completed += 1
            update_status(job_id, completed_slides=completed)

    results = await asyncio.gather(
        *(run_slide(slide) for slide in deck_spec.slides),
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, Exception)]
    if errors:
        first = errors[0]
        raise RuntimeError(f"image generation failed after automatic retries: {first}") from first
