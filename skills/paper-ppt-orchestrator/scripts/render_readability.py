#!/usr/bin/env python3
"""Create an optional overview or four-slide readability review package."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from make_contact_sheet import build_contact_sheet, collect_images
from render_deck_overview import render_with_powerpoint


MODES = ("off", "overview", "full")


def create_package(
    mode: str,
    output_dir: Path,
    *,
    pptx: Path | None = None,
    slides_dir: Path | None = None,
    dpi: int = 120,
    group_size: int = 4,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unsupported readability mode: {mode}")
    if not 1 <= group_size <= 4:
        raise ValueError("group_size must be between 1 and 4")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_files: list[str] = []
    rendered_count = 0

    if mode != "off":
        if bool(pptx) == bool(slides_dir):
            raise ValueError("choose exactly one of pptx or slides_dir")
        if pptx:
            pptx = pptx.resolve()
            rendered_dir = output_dir / "rendered-slides"
            render_with_powerpoint(pptx, rendered_dir, dpi)
        else:
            rendered_dir = slides_dir.resolve()
        images = collect_images(rendered_dir)
        if not images:
            raise ValueError("no rendered slide images found")
        rendered_count = len(images)
        if mode == "overview":
            overview = output_dir / "overview.png"
            build_contact_sheet(images, overview)
            evidence_files.append(str(overview))
        else:
            groups_dir = output_dir / "groups"
            for offset in range(0, len(images), group_size):
                group = images[offset : offset + group_size]
                group_path = groups_dir / f"group-{offset // group_size + 1:02d}.png"
                build_contact_sheet(
                    group,
                    group_path,
                    columns=2 if len(group) > 1 else 1,
                    thumb_width=1000,
                    start_index=offset + 1,
                )
                evidence_files.append(str(group_path))

    manifest = {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "pptx": str(pptx) if pptx else None,
        "pptx_sha256": hashlib.sha256(pptx.read_bytes()).hexdigest() if pptx else None,
        "rendered_slide_count": rendered_count,
        "group_size": group_size if mode == "full" else None,
        "evidence_files": evidence_files,
        "expected_review_calls": math.ceil(rendered_count / group_size) if mode == "full" else (1 if mode == "overview" else 0),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, default="off")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--pptx", type=Path)
    source.add_argument("--slides-dir", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--group-size", type=int, default=4)
    args = parser.parse_args()
    try:
        result = create_package(
            args.mode,
            args.output_dir,
            pptx=args.pptx,
            slides_dir=args.slides_dir,
            dpi=args.dpi,
            group_size=args.group_size,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"Readability package: {result['mode']} | {result['rendered_slide_count']} slides | "
        f"{result['expected_review_calls']} review image(s) | {result['manifest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
