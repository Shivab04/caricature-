"""Claude-powered steps: describe a student's likeness, and review a generated caricature."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import List, Optional, Type, TypeVar

import anthropic
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from .config import Settings

T = TypeVar("T", bound=BaseModel)


# --------------------------------------------------------------------------- schemas


class StudentProfile(BaseModel):
    """Visual likeness notes used to steer the image model."""

    apparent_age_range: str = Field(description="e.g. '5-7 years'")
    face_shape: str
    skin_tone: str = Field(description="Purely visual description, e.g. 'warm medium-brown with golden undertones'")
    hair: str = Field(description="Colour, length, texture, parting, how it is tied, flyaways")
    eyes: str
    eyebrows: str
    nose: str
    mouth_and_smile: str
    ears: str
    distinctive_features: List[str] = Field(description="Dimples, freckles, moles, gap teeth, glasses, etc.")
    accessories: List[str] = Field(description="Earrings, hair clips, bindi, headband, etc.")
    clothing_in_photo: str
    caricature_exaggerations: List[str] = Field(
        description="2-4 gentle, flattering exaggerations that will make the caricature instantly recognisable"
    )
    likeness_summary: str = Field(description="One or two sentences capturing what makes this face recognisable")


class ReviewResult(BaseModel):
    likeness_score: int = Field(description="1-10: would classmates instantly recognise this child?")
    style_score: int = Field(description="1-10: how closely it matches the style reference")
    problems: List[str] = Field(description="Concrete defects: wrong hair colour, extra fingers, cropped feet, text, etc.")
    fix_instructions: str = Field(description="Precise instructions for the next generation attempt; empty if none")
    head_box: List[float] = Field(
        description="Bounding box of the character's head (including hair) as [x0, y0, x1, y1], each 0-1 of image size"
    )
    neck_point: List[float] = Field(description="[x, y] 0-1: base of the neck, used as the bobble-head pivot")
    torso_box: List[float] = Field(
        description="Box from shoulders to hips including both arms, as [x0, y0, x1, y1], 0-1; exclude props"
    )
    character_box: List[float] = Field(description="Bounding box of the whole character as [x0, y0, x1, y1], 0-1")
    ground_y: float = Field(description="0-1: y position of the lowest foot / ground contact point")


# --------------------------------------------------------------------------- helpers


def image_block(path: Path, max_side: int = 1568) -> dict:
    """Load any photo (fixing phone EXIF rotation), downscale, return a base64 image block."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=92)
    data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


class ClaudeVision:
    def __init__(self, settings: Settings, client: Optional[anthropic.Anthropic] = None):
        self.settings = settings
        self.client = client or anthropic.Anthropic()

    def _parse(self, system: str, content: list, schema: Type[T]) -> T:
        response = self.client.beta.messages.parse(
            model=self.settings.claude_model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            output_config={"effort": self.settings.claude_effort},
            # If a safety classifier declines, retry on a fallback model automatically.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            details = response.stop_details.explanation if response.stop_details else "no details"
            raise RuntimeError(f"Claude declined the request: {details}")
        if response.parsed_output is None:
            raise RuntimeError(f"Claude returned no structured output (stop_reason={response.stop_reason})")
        return response.parsed_output

    # ---------------------------------------------------------------- analyse

    def describe_student(self, photo: Path) -> StudentProfile:
        system = (
            "You are the art director for a school's caricature project. Teachers upload a photo of a "
            "student, and an illustrator model draws a warm, friendly caricature of them. Your job is to "
            "write likeness notes so precise that the illustration is unmistakably this child. Describe only "
            "what is visible, in neutral visual terms (colours, shapes, proportions). Never guess ethnicity, "
            "religion or other sensitive traits, and keep every exaggeration kind and flattering - these are "
            "children and the drawings will be shown to their families."
        )
        content = [
            image_block(photo),
            {"type": "text", "text": "Write likeness notes for this student."},
        ]
        return self._parse(system, content, StudentProfile)

    # ---------------------------------------------------------------- review

    def review(self, photo: Path, caricature: Path, style_reference: Path, activity: str) -> ReviewResult:
        system = (
            "You are a strict but kind art director reviewing an AI-generated caricature of a school student. "
            "Compare it with the original photo (likeness) and the style reference (art style). Look carefully "
            "for generation defects: wrong hair or skin colour, extra or missing fingers, malformed hands or "
            "feet, cropped limbs, stray text or watermarks, an unflattering or scary face, a background that is "
            "not plain white. Also locate the head, neck and body so the image can be animated."
        )
        content = [
            {"type": "text", "text": "Image 1 - original photo of the student:"},
            image_block(photo),
            {"type": "text", "text": "Image 2 - style reference (the look we want):"},
            image_block(style_reference),
            {"type": "text", "text": "Image 3 - the generated caricature to review:"},
            image_block(caricature),
            {"type": "text", "text": f"The requested activity was: {activity}. Review image 3."},
        ]
        return self._parse(system, content, ReviewResult)
