from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .pipeline.job_store import create_job, fail_job, job_dir, read_status
from .schemas import JobCreateResponse, JobStatusResponse, StyleInfo
from .styles import list_styles, load_style
from .worker import job_queue


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await job_queue.start()
    try:
        yield
    finally:
        await job_queue.stop()


app = FastAPI(
    title="PPT Generation Service",
    description="Generate image-based PPTX decks from Markdown or PDF files.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def require_api_token(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
) -> None:
    if not settings.api_token:
        return
    token = x_api_token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != settings.api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def _status_response(status: dict[str, object]) -> JobStatusResponse:
    download_url = None
    if status.get("status") == "completed":
        download_url = f"/jobs/{status['job_id']}/download"
    return JobStatusResponse(
        job_id=str(status["job_id"]),
        status=status["status"],  # type: ignore[arg-type]
        total_slides=int(status.get("total_slides") or 0),
        completed_slides=int(status.get("completed_slides") or 0),
        page_count=status.get("page_count") if isinstance(status.get("page_count"), int) else None,
        language=str(status.get("language") or "zh"),
        style=str(status.get("style") or ""),
        image_concurrency=int(status.get("image_concurrency") or 2),
        error_message=status.get("error_message")
        if isinstance(status.get("error_message"), str)
        else None,
        created_at=str(status["created_at"]),
        updated_at=str(status["updated_at"]),
        download_url=download_url,
    )


def _validate_language(language: str) -> str:
    language = language.strip().lower()
    if language not in {"zh", "en"}:
        raise HTTPException(status_code=400, detail="language must be zh or en")
    return language


def _validate_page_count(page_count: Optional[int]) -> Optional[int]:
    if page_count is None:
        return None
    if page_count < settings.min_page_count or page_count > settings.max_page_count:
        raise HTTPException(
            status_code=400,
            detail=f"page_count must be between {settings.min_page_count} and {settings.max_page_count}",
        )
    return page_count


def _validate_image_concurrency(image_concurrency: int) -> int:
    if image_concurrency < 2 or image_concurrency > 5:
        raise HTTPException(status_code=400, detail="image_concurrency must be between 2 and 5")
    return min(image_concurrency, settings.max_image_concurrency_per_job)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/styles", response_model=list[StyleInfo], dependencies=[Depends(require_api_token)])
async def styles() -> list[StyleInfo]:
    return list_styles()


@app.post("/jobs", response_model=JobCreateResponse, dependencies=[Depends(require_api_token)])
async def create_ppt_job(
    file: UploadFile = File(...),
    style: str = Form("clean-professional"),
    page_count: Optional[int] = Form(default=None),
    language: str = Form("zh"),
    title: Optional[str] = Form(default=None),
    image_concurrency: int = Form(2),
) -> JobCreateResponse:
    try:
        load_style(style)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    language = _validate_language(language)
    page_count = _validate_page_count(page_count)
    image_concurrency = _validate_image_concurrency(image_concurrency)

    try:
        status = create_job(
            upload_file=file.file,
            filename=file.filename or "input",
            style=style,
            language=language,
            page_count=page_count,
            image_concurrency=image_concurrency,
            title=title.strip() if title and title.strip() else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        job_queue.submit(str(status["job_id"]))
    except asyncio.QueueFull as exc:
        fail_job(str(status["job_id"]), "Job queue is full")
        raise HTTPException(status_code=429, detail="Job queue is full") from exc

    return JobCreateResponse(
        job_id=str(status["job_id"]),
        status="queued",
        page_count=page_count,
        language=language,
        image_concurrency=image_concurrency,
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse, dependencies=[Depends(require_api_token)])
async def get_job(job_id: str) -> JobStatusResponse:
    try:
        return _status_response(read_status(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/jobs/{job_id}/download", dependencies=[Depends(require_api_token)])
async def download_job(job_id: str) -> FileResponse:
    try:
        status = read_status(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    if status.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Job is not completed")

    output_path = job_dir(job_id) / str(status.get("output_path") or "output.pptx")
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="PPTX file not found")

    return FileResponse(
        path=output_path,
        filename=f"{job_id}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


