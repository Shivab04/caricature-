"""The caricature agent: photo -> likeness notes -> generate -> self-review/retry -> animate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .animate import Layout, animate_still
from .claude_vision import ClaudeVision, ReviewResult
from .config import Settings
from .generate import Generator
from .prompts import image_prompt, video_prompt


@dataclass
class StudentJob:
    name: str
    photo: Path
    activity: Optional[str] = None
    outfit: Optional[str] = None


@dataclass
class StudentResult:
    name: str
    folder: Path
    caricature: Optional[Path] = None
    animations: dict = field(default_factory=dict)
    likeness_score: Optional[int] = None
    style_score: Optional[int] = None
    attempts: int = 0
    error: Optional[str] = None


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "student"


class CaricatureAgent:
    def __init__(self, settings: Optional[Settings] = None, log: Callable[[str], None] = print):
        self.settings = settings or Settings()
        self.vision = ClaudeVision(self.settings)
        self.generator = Generator(self.settings)
        self.log = log

    def run(self, job: StudentJob, out_root: Path, animation: str = "both") -> StudentResult:
        folder = out_root / slugify(job.name)
        folder.mkdir(parents=True, exist_ok=True)
        result = StudentResult(name=job.name, folder=folder)
        try:
            self._run(job, folder, animation, result)
        except Exception as exc:  # keep a batch going if one student fails
            result.error = f"{type(exc).__name__}: {exc}"
            self.log(f"[{job.name}] FAILED - {result.error}")
        return result

    def _run(self, job: StudentJob, folder: Path, animation: str, result: StudentResult) -> None:
        s = self.settings
        self.log(f"[{job.name}] 1/3 reading the photo with Claude...")
        profile = self.vision.describe_student(job.photo)
        (folder / "likeness_notes.json").write_text(profile.model_dump_json(indent=2))

        best: Optional[tuple[int, Path, ReviewResult]] = None
        fix = ""
        for attempt in range(1, s.max_attempts + 1):
            result.attempts = attempt
            self.log(f"[{job.name}] 2/3 drawing caricature (attempt {attempt}/{s.max_attempts})...")
            prompt = image_prompt(profile, job.activity, job.outfit, fix)
            (folder / f"prompt_attempt{attempt}.txt").write_text(prompt)
            draft = self.generator.caricature(job.photo, prompt, folder / f"attempt{attempt}.png")

            review = self.vision.review(job.photo, draft, s.style_reference, job.activity or "the default hoop-hopping scene")
            (folder / f"review_attempt{attempt}.json").write_text(review.model_dump_json(indent=2))
            score = review.likeness_score * 2 + review.style_score - len(review.problems)
            self.log(f"[{job.name}]     likeness {review.likeness_score}/10, style {review.style_score}/10, "
                     f"{len(review.problems)} problem(s)")
            if best is None or score > best[0]:
                best = (score, draft, review)
            if (review.likeness_score >= s.min_likeness_score and review.style_score >= s.min_style_score
                    and not review.problems):
                break
            fix = review.fix_instructions or "; ".join(review.problems)

        assert best is not None
        _, draft, review = best
        final = folder / "caricature.png"
        final.write_bytes(draft.read_bytes())
        result.caricature = final
        result.likeness_score, result.style_score = review.likeness_score, review.style_score

        if animation == "none":
            return
        self.log(f"[{job.name}] 3/3 animating...")
        if animation in ("video", "both"):
            try:
                mp4 = self.generator.animate_video(final, video_prompt(job.activity), folder / "caricature_video.mp4")
                result.animations["video"] = str(mp4)
            except Exception as exc:
                self.log(f"[{job.name}]     AI video unavailable ({exc}); using bobble-head animation instead")
                animation = "both"
        if animation in ("procedural", "both") or "video" not in result.animations:
            layout = Layout(review.head_box, review.neck_point, review.torso_box, review.character_box,
                            review.ground_y)
            result.animations.update(animate_still(final, folder, "caricature_bounce", layout))
        (folder / "result.json").write_text(json.dumps(
            {k: str(v) if isinstance(v, Path) else v for k, v in result.__dict__.items()}, indent=2))
        self.log(f"[{job.name}] done -> {folder}")
