from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable

from ..schemas import DeckSpec
from .job_store import append_log


REPO_ROOT = Path(__file__).resolve().parents[2]
ASSEMBLE_SCRIPT = REPO_ROOT / "skills" / "codex-ppt" / "scripts" / "assemble_ppt.py"


def write_speech_md(deck_spec: DeckSpec, output_path: Path) -> None:
    lines: list[str] = [f"# {deck_spec.title}", ""]
    for slide in deck_spec.slides:
        lines.append(f"## Slide {slide.index}: {slide.title}")
        lines.append("")
        lines.append(slide.speaker_note.strip() or "No speaker notes.")
        lines.append("")
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _load_create_presentation() -> Callable[..., bool]:
    spec = importlib.util.spec_from_file_location("codex_ppt_assemble_ppt", ASSEMBLE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load assemble script: {ASSEMBLE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_presentation


def assemble_pptx(*, job_id: str, job_path: Path, deck_spec: DeckSpec) -> Path:
    origin_image_dir = job_path / "origin_image"
    image_files = [
        origin_image_dir / f"slide_{slide.index:02d}.png"
        for slide in deck_spec.slides
    ]
    missing = [str(path) for path in image_files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing generated slide images: {missing}")

    speech_path = job_path / "speech.md"
    write_speech_md(deck_spec, speech_path)

    output_path = job_path / "output.pptx"
    notes = {slide.index: slide.speaker_note for slide in deck_spec.slides}
    create_presentation = _load_create_presentation()
    ok = create_presentation(
        [str(path) for path in image_files],
        str(output_path),
        "16:9",
        notes,
    )
    if not ok:
        raise RuntimeError("PPT assembly failed")

    append_log(job_id, f"PPT assembled: {output_path.name}")
    return output_path
