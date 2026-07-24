#!/usr/bin/env python3
"""Render a PPTX with PowerPoint and build one zoomable overview image."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from make_contact_sheet import build_contact_sheet, collect_images


def render_with_powerpoint(pptx: Path, slides_dir: Path, dpi: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("the PowerPoint renderer is currently Windows-only")
    script = Path(__file__).with_name("export_pptx_pages.ps1")
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-InputPptx",
        str(pptx),
        "-OutputDir",
        str(slides_dir),
        "-Dpi",
        str(dpi),
    ]
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"PowerPoint rendering failed: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pptx", type=Path)
    source.add_argument("--slides-dir", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--columns", type=int, default=0)
    parser.add_argument("--thumb-width", type=int, default=720)
    args = parser.parse_args()

    try:
        if args.pptx:
            pptx = args.pptx.resolve()
            slides_dir = args.work_dir or args.output.parent / "rendered-slides"
            render_with_powerpoint(pptx, slides_dir.resolve(), args.dpi)
        else:
            slides_dir = args.slides_dir.resolve()
        images = collect_images(slides_dir)
        result = build_contact_sheet(images, args.output, args.columns, args.thumb_width)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Overview: {args.output} | {result['slides']} slides | "
        f"{result['columns']}x{result['rows']} | {result['width']}x{result['height']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
