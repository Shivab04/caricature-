"""Runtime settings, overridable with environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_STYLE_REFERENCE = PACKAGE_DIR.parent / "assets" / "style_reference.png"


@dataclass
class Settings:
    # Claude does the "thinking" parts: reading the photo and judging the result.
    claude_model: str = field(default_factory=lambda: os.getenv("CARICATURE_CLAUDE_MODEL", "claude-opus-5-5"))
    claude_effort: str = field(default_factory=lambda: os.getenv("CARICATURE_CLAUDE_EFFORT", "high"))

    # Image + video generation (OpenAI). Claude cannot draw images itself.
    image_model: str = field(default_factory=lambda: os.getenv("CARICATURE_IMAGE_MODEL", "gpt-image-2"))
    image_quality: str = field(default_factory=lambda: os.getenv("CARICATURE_IMAGE_QUALITY", "high"))
    image_size: str = "1024x1536"  # portrait, same as the style reference
    video_model: str = field(default_factory=lambda: os.getenv("CARICATURE_VIDEO_MODEL", "sora-2"))
    video_seconds: str = field(default_factory=lambda: os.getenv("CARICATURE_VIDEO_SECONDS", "4"))
    video_size: str = "720x1280"

    style_reference: Path = field(
        default_factory=lambda: Path(os.getenv("CARICATURE_STYLE_REFERENCE", str(DEFAULT_STYLE_REFERENCE)))
    )

    # Agent loop: regenerate until the reviewer is happy, up to this many tries.
    max_attempts: int = field(default_factory=lambda: int(os.getenv("CARICATURE_MAX_ATTEMPTS", "3")))
    min_likeness_score: int = 7  # 1-10
    min_style_score: int = 7  # 1-10
