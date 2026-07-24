#!/usr/bin/env python3
"""Crop the author and affiliation band below an academic paper title."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import fitz


BODY_ANCHORS = (
    "abstract",
    "摘要",
    "index terms",
    "keywords",
    "key words",
    "introduction",
)


class CropError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextLine:
    text: str
    bbox: fitz.Rect
    max_size: float
    direction: tuple[float, float]


def normalize(text: str) -> str:
    return re.sub(r"[^0-9a-z\u2e80-\u9fff]+", "", text.casefold())


def horizontal_lines(page: fitz.Page) -> list[TextLine]:
    lines: list[TextLine] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(str(span.get("text", "")) for span in spans).strip()
            direction = tuple(line.get("dir", (1.0, 0.0)))
            if not text or len(direction) != 2 or abs(direction[0]) < 0.9 or abs(direction[1]) > 0.2:
                continue
            lines.append(
                TextLine(
                    text=text,
                    bbox=fitz.Rect(line["bbox"]),
                    max_size=max(float(span.get("size", 0.0)) for span in spans),
                    direction=(float(direction[0]), float(direction[1])),
                )
            )
    return sorted(lines, key=lambda item: (item.bbox.y0, item.bbox.x0))


def detect_title_lines(lines: list[TextLine], page: fitz.Page, expected_title: str) -> tuple[list[TextLine], bool]:
    upper = [line for line in lines if page.rect.y0 + 25 <= line.bbox.y0 <= page.rect.y0 + page.rect.height * 0.32]
    if not upper:
        raise CropError("no horizontal text lines found in the upper page region")

    expected = normalize(expected_title)
    matched: list[TextLine] = []
    if expected:
        for line in upper:
            candidate = normalize(line.text)
            if len(candidate) >= 6 and candidate in expected:
                matched.append(line)
        if matched:
            matched.sort(key=lambda item: item.bbox.y0)
            return matched, True

    largest = max(line.max_size for line in upper)
    threshold = max(13.0, largest - 1.5)
    candidates = [line for line in upper if line.max_size >= threshold]
    if not candidates:
        raise CropError("could not identify title lines by font size")
    candidates.sort(key=lambda item: item.bbox.y0)
    cluster = [candidates[0]]
    for line in candidates[1:]:
        gap = line.bbox.y0 - cluster[-1].bbox.y1
        if gap <= max(14.0, largest * 0.9):
            cluster.append(line)
        elif len(cluster) >= 1:
            break
    return cluster, False


def detect_body_start(lines: list[TextLine], title_bottom: float, page: fitz.Page) -> tuple[float, str | None]:
    candidates = [line for line in lines if line.bbox.y0 > title_bottom + 18 and line.bbox.y0 < page.rect.y0 + page.rect.height * 0.58]
    for line in candidates:
        normalized = re.sub(r"\s+", " ", line.text).strip().casefold()
        if any(normalized.startswith(anchor) for anchor in BODY_ANCHORS):
            return line.bbox.y0, line.text[:80]
    raise CropError("could not find Abstract, keywords, or introduction below the title; use --bbox")


def clamp_rect(rect: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
    clipped = rect & page_rect
    if clipped.is_empty or clipped.width < 40 or clipped.height < 20:
        raise CropError(f"detected crop is too small: {tuple(round(value, 2) for value in clipped)}")
    return clipped


def auto_bbox(page: fitz.Page, expected_title: str) -> tuple[fitz.Rect, dict[str, object]]:
    lines = horizontal_lines(page)
    title_lines, title_matched = detect_title_lines(lines, page, expected_title)
    title_bottom = max(line.bbox.y1 for line in title_lines)
    body_start, body_anchor = detect_body_start(lines, title_bottom, page)
    y0 = title_bottom + 7
    y1 = body_start - 8
    band_lines = [line for line in lines if line.bbox.y0 >= y0 - 2 and line.bbox.y1 <= y1 + 2]
    if not band_lines:
        raise CropError("no author or affiliation text found between title and body")
    x0 = max(page.rect.x0 + 24, min(line.bbox.x0 for line in band_lines) - 12)
    x1 = min(page.rect.x1 - 24, max(line.bbox.x1 for line in band_lines) + 12)
    rect = clamp_rect(fitz.Rect(x0, y0, x1, y1), page.rect)
    return rect, {
        "method": "title_to_body_anchor",
        "title_matched": title_matched,
        "title_lines": [line.text for line in title_lines],
        "body_anchor": body_anchor,
        "confidence": "high" if title_matched and body_anchor else "medium",
    }


def crop_author_block(
    pdf_path: Path,
    output_path: Path,
    *,
    page_number: int = 1,
    title: str = "",
    dpi: int = 260,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, object]:
    if dpi < 120 or dpi > 400:
        raise CropError("dpi must be between 120 and 400")
    if not pdf_path.is_file():
        raise CropError(f"PDF does not exist: {pdf_path}")
    document = fitz.open(pdf_path)
    try:
        if page_number < 1 or page_number > document.page_count:
            raise CropError(f"page must be between 1 and {document.page_count}")
        page = document[page_number - 1]
        if bbox is None:
            rect, detection = auto_bbox(page, title)
        else:
            rect = clamp_rect(fitz.Rect(*bbox), page.rect)
            detection = {"method": "manual_bbox", "confidence": "manual"}

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=rect, alpha=False)
        pixmap.save(output_path)
    finally:
        document.close()

    manifest = {
        "tool": "PaperAuthorCrop/0.1",
        "pdf": str(pdf_path.resolve()),
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "page": page_number,
        "dpi": dpi,
        "crop_bbox": [round(value, 2) for value in rect],
        "output": str(output_path.resolve()),
        "width_px": pixmap.width,
        "height_px": pixmap.height,
        "detection": detection,
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox must be x0,y0,x1,y1 in PDF points") from exc
    if len(values) != 4:
        raise argparse.ArgumentTypeError("bbox must contain exactly four comma-separated values")
    return values  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--page", type=int, default=1, help="1-based PDF page number")
    parser.add_argument("--title", default="", help="expected paper title for stronger title matching")
    parser.add_argument("--dpi", type=int, default=260)
    parser.add_argument("--bbox", type=parse_bbox, help="manual x0,y0,x1,y1 override in PDF points")
    args = parser.parse_args()
    try:
        manifest = crop_author_block(
            args.pdf.resolve(),
            args.output.resolve(),
            page_number=args.page,
            title=args.title,
            dpi=args.dpi,
            bbox=args.bbox,
        )
    except (CropError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Author block: {manifest['output']}")
    print(f"Crop bbox: {manifest['crop_bbox']} | confidence: {manifest['detection']['confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
