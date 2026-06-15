from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from .config import settings
from .pipeline.assemble import assemble_pptx
from .pipeline.extract_text import extract_text, suggest_page_count
from .pipeline.generate_images import generate_slide_images
from .pipeline.job_store import (
    append_log,
    fail_job,
    job_dir,
    mark_interrupted_jobs_failed,
    read_status,
    update_status,
)
from .pipeline.plan_with_deepseek import plan_deck
from .styles import load_style


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=settings.max_queued_jobs)
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False

    @property
    def queued_count(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._started:
            return
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        mark_interrupted_jobs_failed()
        for idx in range(settings.max_active_jobs):
            self._tasks.append(asyncio.create_task(self._run_worker(idx + 1)))
        self._started = True

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._started = False

    def submit(self, job_id: str) -> None:
        self._queue.put_nowait(job_id)

    async def _run_worker(self, worker_id: int) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                append_log(job_id, f"worker {worker_id} picked job")
                await process_job(job_id)
            except Exception as exc:
                fail_job(job_id, str(exc))
            finally:
                self._queue.task_done()


def _resolve_input_path(status: dict[str, object], path: Path) -> Path:
    raw = status.get("input_path")
    if not raw:
        raise ValueError("Job status does not contain input_path")
    return path / str(raw)


def _effective_page_count(status: dict[str, object], extracted: str) -> int:
    raw_page_count = status.get("page_count")
    if raw_page_count is None:
        count = suggest_page_count(extracted, max_page_count=settings.max_page_count)
        return max(settings.min_page_count, min(settings.max_page_count, count))

    count = int(raw_page_count)
    if count < settings.min_page_count or count > settings.max_page_count:
        raise ValueError(
            f"page_count must be between {settings.min_page_count} and {settings.max_page_count}"
        )
    return count


async def process_job(job_id: str) -> None:
    path = job_dir(job_id)
    status = read_status(job_id)

    update_status(job_id, status="extracting", error_message=None)
    input_path = _resolve_input_path(status, path)
    extracted = extract_text(input_path)
    (path / "extracted.txt").write_text(extracted, encoding="utf-8")
    append_log(job_id, f"extracted {len(extracted)} chars from {input_path.name}")

    page_count = _effective_page_count(status, extracted)
    update_status(job_id, page_count=page_count, total_slides=page_count)

    update_status(job_id, status="planning")
    style_id = str(status["style"])
    style_info, style_reference = load_style(style_id)
    deck_spec = await plan_deck(
        job_id=job_id,
        source_text=extracted,
        style_info=style_info,
        style_reference=style_reference,
        language=str(status.get("language") or "zh"),
        page_count=page_count,
        title=status.get("title") if isinstance(status.get("title"), str) else None,
        output_path=path / "deck_spec.json",
    )

    update_status(job_id, status="generating_images", completed_slides=0)
    image_concurrency = int(status.get("image_concurrency") or 2)
    await generate_slide_images(
        job_id=job_id,
        deck_spec=deck_spec,
        output_dir=path / "origin_image",
        image_concurrency=image_concurrency,
    )

    update_status(job_id, status="assembling")
    output_path = assemble_pptx(job_id=job_id, job_path=path, deck_spec=deck_spec)

    update_status(
        job_id,
        status="completed",
        completed_slides=page_count,
        output_path=output_path.name,
        error_message=None,
    )
    append_log(job_id, "job completed")


job_queue = JobQueue()
