"""Procedural animation: turns a still caricature into a looping bouncy 'bobble-head' GIF/MP4.

Runs locally, costs nothing, and works on any caricature on a white background. It is used when
AI video generation is disabled, unavailable, or fails. Only the head and upper body move, so props
on the ground (hoops, balls, books...) are never distorted.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


@dataclass
class Layout:
    """Where things are in the image, all as 0-1 fractions of width/height."""

    head_box: Sequence[float]  # x0, y0, x1, y1
    neck_point: Sequence[float]  # x, y
    torso_box: Sequence[float]  # x0, y0, x1, y1  (shoulders to hips, incl. arms)
    character_box: Sequence[float]  # x0, y0, x1, y1
    ground_y: float

    @classmethod
    def guess(cls, image: Image.Image) -> "Layout":
        """Heuristic layout from the non-white pixels, for when no reviewer layout is available."""
        arr = np.asarray(image.convert("RGB"))
        mask = arr.min(axis=2) < 235
        h, w = mask.shape
        ys, xs = np.nonzero(mask)
        if len(ys) == 0:
            return cls((0.3, 0.05, 0.7, 0.35), (0.5, 0.35), (0.25, 0.35, 0.75, 0.6), (0.1, 0.05, 0.9, 0.95), 0.95)
        top, bottom = ys.min(), ys.max()
        span = bottom - top
        head_bottom = top + int(span * 0.3)
        band_xs = xs[(ys >= top) & (ys <= head_bottom)]
        hx0, hx1 = np.percentile(band_xs, [3, 97])
        hip = top + int(span * 0.55)
        torso_xs = xs[(ys > head_bottom) & (ys <= hip)]
        tx0, tx1 = np.percentile(torso_xs, [2, 98]) if len(torso_xs) else (hx0, hx1)
        return cls(
            head_box=(hx0 / w, top / h, hx1 / w, head_bottom / h),
            neck_point=((hx0 + hx1) / 2 / w, head_bottom / h),
            torso_box=(tx0 / w, head_bottom / h, tx1 / w, hip / h),
            character_box=(xs.min() / w, top / h, xs.max() / w, bottom / h),
            ground_y=bottom / h,
        )


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _sparkle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple) -> None:
    if r < 1:
        return
    t = r * 0.22
    draw.polygon([(cx, cy - r), (cx + t, cy - t), (cx + r, cy), (cx + t, cy + t),
                  (cx, cy + r), (cx - t, cy + t), (cx - r, cy), (cx - t, cy - t)], fill=color)


def _sparkle_positions(layout: Layout, W: int, H: int, rng: random.Random, count: int = 6):
    """Sparkles in the white space beside the head, never on the character."""
    hx0, hy0, hx1, hy1 = layout.head_box
    head_w = (hx1 - hx0) * W
    specs = []
    for i in range(count):
        side = -1 if i % 2 == 0 else 1
        edge = hx0 * W if side < 0 else hx1 * W
        x = edge + side * rng.uniform(0.25, 0.75) * head_w
        y = rng.uniform(hy0 - 0.02, hy1) * H
        x = min(max(x, 0.03 * W), 0.97 * W)
        specs.append((x, y, rng.uniform(0.012, 0.02) * W, rng.random(),
                      rng.choice([(255, 196, 40), (255, 120, 160), (90, 180, 255), (120, 210, 110)])))
    return specs


def render_frames(
    still: Image.Image,
    layout: Optional[Layout] = None,
    frames: int = 24,
    bounce: float = 0.014,
    head_bob: float = 0.008,
    head_tilt_degrees: float = 5.0,
    sparkles: bool = True,
    seed: int = 7,
) -> List[Image.Image]:
    still = still.convert("RGB")
    layout = layout or Layout.guess(still)
    W, H = still.size
    src = np.asarray(still).astype(np.float32)

    # ---- body weight map: 1 over head + torso, easing to 0 below the hips (legs and props stay put).
    tx0, ty0, tx1, ty1 = layout.torso_box
    hx0, hy0, hx1, hy1 = layout.head_box
    hip = ty1 * H
    fade = max((ty1 - ty0) * H * 0.35, 1.0)  # ease out over the lower third of the torso
    ys = np.arange(H, dtype=np.float32)
    w_y = 1.0 - _smoothstep((ys - (hip - fade)) / fade)
    xs = np.arange(W, dtype=np.float32)
    left, right = min(tx0, hx0) * W, max(tx1, hx1) * W
    feather = 0.04 * W
    w_x = _smoothstep((xs - (left - feather)) / feather) * _smoothstep(((right + feather) - xs) / feather)
    weight = w_y[:, None] * w_x[None, :]

    # ---- head mask (feathered ellipse, padded for hair) + pivot at the neck.
    hb = (hx0 * W, hy0 * H, hx1 * W, hy1 * H)
    pad = 0.07 * (hb[2] - hb[0])
    head_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(head_mask).ellipse((hb[0] - pad, hb[1] - pad, hb[2] + pad, hb[3] + pad * 0.5), fill=255)
    head_mask = head_mask.filter(ImageFilter.GaussianBlur(pad * 0.5 + 1))
    pivot = (layout.neck_point[0] * W, layout.neck_point[1] * H)

    spark_specs = _sparkle_positions(layout, W, H, random.Random(seed)) if sparkles else []

    rows = np.arange(H, dtype=np.float32)[:, None]
    cols = np.broadcast_to(np.arange(W)[None, :], (H, W))
    out_frames = []
    for i in range(frames):
        t = i / frames
        hop = abs(math.sin(math.pi * t))  # 0 at landing, 1 at the top of the bounce
        squash = max(0.0, 1.0 - hop * 4) * 0.4  # brief dip on landing
        lift = bounce * H * (hop - squash)

        # Warp: output pixel (y, x) samples the source at y + lift * weight  -> upper body moves up.
        sy = np.clip(rows + lift * weight, 0, H - 1)
        y0 = np.floor(sy).astype(np.int32)
        y1 = np.minimum(y0 + 1, H - 1)
        f = (sy - y0)[..., None]
        warped = src[y0, cols] * (1 - f) + src[y1, cols] * f
        frame = Image.fromarray(warped.clip(0, 255).astype(np.uint8))

        # Bobble head: extra lagging bob + tilt around the neck.
        extra = head_bob * H * math.sin(2 * math.pi * t - 0.9)
        angle = head_tilt_degrees * math.sin(2 * math.pi * t + 0.6)
        piv = (pivot[0], pivot[1] - lift)
        head_layer = frame.transform(frame.size, Image.AFFINE, (1, 0, 0, 0, 1, extra), fillcolor="white")
        head_layer = head_layer.rotate(angle, resample=Image.BICUBIC, center=(piv[0], piv[1] - extra),
                                       fillcolor="white")
        mask = head_mask.transform(head_mask.size, Image.AFFINE, (1, 0, 0, 0, 1, lift + extra))
        mask = mask.rotate(angle, resample=Image.BICUBIC, center=(piv[0], piv[1] - extra))
        frame.paste(head_layer, (0, 0), mask)

        draw = ImageDraw.Draw(frame)
        for sx, sy_, r, phase, color in spark_specs:
            _sparkle(draw, sx, sy_, r * max(0.0, math.sin(2 * math.pi * (t + phase))), color)
        out_frames.append(frame)
    return out_frames


def save_gif(frames: List[Image.Image], path: Path, fps: int = 12, max_width: int = 480) -> Path:
    scaled = []
    for fr in frames:
        if fr.width > max_width:
            fr = fr.resize((max_width, round(fr.height * max_width / fr.width)), Image.LANCZOS)
        scaled.append(fr.convert("P", palette=Image.ADAPTIVE, colors=255))
    scaled[0].save(path, save_all=True, append_images=scaled[1:], duration=round(1000 / fps), loop=0,
                   optimize=True, disposal=2)
    return path


def save_mp4(frames: List[Image.Image], path: Path, fps: int = 12, loops: int = 4) -> Optional[Path]:
    try:
        import imageio.v2 as imageio
    except ImportError:
        return None
    with imageio.get_writer(path, fps=fps, codec="libx264", quality=8, macro_block_size=8,
                            pixelformat="yuv420p") as writer:
        for _ in range(loops):
            for fr in frames:
                writer.append_data(np.asarray(fr))
    return path


def animate_still(still_path: Path, out_dir: Path, stem: str, layout: Optional[Layout] = None) -> dict:
    with Image.open(still_path) as im:
        frames = render_frames(im, layout)
    result = {"gif": str(save_gif(frames, out_dir / f"{stem}.gif"))}
    mp4 = save_mp4(frames, out_dir / f"{stem}.mp4")
    if mp4:
        result["mp4"] = str(mp4)
    return result
