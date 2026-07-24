#!/usr/bin/env python3
"""Combine rendered slide images into one high-resolution overview PNG."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def collect_images(input_dir: Path) -> list[Path]:
    images = [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
    return sorted(images, key=natural_key)


def auto_columns(count: int) -> int:
    if count <= 12:
        return 4
    if count <= 24:
        return 5
    return 6


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in ("arial.ttf", "msyh.ttc", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_contact_sheet(
    image_paths: list[Path],
    output_path: Path,
    columns: int = 0,
    thumb_width: int = 720,
    start_index: int = 1,
) -> dict[str, int]:
    if not image_paths:
        raise ValueError("no rendered slide images found")
    columns = columns or auto_columns(len(image_paths))
    if not 1 <= columns <= 10:
        raise ValueError("columns must be between 1 and 10")
    if not 320 <= thumb_width <= 1200:
        raise ValueError("thumb_width must be between 320 and 1200")

    thumb_height = round(thumb_width * 9 / 16)
    label_height = 42
    gap = 18
    margin = 24
    rows = math.ceil(len(image_paths) / columns)
    cell_height = thumb_height + label_height
    width = margin * 2 + columns * thumb_width + (columns - 1) * gap
    height = margin * 2 + rows * cell_height + (rows - 1) * gap
    canvas = Image.new("RGB", (width, height), "#20252C")
    draw = ImageDraw.Draw(canvas)
    label_font = load_font(24)

    for index, path in enumerate(image_paths):
        row, column = divmod(index, columns)
        x = margin + column * (thumb_width + gap)
        y = margin + row * (cell_height + gap)
        with Image.open(path) as source:
            slide = source.convert("RGB")
            fitted = ImageOps.contain(slide, (thumb_width, thumb_height), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", (thumb_width, thumb_height), "white")
        paste_x = (thumb_width - fitted.width) // 2
        paste_y = (thumb_height - fitted.height) // 2
        frame.paste(fitted, (paste_x, paste_y))
        canvas.paste(frame, (x, y))
        draw.rectangle((x, y + thumb_height, x + thumb_width, y + cell_height), fill="#15191E")
        draw.text(
            (x + 12, y + thumb_height + 6),
            f"Slide {start_index + index:02d}",
            font=label_font,
            fill="white",
        )
        draw.rectangle((x, y, x + thumb_width - 1, y + thumb_height - 1), outline="#66717E", width=2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=True)
    return {"slides": len(image_paths), "columns": columns, "rows": rows, "width": width, "height": height}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=0, help="0 selects 4-6 columns automatically")
    parser.add_argument("--thumb-width", type=int, default=720)
    args = parser.parse_args()
    try:
        paths = collect_images(args.input_dir)
        result = build_contact_sheet(paths, args.output, args.columns, args.thumb_width)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        f"Contact sheet: {args.output} | {result['slides']} slides | "
        f"{result['columns']}x{result['rows']} | {result['width']}x{result['height']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
