from __future__ import annotations

import os
from pathlib import Path


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return max(minimum, min(maximum, value))


class Settings:
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", "/data/jobs"))

    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    image_model: str = os.getenv("IMAGE_MODEL", "gpt-image-2")
    image_size: str = os.getenv("IMAGE_SIZE", "2560x1440")
    image_quality: str = os.getenv("IMAGE_QUALITY", "medium")

    max_active_jobs: int = _int_env("MAX_ACTIVE_JOBS", 1, 1, 2)
    max_image_concurrency_per_job: int = _int_env("MAX_IMAGE_CONCURRENCY_PER_JOB", 5, 2, 5)
    max_image_retries: int = _int_env("MAX_IMAGE_RETRIES", 2, 0, 5)
    max_queued_jobs: int = _int_env("MAX_QUEUED_JOBS", 20, 1, 200)

    default_page_count: int = _int_env("DEFAULT_PAGE_COUNT", 8, 1, 30)
    max_page_count: int = _int_env("MAX_PAGE_COUNT", 30, 1, 60)
    min_page_count: int = _int_env("MIN_PAGE_COUNT", 1, 1, 30)

    api_token: str = os.getenv("API_TOKEN", "")

    cors_allow_origins: list[str] = [
        item.strip()
        for item in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
        if item.strip()
    ]


settings = Settings()
