#!/usr/bin/env python3
"""Apply explicit, audited QA transitions to content slides in a deck plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class QAError(RuntimeError):
    pass


def resolve_from(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_content_slides(
    plan: dict[str, Any], slide_ids: list[str] | None, all_content: bool
) -> list[dict[str, Any]]:
    if bool(slide_ids) == all_content:
        raise QAError("choose exactly one of --slides or --all-content")
    content = [slide for slide in plan.get("slides", []) if slide.get("type") == "content"]
    if all_content:
        return content
    by_id = {slide.get("id"): slide for slide in content}
    missing = [slide_id for slide_id in slide_ids or [] if slide_id not in by_id]
    if missing:
        raise QAError(f"unknown or non-content slide IDs: {', '.join(missing)}")
    return [by_id[slide_id] for slide_id in slide_ids or []]


def require_asset(plan_base: Path, slide: dict[str, Any]) -> None:
    visual = slide.get("visual", {})
    if visual.get("mode") == "none":
        return
    asset_ref = visual.get("asset_ref")
    if not isinstance(asset_ref, str) or not asset_ref.strip():
        raise QAError(f"{slide.get('id')}: visual asset_ref is missing")
    asset = resolve_from(plan_base, asset_ref)
    if not asset.is_file():
        raise QAError(f"{slide.get('id')}: visual asset does not exist: {asset_ref}")


def readability_evidence(
    plan: dict[str, Any],
    plan_base: Path,
    mode_override: str | None,
    manifest_override: Path | None,
) -> dict[str, Any]:
    project = plan.get("project", {})
    mode = mode_override or project.get("final_readability_mode", "off")
    if mode not in {"off", "overview", "full"}:
        raise QAError(f"invalid readability mode: {mode}")
    if mode == "off":
        return {"mode": "off", "manifest": None, "manifest_sha256": None}
    manifest_value = project.get("readability_manifest", "qa/readability/manifest.json")
    manifest = manifest_override.resolve() if manifest_override else resolve_from(plan_base, manifest_value)
    if not manifest.is_file():
        raise QAError(f"readability mode '{mode}' requires a manifest: {manifest}")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QAError(f"cannot read readability manifest: {exc}") from exc
    if payload.get("mode") != mode:
        raise QAError(
            f"readability manifest mode is '{payload.get('mode')}', expected '{mode}'"
        )
    evidence_files = payload.get("evidence_files")
    if not isinstance(evidence_files, list) or not evidence_files:
        raise QAError("readability manifest contains no review evidence files")
    for value in evidence_files:
        if not isinstance(value, str):
            raise QAError("readability manifest evidence_files must contain paths")
        evidence_path = resolve_from(manifest.parent, value)
        if not evidence_path.is_file():
            raise QAError(f"readability evidence does not exist: {value}")
    if mode == "full" and payload.get("group_size") not in {1, 2, 3, 4}:
        raise QAError("full readability review requires group_size between 1 and 4")
    declared_count = project.get("target_slide_count")
    rendered_count = payload.get("rendered_slide_count")
    if isinstance(declared_count, int) and rendered_count != declared_count:
        raise QAError(
            f"readability manifest covers {rendered_count} slides, expected {declared_count}"
        )
    if mode == "overview" and len(evidence_files) != 1:
        raise QAError("overview readability review requires exactly one evidence image")
    if mode == "full":
        group_size = int(payload["group_size"])
        expected_files = math.ceil(int(rendered_count) / group_size)
        if len(evidence_files) != expected_files:
            raise QAError(
                f"full readability review has {len(evidence_files)} evidence images, expected {expected_files}"
            )
    return {
        "mode": mode,
        "manifest": str(manifest),
        "manifest_sha256": file_hash(manifest),
        "evidence_files": len(evidence_files),
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def append_audit(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def apply_action(
    plan_path: Path,
    action: str,
    *,
    slide_ids: list[str] | None = None,
    all_content: bool = False,
    note: str = "",
    actor: str | None = None,
    log_path: Path | None = None,
    readability_mode: str | None = None,
    readability_manifest: Path | None = None,
) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QAError(f"cannot read deck plan: {exc}") from exc
    selected = select_content_slides(plan, slide_ids, all_content)
    if not selected:
        raise QAError("no content slides selected")
    before_hash = file_hash(plan_path)
    changes: list[dict[str, Any]] = []

    evidence = {"mode": "not_applicable", "manifest": None, "manifest_sha256": None}
    if action == "approve-slides":
        evidence = readability_evidence(
            plan, plan_path.parent, readability_mode, readability_manifest
        )

    for slide in selected:
        slide_id = str(slide.get("id"))
        visual = slide.get("visual")
        review = slide.get("review")
        if not isinstance(visual, dict) or not isinstance(review, dict):
            raise QAError(f"{slide_id}: content slide lacks visual/review state")
        require_asset(plan_path.parent, slide)
        current = visual.get("qa_status")
        before = {
            "qa_status": current,
            "content_approved": review.get("content_approved"),
            "visual_approved": review.get("visual_approved"),
        }
        if action == "approve-assets":
            if current == "rejected":
                raise QAError(f"{slide_id}: rejected asset must be replaced before approval")
            if current not in {"planned", "ready", "approved"}:
                raise QAError(f"{slide_id}: invalid visual QA state: {current}")
            if current != "approved":
                visual["qa_status"] = "ready"
        elif action == "approve-slides":
            if current not in {"ready", "approved"}:
                raise QAError(
                    f"{slide_id}: final approval requires visual qa_status ready or approved, got {current}"
                )
            visual["qa_status"] = "approved"
            review["content_approved"] = True
            review["visual_approved"] = True
        else:
            raise QAError(f"unsupported action: {action}")
        after = {
            "qa_status": visual.get("qa_status"),
            "content_approved": review.get("content_approved"),
            "visual_approved": review.get("visual_approved"),
        }
        changes.append({"slide_id": slide_id, "before": before, "after": after})

    atomic_write_json(plan_path, plan)
    after_hash = file_hash(plan_path)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor or os.environ.get("PAPER_PPT_ACTOR") or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "note": note,
        "plan": str(plan_path),
        "plan_sha256_before": before_hash,
        "plan_sha256_after": after_hash,
        "readability": evidence,
        "changes": changes,
    }
    audit_path = log_path.resolve() if log_path else plan_path.parent / "qa" / "approval-log.jsonl"
    append_audit(audit_path, event)
    event["audit_log"] = str(audit_path)
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("approve-assets", "approve-slides"))
    parser.add_argument("plan", type=Path)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--slides", nargs="+")
    selection.add_argument("--all-content", action="store_true")
    parser.add_argument("--note", default="")
    parser.add_argument("--actor")
    parser.add_argument("--log", type=Path)
    parser.add_argument("--readability-mode", choices=("off", "overview", "full"))
    parser.add_argument("--readability-manifest", type=Path)
    args = parser.parse_args()
    try:
        event = apply_action(
            args.plan,
            args.action,
            slide_ids=args.slides,
            all_content=args.all_content,
            note=args.note,
            actor=args.actor,
            log_path=args.log,
            readability_mode=args.readability_mode,
            readability_manifest=args.readability_manifest,
        )
    except QAError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        f"QA transition: {event['action']} | {len(event['changes'])} slides | "
        f"log: {event['audit_log']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
