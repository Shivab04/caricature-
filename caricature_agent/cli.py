"""Command line entry point.

  python -m caricature_agent one  photos/aanya.jpg --name "Aanya"
  python -m caricature_agent batch roster.csv            # name,photo,activity,outfit
  python -m caricature_agent batch photos/               # every image, name from file name
  python -m caricature_agent animate caricature.png      # bobble-head GIF/MP4 only, no API keys
"""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from .animate import animate_still

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp"}


def load_jobs(source: Path):
    from .pipeline import StudentJob

    if source.is_dir():
        return [StudentJob(name=p.stem.replace("_", " ").title(), photo=p)
                for p in sorted(source.iterdir()) if p.suffix.lower() in PHOTO_EXTS]
    jobs = []
    with source.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("photo"):
                continue
            photo = Path(row["photo"])
            if not photo.is_absolute():
                photo = source.parent / photo
            jobs.append(StudentJob(name=row.get("name") or photo.stem, photo=photo,
                                   activity=row.get("activity") or None, outfit=row.get("outfit") or None))
    return jobs


def run_jobs(jobs: List, out: Path, animation: str, workers: int) -> int:
    from .pipeline import CaricatureAgent

    missing = [j for j in jobs if not j.photo.exists()]
    for j in missing:
        print(f"Photo not found for {j.name}: {j.photo}", file=sys.stderr)
    jobs = [j for j in jobs if j.photo.exists()]
    if not jobs:
        print("No students to process.", file=sys.stderr)
        return 1

    agent = CaricatureAgent()
    out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda j: agent.run(j, out, animation), jobs))

    with (out / "summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "caricature", "gif", "mp4", "ai_video", "likeness", "style", "attempts", "error"])
        for r in results:
            a = r.animations
            w.writerow([r.name, r.caricature or "", a.get("gif", ""), a.get("mp4", ""), a.get("video", ""),
                        r.likeness_score or "", r.style_score or "", r.attempts, r.error or ""])
    ok = sum(1 for r in results if not r.error)
    print(f"\n{ok}/{len(results)} caricatures created. Summary: {out / 'summary.csv'}")
    return 0 if ok == len(results) else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="caricature_agent", description="Animated student caricatures from photos")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", type=Path, default=Path("output"), help="output folder (default: output/)")
        p.add_argument("--animation", choices=["both", "video", "procedural", "none"], default="both",
                       help="video = AI video (Sora), procedural = free local bobble-head GIF/MP4")

    one = sub.add_parser("one", help="one student")
    one.add_argument("photo", type=Path)
    one.add_argument("--name", required=True)
    one.add_argument("--activity", help="e.g. 'kicking a football', 'reading a big storybook'")
    one.add_argument("--outfit", help="e.g. 'red school uniform with a tie'")
    common(one)

    batch = sub.add_parser("batch", help="a whole class from a CSV roster or a folder of photos")
    batch.add_argument("source", type=Path)
    batch.add_argument("--workers", type=int, default=2, help="students processed in parallel")
    common(batch)

    anim = sub.add_parser("animate", help="animate an existing caricature locally (no API keys needed)")
    anim.add_argument("image", type=Path)
    anim.add_argument("--out", type=Path, default=Path("output"))

    args = parser.parse_args(argv)
    if args.command == "animate":
        args.out.mkdir(parents=True, exist_ok=True)
        print(animate_still(args.image, args.out, args.image.stem + "_bounce"))
        return 0
    if args.command == "one":
        from .pipeline import StudentJob

        return run_jobs([StudentJob(args.name, args.photo, args.activity, args.outfit)], args.out, args.animation, 1)
    return run_jobs(load_jobs(args.source), args.out, args.animation, args.workers)


if __name__ == "__main__":
    sys.exit(main())
