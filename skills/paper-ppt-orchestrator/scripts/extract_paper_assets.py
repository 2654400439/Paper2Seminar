#!/usr/bin/env python3
"""Extract figure and table regions from academic-paper PDFs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import fitz
from PIL import Image, ImageDraw, ImageFont, ImageOps


MODEL_FILENAME = "doclayout_yolo_ft.pt"
MODEL_SHA256 = "9A2EE0220FE3D9AD31B47E1D9F1282F46959A54E4618FCE9CFFCC9715B8286E2"
MODEL_REVISION = "221d2454db9d18253ddf43a24c79f8fa3e8e83da"
MODEL_URL = (
    "https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0/resolve/"
    f"{MODEL_REVISION}/models/Layout/YOLO/{MODEL_FILENAME}?download=true"
)
ALGORITHM_PATTERN = re.compile(r"(?im)^\s*algorithm\s+\d+\b")
MANAGED_OUTPUTS = (
    "crops",
    "annotated_pages",
    "contact_sheet.jpg",
    "manifest.csv",
    "manifest.json",
    "summary.json",
)


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Detection:
    kind: str
    confidence: float
    bbox_pixels: tuple[float, float, float, float]


@dataclass(frozen=True)
class ExtractionConfig:
    confidence: float = 0.18
    image_size: int = 1024
    detection_dpi: int = 144
    crop_dpi: int = 300
    padding_points: float = 5.0
    dedupe_iou: float = 0.75
    device: str = "cpu"


class Predictor(Protocol):
    def predict(self, image: Image.Image) -> list[Detection]: ...


def default_cache_dir() -> Path:
    override = os.environ.get("PAPER_PPT_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Paper2Seminar"
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    return Path(xdg_cache).expanduser() / "paper2seminar" if xdg_cache else Path.home() / ".cache" / "paper2seminar"


def default_model_path(cache_dir: Path | None = None) -> Path:
    configured = os.environ.get("PAPER_PPT_DOCLAYOUT_MODEL")
    if configured:
        return Path(configured).expanduser()
    return (cache_dir or default_cache_dir()) / "models" / MODEL_FILENAME


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_model(path: Path, *, allow_unverified: bool = False) -> str:
    if not path.is_file():
        raise ExtractionError(
            f"DocLayout model does not exist: {path}. "
            "Run `paper_ppt.py download-layout-model` or pass --model."
        )
    digest = sha256_file(path)
    if digest != MODEL_SHA256 and not allow_unverified:
        raise ExtractionError(
            f"DocLayout model SHA-256 mismatch for {path}: {digest}. "
            f"Expected {MODEL_SHA256}; use only a trusted model or pass --allow-unverified-model explicitly."
        )
    return digest


def download_model(output: Path, *, force: bool = False) -> dict[str, object]:
    output = output.expanduser().resolve()
    if output.exists() and not force:
        digest = verify_model(output)
        return {"path": str(output), "sha256": digest, "downloaded": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{MODEL_FILENAME}.", suffix=".download", dir=output.parent, delete=False
        ) as target:
            temporary = Path(target.name)
            request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "Paper2Seminar/0.2"})
            with urllib.request.urlopen(request, timeout=120) as source:
                shutil.copyfileobj(source, target)
        digest = verify_model(temporary)
        os.replace(temporary, output)
        temporary = None
        return {"path": str(output), "sha256": digest, "downloaded": True}
    except (OSError, urllib.error.URLError) as exc:
        raise ExtractionError(f"could not download DocLayout model: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _tensor_values(value: Any) -> list[Any]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return list(value)


class DocLayoutPredictor:
    def __init__(
        self,
        model_path: Path,
        config: ExtractionConfig,
        *,
        cache_dir: Path | None = None,
        allow_unverified_model: bool = False,
    ) -> None:
        self.model_sha256 = verify_model(model_path, allow_unverified=allow_unverified_model)
        self.config = config
        yolo_config = (cache_dir or default_cache_dir()) / "yolo-config"
        yolo_config.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(yolo_config.resolve()))
        try:
            from doclayout_yolo import YOLOv10
        except ImportError as exc:
            raise ExtractionError(
                "DocLayout backend is not installed. Install requirements-doclayout.txt."
            ) from exc
        try:
            self.model = YOLOv10(str(model_path.resolve()))
        except Exception as exc:
            raise ExtractionError(f"could not load DocLayout model: {exc}") from exc

    def predict(self, image: Image.Image) -> list[Detection]:
        try:
            results = self.model.predict(
                source=image,
                imgsz=self.config.image_size,
                conf=self.config.confidence,
                device=self.config.device,
                verbose=False,
            )
        except Exception as exc:
            raise ExtractionError(f"DocLayout inference failed: {exc}") from exc
        if not results:
            return []
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        names = getattr(result, "names", None) or getattr(self.model, "names", {})
        xyxy = _tensor_values(boxes.xyxy)
        classes = _tensor_values(boxes.cls)
        confidences = _tensor_values(boxes.conf)
        detections: list[Detection] = []
        for coordinates, class_id, confidence in zip(xyxy, classes, confidences):
            kind = str(names.get(int(class_id), "") if isinstance(names, dict) else names[int(class_id)]).casefold()
            if kind not in {"figure", "table"}:
                continue
            detections.append(
                Detection(
                    kind=kind,
                    confidence=float(confidence),
                    bbox_pixels=tuple(float(value) for value in coordinates),  # type: ignore[arg-type]
                )
            )
        return detections


def intersection_over_union(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def deduplicate(detections: Sequence[Detection], threshold: float) -> list[Detection]:
    retained: list[Detection] = []
    for candidate in sorted(detections, key=lambda item: item.confidence, reverse=True):
        if any(
            candidate.kind == existing.kind
            and intersection_over_union(candidate.bbox_pixels, existing.bbox_pixels) >= threshold
            for existing in retained
        ):
            continue
        retained.append(candidate)
    return sorted(retained, key=lambda item: (item.bbox_pixels[1], item.bbox_pixels[0], item.kind))


def detection_to_pdf_rect(
    detection: Detection, image_size: tuple[int, int], page_rect: fitz.Rect
) -> fitz.Rect:
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ExtractionError("detection image has invalid dimensions")
    x_scale = page_rect.width / width
    y_scale = page_rect.height / height
    x0, y0, x1, y1 = detection.bbox_pixels
    return fitz.Rect(
        page_rect.x0 + x0 * x_scale,
        page_rect.y0 + y0 * y_scale,
        page_rect.x0 + x1 * x_scale,
        page_rect.y0 + y1 * y_scale,
    ) & page_rect


def padded_rect(rect: fitz.Rect, page_rect: fitz.Rect, padding: float) -> fitz.Rect:
    return fitz.Rect(rect.x0 - padding, rect.y0 - padding, rect.x1 + padding, rect.y1 + padding) & page_rect


def pixmap_to_image(pixmap: fitz.Pixmap) -> Image.Image:
    mode = "RGBA" if pixmap.alpha else "RGB"
    return Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples).convert("RGB")


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def save_annotated_page(
    image: Image.Image,
    accepted: Sequence[Detection],
    rejected: Sequence[tuple[Detection, str]],
    output: Path,
) -> None:
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    font = _load_font(18)
    for detection, reason in [(item, "") for item in accepted] + list(rejected):
        color = "#D62828" if reason else ("#176B3A" if detection.kind == "figure" else "#1559A6")
        box = tuple(round(value) for value in detection.bbox_pixels)
        draw.rectangle(box, outline=color, width=4)
        label = f"{detection.kind} {detection.confidence:.2f}" + (f" REJECTED: {reason}" if reason else "")
        text_box = draw.textbbox((box[0], box[1]), label, font=font)
        label_y = max(0, box[1] - (text_box[3] - text_box[1]) - 6)
        draw.rectangle((box[0], label_y, box[0] + text_box[2] - text_box[0] + 8, box[1]), fill=color)
        draw.text((box[0] + 4, label_y + 2), label, fill="white", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=90)


def build_asset_contact_sheet(entries: Sequence[dict[str, object]], root: Path, output: Path) -> None:
    columns = 4 if len(entries) <= 16 else 5
    cell_width, image_height, label_height, gap, margin = 500, 320, 56, 16, 20
    rows = max(1, math.ceil(len(entries) / columns))
    width = margin * 2 + columns * cell_width + (columns - 1) * gap
    height = margin * 2 + rows * (image_height + label_height) + (rows - 1) * gap
    canvas = Image.new("RGB", (width, height), "#20252C")
    draw = ImageDraw.Draw(canvas)
    font = _load_font(20)
    if not entries:
        draw.text((margin, margin), "No figure or table candidates were extracted.", fill="white", font=font)
    for index, entry in enumerate(entries):
        row, column = divmod(index, columns)
        x = margin + column * (cell_width + gap)
        y = margin + row * (image_height + label_height + gap)
        with Image.open(root / str(entry["file"])) as source:
            fitted = ImageOps.contain(source.convert("RGB"), (cell_width, image_height), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", (cell_width, image_height), "white")
        frame.paste(fitted, ((cell_width - fitted.width) // 2, (image_height - fitted.height) // 2))
        canvas.paste(frame, (x, y))
        draw.rectangle((x, y + image_height, x + cell_width, y + image_height + label_height), fill="#15191E")
        label = f"{entry['id']} | page {entry['page']} | conf {float(entry['confidence']):.3f}"
        draw.text((x + 10, y + image_height + 8), label, fill="white", font=font)
        draw.rectangle((x, y, x + cell_width - 1, y + image_height - 1), outline="#66717E", width=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=88)


def prepare_output(output: Path, clean: bool) -> None:
    if not output.exists():
        output.mkdir(parents=True)
        return
    present = [output / name for name in MANAGED_OUTPUTS if (output / name).exists()]
    if present and not clean:
        raise ExtractionError(f"output already contains extraction artifacts: {output}; pass --clean to replace them")
    for path in present:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def extract_pdf(
    pdf_path: Path,
    output: Path,
    predictor: Predictor,
    config: ExtractionConfig,
    *,
    clean: bool = False,
    model_path: Path | None = None,
    model_sha256: str | None = None,
) -> dict[str, object]:
    pdf_path = pdf_path.resolve()
    output = output.resolve()
    if not pdf_path.is_file():
        raise ExtractionError(f"PDF does not exist: {pdf_path}")
    if not 0 < config.confidence <= 1:
        raise ExtractionError("confidence must be greater than 0 and at most 1")
    if not 0 < config.dedupe_iou <= 1:
        raise ExtractionError("dedupe IoU must be greater than 0 and at most 1")
    if config.detection_dpi < 72 or config.crop_dpi < 72:
        raise ExtractionError("detection and crop DPI must be at least 72")
    prepare_output(output, clean)
    crops_dir = output / "crops"
    annotated_dir = output / "annotated_pages"
    crops_dir.mkdir(parents=True, exist_ok=True)
    annotated_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, object]] = []
    rejected_records: list[dict[str, object]] = []
    deduplicated_count = 0
    counters = {"figure": 0, "table": 0}
    document = fitz.open(pdf_path)
    try:
        for page_index, page in enumerate(document):
            detection_pixmap = page.get_pixmap(dpi=config.detection_dpi, alpha=False)
            detection_image = pixmap_to_image(detection_pixmap)
            raw = predictor.predict(detection_image)
            candidates = deduplicate(raw, config.dedupe_iou)
            deduplicated_count += len(raw) - len(candidates)
            accepted: list[Detection] = []
            rejected: list[tuple[Detection, str]] = []
            for detection in candidates:
                unpadded = detection_to_pdf_rect(detection, detection_image.size, page.rect)
                if unpadded.is_empty or unpadded.width < 1 or unpadded.height < 1:
                    rejected.append((detection, "invalid_bbox"))
                    continue
                if detection.kind == "table" and ALGORITHM_PATTERN.search(page.get_textbox(unpadded).strip()):
                    rejected.append((detection, "algorithm_block"))
                    continue
                accepted.append(detection)
                counters[detection.kind] += 1
                identifier = f"{detection.kind}_{counters[detection.kind]:02d}"
                crop_rect = padded_rect(unpadded, page.rect, config.padding_points)
                crop_pixmap = page.get_pixmap(dpi=config.crop_dpi, clip=crop_rect, alpha=False)
                filename = f"{identifier}_page_{page_index + 1:02d}.png"
                crop_path = crops_dir / filename
                crop_pixmap.save(crop_path)
                entries.append(
                    {
                        "id": identifier,
                        "kind": detection.kind,
                        "page": page_index + 1,
                        "confidence": round(detection.confidence, 6),
                        "bbox_pdf_points": [round(value, 3) for value in crop_rect],
                        "bbox_detection_pixels": [round(value, 3) for value in detection.bbox_pixels],
                        "width": crop_pixmap.width,
                        "height": crop_pixmap.height,
                        "file": f"crops/{filename}",
                        "review_status": "unreviewed",
                    }
                )
            if accepted or rejected:
                save_annotated_page(
                    detection_image,
                    accepted,
                    rejected,
                    annotated_dir / f"page_{page_index + 1:02d}.jpg",
                )
            for detection, reason in rejected:
                rejected_records.append(
                    {
                        "page": page_index + 1,
                        "kind": detection.kind,
                        "confidence": round(detection.confidence, 6),
                        "bbox_detection_pixels": [round(value, 3) for value in detection.bbox_pixels],
                        "reason": reason,
                    }
                )
    finally:
        page_count = document.page_count
        document.close()

    (output / "manifest.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fieldnames = [
        "id", "kind", "page", "confidence", "bbox_pdf_points", "bbox_detection_pixels",
        "width", "height", "file", "review_status",
    ]
    with (output / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow({**entry, "bbox_pdf_points": json.dumps(entry["bbox_pdf_points"]), "bbox_detection_pixels": json.dumps(entry["bbox_detection_pixels"])})
    build_asset_contact_sheet(entries, output, output / "contact_sheet.jpg")
    summary: dict[str, object] = {
        "tool": "Paper2Seminar DocLayout extractor/0.2",
        "backend": "doclayout",
        "pdf": str(pdf_path),
        "pdf_sha256": sha256_file(pdf_path),
        "pages": page_count,
        "figures": counters["figure"],
        "tables": counters["table"],
        "total": len(entries),
        "deduplicated_detections": deduplicated_count,
        "output": str(output),
        "model": str(model_path.resolve()) if model_path else None,
        "model_sha256": model_sha256,
        "parameters": {
            "confidence": config.confidence,
            "image_size": config.image_size,
            "detection_dpi": config.detection_dpi,
            "crop_dpi": config.crop_dpi,
            "padding_points": config.padding_points,
            "dedupe_iou": config.dedupe_iou,
            "device": config.device,
        },
        "rejected_detections": rejected_records,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def resolve_captioncrop_command(value: Path | None) -> list[str]:
    if value:
        resolved = value.expanduser().resolve()
        if not resolved.is_file():
            raise ExtractionError(f"CaptionCrop command does not exist: {resolved}")
        return [sys.executable, str(resolved)] if resolved.suffix.casefold() == ".py" else [str(resolved)]
    for name in ("caption-crop", "captioncrop", "caption_crop.py"):
        found = shutil.which(name)
        if found:
            return [sys.executable, found] if Path(found).suffix.casefold() == ".py" else [found]
    raise ExtractionError("CaptionCrop was not found; pass --captioncrop-command with its script or executable")


def run_captioncrop(
    pdf: Path,
    output: Path,
    *,
    command: Path | None = None,
    dpi: int = 240,
    clean: bool = False,
) -> None:
    invocation = [*resolve_captioncrop_command(command), str(pdf.resolve()), "-o", str(output.resolve()), "--dpi", str(dpi), "--contact-sheet"]
    if clean:
        invocation.append("--clean")
    completed = subprocess.run(invocation, check=False)
    if completed.returncode != 0:
        raise ExtractionError(f"CaptionCrop exited with status {completed.returncode}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("doclayout", "captioncrop"), default="doclayout")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--allow-unverified-model", action="store_true")
    parser.add_argument("--confidence", type=float, default=0.18)
    parser.add_argument("--image-size", type=int, default=1024)
    parser.add_argument("--detection-dpi", type=int, default=144)
    parser.add_argument("--crop-dpi", type=int, default=300)
    parser.add_argument("--padding-points", type=float, default=5.0)
    parser.add_argument("--dedupe-iou", type=float, default=0.75)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--captioncrop-command", type=Path)
    parser.add_argument("--captioncrop-dpi", type=int, default=240)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.backend == "captioncrop":
            run_captioncrop(
                args.pdf, args.output, command=args.captioncrop_command, dpi=args.captioncrop_dpi, clean=args.clean
            )
            return 0
        cache_dir = args.cache_dir.expanduser().resolve() if args.cache_dir else default_cache_dir()
        model_path = (args.model or default_model_path(cache_dir)).expanduser().resolve()
        config = ExtractionConfig(
            confidence=args.confidence,
            image_size=args.image_size,
            detection_dpi=args.detection_dpi,
            crop_dpi=args.crop_dpi,
            padding_points=args.padding_points,
            dedupe_iou=args.dedupe_iou,
            device=args.device,
        )
        predictor = DocLayoutPredictor(
            model_path,
            config,
            cache_dir=cache_dir,
            allow_unverified_model=args.allow_unverified_model,
        )
        summary = extract_pdf(
            args.pdf,
            args.output,
            predictor,
            config,
            clean=args.clean,
            model_path=model_path,
            model_sha256=predictor.model_sha256,
        )
    except (ExtractionError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"Extracted {summary['figures']} figures and {summary['tables']} tables "
        f"from {summary['pages']} pages into {summary['output']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
