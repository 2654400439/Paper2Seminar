#!/usr/bin/env python3
"""Crop a raster asset by normalized coordinates and record the operation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        bbox = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox must be x0,y0,x1,y1") from exc
    if len(bbox) != 4 or not (0 <= bbox[0] < bbox[2] <= 1 and 0 <= bbox[1] < bbox[3] <= 1):
        raise argparse.ArgumentTypeError("normalized bbox values must satisfy 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1")
    return bbox


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--bbox", type=parse_bbox, required=True, help="normalized x0,y0,x1,y1")
    parser.add_argument("--source-label", default="")
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    try:
        with Image.open(source) as image:
            width, height = image.size
            x0, y0, x1, y1 = args.bbox
            pixel_bbox = (
                round(x0 * width),
                round(y0 * height),
                round(x1 * width),
                round(y1 * height),
            )
            cropped = image.crop(pixel_bbox)
            output.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(output, format="PNG", optimize=True)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    manifest = {
        "tool": "crop_image_region/0.1",
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_label": args.source_label,
        "normalized_bbox": list(args.bbox),
        "pixel_bbox": list(pixel_bbox),
        "output": str(output),
        "output_size": list(cropped.size),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Cropped image: {output}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
