from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Optional
from uuid import uuid4

from ..config import settings


INPUT_EXTENSIONS = {".md", ".pdf"}
IN_PROGRESS_STATUSES = {"queued", "extracting", "planning", "generating_images", "assembling"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_dir(job_id: str) -> Path:
    return settings.output_dir / job_id


def status_path(job_id: str) -> Path:
    return job_dir(job_id) / "status.json"


def log_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.log"


def append_log(job_id: str, message: str) -> None:
    path = log_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{utc_now()}] {message}\n")


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def read_status(job_id: str) -> dict[str, Any]:
    path = status_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Job not found: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(job_id: str, status: dict[str, Any]) -> dict[str, Any]:
    status["updated_at"] = utc_now()
    _write_json_atomic(status_path(job_id), status)
    return status


def update_status(job_id: str, **updates: Any) -> dict[str, Any]:
    status = read_status(job_id)
    status.update(updates)
    return write_status(job_id, status)


def fail_job(job_id: str, message: str) -> dict[str, Any]:
    append_log(job_id, f"FAILED: {message}")
    return update_status(job_id, status="failed", error_message=message)


def create_job(
    *,
    upload_file: BinaryIO,
    filename: str,
    style: str,
    language: str,
    page_count: Optional[int],
    image_concurrency: int,
    title: Optional[str],
) -> dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext not in INPUT_EXTENSIONS:
        allowed = ", ".join(sorted(INPUT_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {allowed}")

    job_id = str(uuid4())
    path = job_dir(job_id)
    path.mkdir(parents=True, exist_ok=False)

    input_name = f"input{ext}"
    with (path / input_name).open("wb") as f:
        shutil.copyfileobj(upload_file, f)

    now = utc_now()
    status = {
        "job_id": job_id,
        "status": "queued",
        "style": style,
        "language": language,
        "page_count": page_count,
        "image_concurrency": image_concurrency,
        "title": title,
        "input_filename": filename,
        "input_path": input_name,
        "total_slides": 0,
        "completed_slides": 0,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    _write_json_atomic(path / "status.json", status)
    append_log(job_id, f"created job for {filename}")
    return status


def list_job_statuses() -> list[dict[str, Any]]:
    if not settings.output_dir.exists():
        return []
    statuses: list[dict[str, Any]] = []
    for path in settings.output_dir.iterdir():
        status_file = path / "status.json"
        if not status_file.exists():
            continue
        try:
            statuses.append(json.loads(status_file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return statuses


def mark_interrupted_jobs_failed() -> None:
    for status in list_job_statuses():
        if status.get("status") in IN_PROGRESS_STATUSES:
            job_id = status["job_id"]
            fail_job(job_id, "Service restarted while this job was not completed.")
