from __future__ import annotations

from pathlib import Path

from .schemas import StyleInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "skills" / "codex-ppt" / "references"

STYLE_FILES: dict[str, tuple[str, str, str]] = {
    "clean-professional": ("清爽专业风", "清爽专业风.md", "清爽、克制、适合通用汇报。"),
    "scientific-defense": ("科研答辩风", "科研答辩风.md", "适合论文、科研项目、答辩材料。"),
    "mckinsey-style": ("麦肯锡风格", "麦肯锡风格.md", "适合商业汇报、咨询分析、结论先行表达。"),
    "handdrawn-technical": ("手绘技术解释风", "手绘技术解释风.md", "适合技术讲解、课程和概念解释。"),
    "data-dashboard": ("数据仪表盘风", "数据仪表盘风.md", "适合数据分析、指标监控和经营看板。"),
    "creative-magazine": ("创意杂志风", "创意杂志风.md", "适合偏视觉化、传播感强的内容。"),
    "e-ink-magazine": ("电子墨水杂志风", "电子墨水杂志风.md", "适合黑白灰、高阅读感的内容。"),
    "retro-flat-illustration": ("复古扁平插画风", "复古扁平插画风.md", "适合轻松、故事化的介绍。"),
    "handdrawn-whiteboard": ("手绘白板风", "手绘白板风.md", "适合教学、培训和白板推演。"),
    "warm-handmade": ("温暖手工风", "温暖手工风.md", "适合温和、手作、生活化主题。"),
}


def list_styles() -> list[StyleInfo]:
    return [
        StyleInfo(id=style_id, name=name, description=description)
        for style_id, (name, _filename, description) in STYLE_FILES.items()
    ]


def load_style(style_id: str) -> tuple[StyleInfo, str]:
    if style_id not in STYLE_FILES:
        allowed = ", ".join(sorted(STYLE_FILES))
        raise ValueError(f"Unknown style '{style_id}'. Allowed styles: {allowed}")
    name, filename, description = STYLE_FILES[style_id]
    path = REFERENCE_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Style reference file not found: {path}")
    return StyleInfo(id=style_id, name=name, description=description), path.read_text(encoding="utf-8")
