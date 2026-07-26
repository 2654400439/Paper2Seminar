#!/usr/bin/env python3
"""Validate a paper-PPT deck plan using only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


SECTION_ORDER = ["background", "method", "results", "reflection"]
SLIDE_TYPES = {
    "cover",
    "paper_info",
    "one_page",
    "contents",
    "section_divider",
    "content",
    "closing",
}
VISUAL_MODES = {"paper_asset", "tikz", "data_redraw", "imagegen", "external_image", "none"}
LAYOUTS = {"content_stacked"}
BODY_LINE_UNITS = 96
CONTRIBUTION_LINE_UNITS = 88
PLACEHOLDER_RE = re.compile(
    r"\{\{[^{}]+\}\}|<TODO>|\b(?:TODO|lorem|ipsum|xxxx)\b", re.IGNORECASE
)


class Reporter:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"[ERROR] {path}: {message}")

    def warn(self, path: str, message: str) -> None:
        self.warnings.append(f"[WARN] {path}: {message}")


def get_str(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    return value.strip() if isinstance(value, str) else ""


def path_from(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_http_url(value: str) -> bool:
    return bool(re.match(r"^https?://[^\s]+$", value))


def text_units(text: str) -> int:
    """Approximate visual width: CJK counts twice, other non-space chars once."""
    return sum(2 if "\u2e80" <= char <= "\u9fff" else 1 for char in text if not char.isspace())


def speech_units(text: str) -> int:
    """Approximate spoken length for mixed Chinese and English scripts."""
    cjk = sum(1 for char in text if "\u2e80" <= char <= "\u9fff")
    without_cjk = re.sub(r"[\u2e80-\u9fff]", " ", text)
    words = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", without_cjk))
    return cjk + round(words * 1.6)


def estimated_lines(text: str, units_per_line: int) -> int:
    return max(1, math.ceil(text_units(text) / units_per_line))


def iter_strings(value: Any, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_strings(item, f"{path}.{key}")


def validate(plan: Any, stage: str, plan_path: Path, reporter: Reporter) -> None:
    if not isinstance(plan, dict):
        reporter.error("$", "top-level JSON value must be an object")
        return

    for key in ("schema_version", "project", "paper", "sections", "slides"):
        if key not in plan:
            reporter.error("$", f"missing required key '{key}'")

    if plan.get("schema_version") != "0.1":
        reporter.error("$.schema_version", "must equal '0.1'")

    for path, value in iter_strings(plan):
        match = PLACEHOLDER_RE.search(value)
        if match:
            reporter.error(path, f"contains unresolved placeholder '{match.group(0)}'")

    base = plan_path.parent
    project = plan.get("project")
    if not isinstance(project, dict):
        reporter.error("$.project", "must be an object")
        project = {}

    supported_layouts = project.get("supported_layouts")
    if not isinstance(supported_layouts, list) or not supported_layouts:
        reporter.error("$.project.supported_layouts", "must be a non-empty array")
        supported_layout_set: set[str] = set()
    else:
        supported_layout_set = set()
        for index, layout in enumerate(supported_layouts):
            if layout not in LAYOUTS:
                reporter.error(
                    f"$.project.supported_layouts[{index}]", f"unsupported layout '{layout}'"
                )
            else:
                supported_layout_set.add(layout)

    readability_mode = project.get("final_readability_mode", "off")
    if readability_mode not in {"off", "overview", "full"}:
        reporter.error(
            "$.project.final_readability_mode", "must be off, overview, or full"
        )
    if stage in {"notes", "final"} and readability_mode in {"overview", "full"}:
        manifest_value = get_str(project, "readability_manifest") or "qa/readability/manifest.json"
        manifest_path = path_from(base, manifest_value)
        if not manifest_path.is_file():
            reporter.error(
                "$.project.readability_manifest",
                f"readability mode '{readability_mode}' requires: {manifest_value}",
            )
        else:
            try:
                readability = json.loads(manifest_path.read_text(encoding="utf-8"))
                if readability.get("mode") != readability_mode:
                    reporter.error(
                        "$.project.readability_manifest",
                        f"manifest mode is '{readability.get('mode')}', expected '{readability_mode}'",
                    )
                rendered_count = readability.get("rendered_slide_count")
                declared_count = project.get("target_slide_count")
                if isinstance(declared_count, int) and rendered_count != declared_count:
                    reporter.error(
                        "$.project.readability_manifest",
                        f"manifest covers {rendered_count} slides, expected {declared_count}",
                    )
                evidence_files = readability.get("evidence_files")
                if not isinstance(evidence_files, list) or not evidence_files:
                    reporter.error(
                        "$.project.readability_manifest", "manifest has no evidence files"
                    )
                else:
                    for index, value in enumerate(evidence_files):
                        if not isinstance(value, str):
                            reporter.error(
                                f"$.project.readability_manifest.evidence_files[{index}]",
                                "must be a path",
                            )
                            continue
                        evidence_path = path_from(manifest_path.parent, value)
                        if not evidence_path.is_file():
                            reporter.error(
                                f"$.project.readability_manifest.evidence_files[{index}]",
                                f"file does not exist: {value}",
                            )
                if readability_mode == "full" and readability.get("group_size") not in {1, 2, 3, 4}:
                    reporter.error(
                        "$.project.readability_manifest",
                        "full mode requires group_size between 1 and 4",
                    )
            except (OSError, json.JSONDecodeError, AttributeError) as exc:
                reporter.error(
                    "$.project.readability_manifest", f"cannot inspect manifest: {exc}"
                )

    speaker_config = project.get("speaker_notes", {"enabled": False})
    if not isinstance(speaker_config, dict):
        reporter.error("$.project.speaker_notes", "must be an object")
        speaker_config = {"enabled": False}
    notes_enabled = speaker_config.get("enabled", False)
    if not isinstance(notes_enabled, bool):
        reporter.error("$.project.speaker_notes.enabled", "must be a boolean")
        notes_enabled = False
    if notes_enabled:
        if speaker_config.get("generation_stage") != "post_qa":
            reporter.error(
                "$.project.speaker_notes.generation_stage", "must be post_qa"
            )
        if speaker_config.get("delivery_style") != "verbatim":
            reporter.error(
                "$.project.speaker_notes.delivery_style", "must be verbatim"
            )
        target_notes_minutes = speaker_config.get("target_minutes")
        if not isinstance(target_notes_minutes, int) or not 5 <= target_notes_minutes <= 120:
            reporter.error(
                "$.project.speaker_notes.target_minutes", "must be an integer from 5 to 120"
            )
        pace = speaker_config.get("pace_units_per_minute")
        if not isinstance(pace, int) or not 80 <= pace <= 400:
            reporter.error(
                "$.project.speaker_notes.pace_units_per_minute",
                "must be an integer from 80 to 400",
            )

    if stage in {"assembly", "notes", "final"}:
        for key in ("paper_pdf", "template_pptx", "one_page_image", "author_visual"):
            value = get_str(project, key)
            if not value:
                reporter.error(f"$.project.{key}", "must be a non-empty path")
            elif not path_from(base, value).is_file():
                reporter.error(f"$.project.{key}", f"file does not exist: {value}")

    sections = plan.get("sections")
    section_ids: list[str] = []
    if not isinstance(sections, list):
        reporter.error("$.sections", "must be an array")
    else:
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                reporter.error(f"$.sections[{index}]", "must be an object")
                continue
            section_id = get_str(section, "id")
            section_ids.append(section_id)
            if not get_str(section, "title"):
                reporter.error(f"$.sections[{index}].title", "must be non-empty")
        if section_ids != SECTION_ORDER:
            reporter.error(
                "$.sections", f"section IDs must appear exactly in this order: {SECTION_ORDER}"
            )

    paper = plan.get("paper")
    if not isinstance(paper, dict):
        reporter.error("$.paper", "must be an object")
    else:
        contributions = paper.get("contributions")
        if not isinstance(contributions, list) or not 1 <= len(contributions) <= 5:
            reporter.error("$.paper.contributions", "must contain 1-5 contribution statements")
        else:
            for index, contribution in enumerate(contributions):
                path = f"$.paper.contributions[{index}]"
                if not isinstance(contribution, dict):
                    reporter.error(path, "must be an object with rich-text runs")
                    continue
                runs = contribution.get("runs")
                if not isinstance(runs, list) or not runs:
                    reporter.error(f"{path}.runs", "must be a non-empty array")
                    continue
                contribution_text = ""
                bold_count = 0
                for run_index, run in enumerate(runs):
                    run_path = f"{path}.runs[{run_index}]"
                    if not isinstance(run, dict) or not get_str(run, "text"):
                        reporter.error(run_path, "must contain non-empty text")
                        continue
                    emphasis = run.get("emphasis")
                    if emphasis not in {"none", "bold"}:
                        reporter.error(f"{run_path}.emphasis", "contributions allow only none or bold")
                    if emphasis == "bold":
                        bold_count += 1
                    contribution_text += get_str(run, "text")
                if bold_count == 0:
                    reporter.error(f"{path}.runs", "must bold at least one key phrase")
                lines = estimated_lines(contribution_text, CONTRIBUTION_LINE_UNITS)
                if lines < 2:
                    reporter.error(path, "is too short; each contribution should occupy about two lines")
                elif lines > 2:
                    reporter.warn(path, f"is estimated at {lines} lines; target about two lines")

    evidence = plan.get("evidence", [])
    evidence_by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(evidence, list):
        reporter.error("$.evidence", "must be an array")
    else:
        for index, item in enumerate(evidence):
            path = f"$.evidence[{index}]"
            if not isinstance(item, dict):
                reporter.error(path, "must be an object")
                continue
            evidence_id = get_str(item, "id")
            if not re.fullmatch(r"E\d{3}", evidence_id):
                reporter.error(f"{path}.id", "must match E000")
            elif evidence_id in evidence_by_id:
                reporter.error(f"{path}.id", f"duplicate evidence ID '{evidence_id}'")
            else:
                evidence_by_id[evidence_id] = item
            if not get_str(item, "claim"):
                reporter.error(f"{path}.claim", "must be non-empty")
            kind = item.get("kind")
            if kind not in {"paper_claim", "presenter_analysis"}:
                reporter.error(f"{path}.kind", "must be paper_claim or presenter_analysis")
            if kind == "paper_claim" and not (
                isinstance(item.get("paper_page"), int) or get_str(item, "paper_section")
            ):
                reporter.error(path, "paper_claim needs paper_page or paper_section")
            if item.get("confidence") not in {"high", "medium", "low"}:
                reporter.error(f"{path}.confidence", "must be high, medium, or low")

    slides = plan.get("slides")
    if not isinstance(slides, list):
        reporter.error("$.slides", "must be an array")
        return
    if not slides:
        reporter.error("$.slides", "must not be empty")
        return

    target_count = project.get("target_slide_count")
    if not isinstance(target_count, int):
        reporter.error("$.project.target_slide_count", "must be an integer")
    elif target_count != len(slides):
        reporter.error(
            "$.project.target_slide_count",
            f"declares {target_count}, but slides contains {len(slides)} entries",
        )

    slide_ids: set[str] = set()
    titles: dict[str, str] = {}
    current_section: str | None = None
    divider_seen: list[str] = []
    content_count = 0
    none_count = 0
    scripted_seconds = 0
    content_per_section = {section: 0 for section in SECTION_ORDER}

    required_role_counts = {
        "cover": 0,
        "paper_info": 0,
        "one_page": 0,
        "contents": 0,
        "closing": 0,
    }

    for index, slide in enumerate(slides):
        path = f"$.slides[{index}]"
        if not isinstance(slide, dict):
            reporter.error(path, "must be an object")
            continue

        slide_id = get_str(slide, "id")
        if not re.fullmatch(r"S\d{2}", slide_id):
            reporter.error(f"{path}.id", "must match S00")
        elif slide_id in slide_ids:
            reporter.error(f"{path}.id", f"duplicate slide ID '{slide_id}'")
        else:
            slide_ids.add(slide_id)

        slide_type = slide.get("type")
        if slide_type not in SLIDE_TYPES:
            reporter.error(f"{path}.type", f"unsupported slide type '{slide_type}'")
            continue
        if slide_type in required_role_counts:
            required_role_counts[slide_type] += 1

        title = get_str(slide, "title")
        if not title:
            reporter.error(f"{path}.title", "must be non-empty")
        elif title in titles:
            reporter.warn(f"{path}.title", f"duplicates title from {titles[title]}")
        else:
            titles[title] = slide_id or path
        if text_units(title) > 80:
            reporter.warn(f"{path}.title", "may be too long for the template title region")

        notes_text = get_str(slide, "speaker_notes")
        speaker_seconds = slide.get("speaker_seconds")
        if notes_enabled and stage in {"notes", "final"}:
            if not notes_text:
                reporter.error(f"{path}.speaker_notes", "post-QA verbatim script is required")
            if not isinstance(speaker_seconds, int) or not 5 <= speaker_seconds <= 600:
                reporter.error(
                    f"{path}.speaker_seconds", "must be an integer from 5 to 600"
                )
            else:
                scripted_seconds += speaker_seconds
                pace = speaker_config.get("pace_units_per_minute")
                if notes_text and isinstance(pace, int):
                    expected_units = speaker_seconds * pace / 60
                    actual_units = speech_units(notes_text)
                    if actual_units < expected_units * 0.55:
                        reporter.warn(
                            f"{path}.speaker_notes",
                            "is sparse for the allocated speaking time; write a real verbatim script",
                        )
                    elif actual_units > expected_units * 1.55:
                        reporter.warn(
                            f"{path}.speaker_notes",
                            "is dense for the allocated speaking time; shorten or increase speaker_seconds",
                        )
        elif notes_text and not isinstance(speaker_seconds, int):
            reporter.warn(
                f"{path}.speaker_seconds", "add a time budget when a speaker script is present"
            )

        section_id = slide.get("section_id")
        if slide_type == "section_divider":
            if section_id not in SECTION_ORDER:
                reporter.error(f"{path}.section_id", "must identify one of the four sections")
            else:
                divider_seen.append(section_id)
                current_section = section_id

        if slide_type != "content":
            continue

        content_count += 1
        if section_id not in SECTION_ORDER:
            reporter.error(f"{path}.section_id", "content slide needs a valid section")
        else:
            content_per_section[section_id] += 1
            if current_section != section_id:
                reporter.error(
                    f"{path}.section_id",
                    f"content appears under '{current_section}', not '{section_id}'",
                )

        for key in ("purpose", "takeaway"):
            if not get_str(slide, key):
                reporter.error(f"{path}.{key}", "must be non-empty")

        layout = slide.get("layout")
        if layout not in LAYOUTS:
            reporter.error(f"{path}.layout", f"unsupported layout '{layout}'")
        elif layout not in supported_layout_set:
            reporter.error(
                f"{path}.layout", f"layout '{layout}' is not supported by this template"
            )

        body = slide.get("body")
        body_chars = 0
        body_lines = 0
        if not isinstance(body, list) or not (2 <= len(body) <= 5):
            reporter.error(f"{path}.body", "must contain 2-5 body points totaling 5-6 rendered lines")
            body = []
        for point_index, point in enumerate(body):
            point_path = f"{path}.body[{point_index}]"
            if not isinstance(point, dict):
                reporter.error(point_path, "must be an object")
                continue
            runs = point.get("runs")
            if not isinstance(runs, list) or not runs:
                reporter.error(f"{point_path}.runs", "must be a non-empty array")
            else:
                point_text = ""
                for run_index, run in enumerate(runs):
                    run_path = f"{point_path}.runs[{run_index}]"
                    if not isinstance(run, dict) or not get_str(run, "text"):
                        reporter.error(run_path, "run text must be non-empty")
                        continue
                    if run.get("emphasis") not in {"none", "bold", "accent"}:
                        reporter.error(f"{run_path}.emphasis", "invalid emphasis")
                    if run_index == 0 and run.get("emphasis") == "accent":
                        reporter.error(
                            f"{run_path}.emphasis",
                            "the first run cannot use accent color because the bullet would inherit it; use bold",
                        )
                    run_text = get_str(run, "text")
                    body_chars += len(run_text)
                    point_text += run_text
                if point_text:
                    body_lines += estimated_lines(point_text, BODY_LINE_UNITS)

            evidence_ids = point.get("evidence_ids", [])
            if not isinstance(evidence_ids, list):
                reporter.error(f"{point_path}.evidence_ids", "must be an array when provided")
            else:
                for evidence_id in evidence_ids:
                    if evidence_id not in evidence_by_id:
                        reporter.error(
                            f"{point_path}.evidence_ids", f"unknown evidence ID '{evidence_id}'"
                        )
                    elif section_id == "results" and evidence_by_id[evidence_id].get("kind") != "paper_claim":
                        reporter.error(
                            f"{point_path}.evidence_ids",
                            "results bullets must be backed by paper_claim evidence",
                        )

        if body_chars > 320:
            reporter.error(f"{path}.body", f"contains {body_chars} characters; split the slide")
        elif body_chars > 280:
            reporter.warn(f"{path}.body", f"contains {body_chars} characters; check wrapping")
        if body_lines not in {5, 6}:
            reporter.error(
                f"{path}.body",
                f"is estimated at {body_lines} rendered lines; target 5-6 lines for this template",
            )

        visual = slide.get("visual")
        if not isinstance(visual, dict):
            reporter.error(f"{path}.visual", "must be an object")
            continue
        mode = visual.get("mode")
        if mode not in VISUAL_MODES:
            reporter.error(f"{path}.visual.mode", f"unsupported mode '{mode}'")
            continue
        if not get_str(visual, "rationale"):
            reporter.error(f"{path}.visual.rationale", "must explain the visual decision")
        if "alt_text" not in visual or not isinstance(visual.get("alt_text"), str):
            reporter.error(f"{path}.visual.alt_text", "must be a string")

        if mode == "paper_asset":
            if not get_str(visual, "asset_ref"):
                reporter.error(f"{path}.visual.asset_ref", "paper_asset requires an asset path")
            if not isinstance(visual.get("source_refs"), list) or not visual.get("source_refs"):
                reporter.error(f"{path}.visual.source_refs", "paper_asset requires source references")
        elif mode == "tikz":
            if not get_str(visual, "asset_ref"):
                reporter.error(f"{path}.visual.asset_ref", "tikz requires a rendered asset path")
        elif mode == "data_redraw":
            if not get_str(visual, "asset_ref"):
                reporter.error(f"{path}.visual.asset_ref", "data_redraw requires a rendered asset path")
            if not get_str(visual, "data_spec_ref"):
                reporter.error(f"{path}.visual.data_spec_ref", "data_redraw requires its source spec")
        elif mode == "imagegen":
            if section_id == "results":
                reporter.error(f"{path}.visual.mode", "imagegen is forbidden on results slides")
            elif section_id == "method":
                reporter.warn(f"{path}.visual.mode", "imagegen on a method slide may imply false structure")
            if not get_str(visual, "asset_ref"):
                reporter.error(f"{path}.visual.asset_ref", "imagegen requires an output asset path")
            if not get_str(visual, "prompt"):
                reporter.error(f"{path}.visual.prompt", "imagegen requires a recorded prompt")
            if visual.get("no_text") is not True:
                reporter.error(f"{path}.visual.no_text", "imagegen prompt must require no text")
        elif mode == "external_image":
            if section_id == "results":
                reporter.error(f"{path}.visual.mode", "external_image is forbidden on results slides")
            elif section_id == "method":
                reporter.warn(
                    f"{path}.visual.mode",
                    "external_image on a method slide may imply false structure",
                )
            if not get_str(visual, "asset_ref"):
                reporter.error(
                    f"{path}.visual.asset_ref", "external_image requires a downloaded asset path"
                )
            if not get_str(visual, "search_query"):
                reporter.error(
                    f"{path}.visual.search_query", "external_image requires the recorded search query"
                )
            source = visual.get("external_source")
            if not isinstance(source, dict):
                reporter.error(
                    f"{path}.visual.external_source",
                    "external_image requires provenance and license metadata",
                )
            else:
                for key in ("page_url", "license_name", "license_url", "retrieved_at"):
                    if not get_str(source, key):
                        reporter.error(
                            f"{path}.visual.external_source.{key}", "must be non-empty"
                        )
                for key in ("page_url", "license_url"):
                    value = get_str(source, key)
                    if value and not is_http_url(value):
                        reporter.error(
                            f"{path}.visual.external_source.{key}", "must be an HTTP(S) URL"
                        )
                asset_url = get_str(source, "asset_url")
                if asset_url and not is_http_url(asset_url):
                    reporter.error(
                        f"{path}.visual.external_source.asset_url", "must be an HTTP(S) URL"
                    )
                retrieved_at = get_str(source, "retrieved_at")
                if retrieved_at and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved_at):
                    reporter.error(
                        f"{path}.visual.external_source.retrieved_at",
                        "must use YYYY-MM-DD",
                    )
                sha256 = get_str(source, "sha256")
                if sha256 and not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
                    reporter.error(
                        f"{path}.visual.external_source.sha256",
                        "must contain 64 hexadecimal characters",
                    )
        else:
            none_count += 1
            if section_id != "reflection":
                reporter.warn(f"{path}.visual.mode", "none is normally reserved for reflection")

        qa_status = visual.get("qa_status")
        if qa_status not in {"planned", "ready", "approved", "rejected"}:
            reporter.error(f"{path}.visual.qa_status", "invalid QA status")
        if stage == "assembly" and qa_status not in {"ready", "approved"}:
            reporter.error(f"{path}.visual.qa_status", "must be ready or approved for assembly")
        if stage in {"notes", "final"} and qa_status != "approved":
            reporter.error(f"{path}.visual.qa_status", "must be approved for final delivery")

        if stage in {"assembly", "notes", "final"} and mode != "none":
            asset_ref = get_str(visual, "asset_ref")
            if asset_ref and not path_from(base, asset_ref).is_file():
                reporter.error(f"{path}.visual.asset_ref", f"file does not exist: {asset_ref}")
            if mode == "data_redraw":
                spec_ref = get_str(visual, "data_spec_ref")
                if spec_ref and not path_from(base, spec_ref).is_file():
                    reporter.error(f"{path}.visual.data_spec_ref", f"file does not exist: {spec_ref}")
                elif spec_ref:
                    try:
                        spec = json.loads(path_from(base, spec_ref).read_text(encoding="utf-8"))
                        if spec.get("chart_type") == "compact_table":
                            rows = spec.get("table", {}).get("rows", [])
                            points = sum(
                                isinstance(value, (int, float))
                                for row in rows if isinstance(row, list)
                                for value in row
                            )
                        else:
                            points = sum(
                                len(series.get("values", []))
                                for series in spec.get("series", [])
                                if isinstance(series, dict) and isinstance(series.get("values"), list)
                            )
                        if points < 2:
                            reporter.error(
                                f"{path}.visual.data_spec_ref",
                                "data_redraw needs at least two comparable data points; emphasize a lone value in text",
                            )
                    except (OSError, json.JSONDecodeError, AttributeError) as exc:
                        reporter.error(f"{path}.visual.data_spec_ref", f"cannot inspect data spec: {exc}")

        review = slide.get("review")
        if not isinstance(review, dict):
            reporter.error(f"{path}.review", "must be an object")
        elif stage in {"notes", "final"}:
            if review.get("content_approved") is not True:
                reporter.error(f"{path}.review.content_approved", "must be true")
            if review.get("visual_approved") is not True:
                reporter.error(f"{path}.review.visual_approved", "must be true")

    if slides[0].get("type") != "cover":
        reporter.error("$.slides[0].type", "the first slide must be cover")
    if slides[-1].get("type") != "closing":
        reporter.error(f"$.slides[{len(slides) - 1}].type", "the last slide must be closing")

    for role, count in required_role_counts.items():
        if count != 1:
            reporter.error("$.slides", f"requires exactly one '{role}' slide, found {count}")
    if divider_seen != SECTION_ORDER:
        reporter.error(
            "$.slides", f"section dividers must appear exactly in this order: {SECTION_ORDER}"
        )
    for section, count in content_per_section.items():
        if count == 0:
            reporter.error("$.slides", f"section '{section}' has no content slide")

    allowed_none = max(1, math.floor(content_count * 0.2))
    if none_count > allowed_none:
        reporter.error(
            "$.slides",
            f"{none_count}/{content_count} content slides use no visual; maximum is {allowed_none}",
        )

    if notes_enabled and stage in {"notes", "final"}:
        target_seconds = speaker_config.get("target_minutes", 0) * 60
        if target_seconds and not target_seconds * 0.85 <= scripted_seconds <= target_seconds * 1.15:
            reporter.error(
                "$.slides",
                f"speaker scripts total {scripted_seconds / 60:.1f} minutes; "
                f"target {target_seconds / 60:.1f} minutes with a +/-15% tolerance",
            )

    if notes_enabled and stage == "final":
        output_value = get_str(project, "output_pptx")
        if output_value:
            output_path = path_from(base, output_value)
            report_value = get_str(project, "speaker_notes_report")
            report_path = (
                path_from(base, report_value)
                if report_value
                else output_path.with_suffix(".notes.json")
            )
            if not report_path.is_file():
                reporter.error(
                    "$.project.speaker_notes_report",
                    f"post-QA notes report does not exist: {report_path}",
                )
            elif output_path.is_file():
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    if report.get("slides") != len(slides):
                        reporter.error(
                            "$.project.speaker_notes_report",
                            "report slide count does not match the plan",
                        )
                    if report.get("scripted_seconds") != scripted_seconds:
                        reporter.error(
                            "$.project.speaker_notes_report",
                            "report timing does not match the plan",
                        )
                    if report.get("after_sha256") != sha256_file(output_path):
                        reporter.error(
                            "$.project.speaker_notes_report",
                            "PPTX changed after notes were applied",
                        )
                except (OSError, json.JSONDecodeError, AttributeError) as exc:
                    reporter.error(
                        "$.project.speaker_notes_report",
                        f"cannot inspect notes report: {exc}",
                    )

    if stage in {"notes", "final"}:
        output = get_str(project, "output_pptx")
        if not output:
            reporter.error("$.project.output_pptx", "must be a non-empty path")
        elif not path_from(base, output).is_file():
            reporter.error("$.project.output_pptx", f"file does not exist: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="path to deck-plan.json")
    parser.add_argument(
        "--stage", choices=("plan", "assembly", "notes", "final"), default="plan"
    )
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()

    try:
        with args.plan.open("r", encoding="utf-8") as handle:
            plan = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read deck plan: {exc}", file=sys.stderr)
        return 2

    reporter = Reporter()
    validate(plan, args.stage, args.plan.resolve(), reporter)
    for message in reporter.warnings:
        print(message)
    for message in reporter.errors:
        print(message, file=sys.stderr)

    failed = bool(reporter.errors) or (args.warnings_as_errors and reporter.warnings)
    if failed:
        print(
            f"FAIL: {len(reporter.errors)} error(s), {len(reporter.warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: deck plan is valid for stage '{args.stage}'")
    if reporter.warnings:
        print(f"PASS with {len(reporter.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
