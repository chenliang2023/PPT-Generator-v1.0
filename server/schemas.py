from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


JobStatus = Literal[
    "queued",
    "extracting",
    "planning",
    "generating_images",
    "assembling",
    "completed",
    "failed",
]


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    total_slides: int = 0
    completed_slides: int = 0
    page_count: Optional[int] = None
    language: str = "zh"
    style: str
    image_concurrency: int
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    download_url: Optional[str] = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    page_count: Optional[int] = None
    language: str
    image_concurrency: int


class StyleInfo(BaseModel):
    id: str
    name: str
    description: str = ""


class SlideSpec(BaseModel):
    index: int = Field(ge=1)
    title: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)
    image_prompt: str = Field(min_length=20)
    speaker_note: str = ""


class DeckSpec(BaseModel):
    title: str = Field(min_length=1)
    language: str
    style: str
    slides: list[SlideSpec] = Field(min_length=1)
