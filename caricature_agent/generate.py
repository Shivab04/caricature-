"""Image and video generation via OpenAI (Claude reads images but does not draw them)."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Optional

import openai
from PIL import Image, ImageOps

from .config import Settings


def _png_upload(path: Path, name: str, max_side: int = 1536) -> tuple:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
    return (name, buf.getvalue(), "image/png")


def fit_on_white(src: Path, size: tuple[int, int]) -> bytes:
    """Letterbox an image onto a white canvas of exactly `size` (video models need an exact match)."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail(size, Image.LANCZOS)
        canvas = Image.new("RGB", size, "white")
        canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
    return buf.getvalue()


class Generator:
    def __init__(self, settings: Settings, client: Optional[openai.OpenAI] = None):
        self.settings = settings
        self.client = client or openai.OpenAI()

    def caricature(self, photo: Path, prompt: str, out_path: Path) -> Path:
        kwargs = {}
        # gpt-image-2 always works at high fidelity and rejects the parameter; older models need it.
        if self.settings.image_model.startswith("gpt-image-1"):
            kwargs["input_fidelity"] = "high"
        result = self.client.images.edit(
            model=self.settings.image_model,
            image=[
                _png_upload(photo, "student_photo.png"),
                _png_upload(self.settings.style_reference, "style_reference.png"),
            ],
            prompt=prompt,
            size=self.settings.image_size,
            quality=self.settings.image_quality,
            background="opaque",
            output_format="png",
            n=1,
            **kwargs,
        )
        out_path.write_bytes(base64.b64decode(result.data[0].b64_json))
        return out_path

    def animate_video(self, caricature: Path, prompt: str, out_path: Path) -> Path:
        width, height = (int(v) for v in self.settings.video_size.split("x"))
        video = self.client.videos.create_and_poll(
            model=self.settings.video_model,
            prompt=prompt,
            input_reference=("caricature.png", fit_on_white(caricature, (width, height)), "image/png"),
            seconds=self.settings.video_seconds,
            size=self.settings.video_size,
        )
        if video.status != "completed":
            error = getattr(video, "error", None)
            raise RuntimeError(f"Video generation {video.status}: {error}")
        self.client.videos.download_content(video.id, variant="video").write_to_file(out_path)
        return out_path
