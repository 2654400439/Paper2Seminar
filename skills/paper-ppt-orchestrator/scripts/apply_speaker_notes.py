#!/usr/bin/env python3
"""Apply post-QA per-slide speaker scripts to an existing PPTX."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


class NotesError(RuntimeError):
    pass


def run_command(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        output = completed.stderr.strip() or completed.stdout.strip()
        raise NotesError(f"command failed ({completed.returncode}): {' '.join(command[:4])}\n{output}")
    return completed


def office(pptx: Path, arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(["officecli", *arguments[:1], str(pptx), *arguments[1:]], check=check)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_from(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def load_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NotesError(f"cannot read deck plan: {exc}") from exc
    if not isinstance(payload, dict):
        raise NotesError("deck plan must be a JSON object")
    return payload


def set_notes(pptx: Path, slide_number: int, text: str) -> None:
    path = f"/slide[{slide_number}]/notes"
    existing = office(pptx, ["get", path], check=False)
    if existing.returncode == 0:
        office(pptx, ["set", path, "--prop", f"text={text}"])
    else:
        office(pptx, ["add", f"/slide[{slide_number}]", "--type", "notes", "--prop", f"text={text}"])


def slide_count(pptx: Path) -> int:
    stats = office(pptx, ["view", "stats"])
    match = re.search(r"(?m)^Slides:\s*(\d+)\s*$", stats.stdout)
    if not match:
        raise NotesError("OfficeCLI stats did not report a slide count")
    return int(match.group(1))


def replace_with_retry(source: Path, destination: Path, attempts: int = 20) -> None:
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.1)


def unlink_with_retry(path: Path, attempts: int = 20) -> None:
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == attempts - 1:
                return
            time.sleep(0.1)


def apply_notes(plan_path: Path, pptx_override: Path | None = None) -> dict[str, Any]:
    validator = SCRIPT_DIR / "validate_deck_plan.py"
    run_command([sys.executable, str(validator), str(plan_path), "--stage", "notes"])

    plan = load_plan(plan_path)
    base = plan_path.parent
    configured = resolve_from(base, str(plan["project"]["output_pptx"]))
    output = pptx_override.resolve() if pptx_override else configured
    if not output.is_file():
        raise NotesError(f"PPTX does not exist: {output}")
    actual_slide_count = slide_count(output)
    if actual_slide_count != len(plan["slides"]):
        raise NotesError(
            f"PPTX slide count does not match deck plan: {actual_slide_count} != {len(plan['slides'])}"
        )

    temporary = output.with_name(f".{output.stem}.notes.tmp{output.suffix}")
    shutil.copy2(output, temporary)
    before_sha256 = sha256_file(output)
    slides = plan["slides"]
    try:
        for slide_number, slide in enumerate(slides, start=1):
            set_notes(temporary, slide_number, str(slide["speaker_notes"]).strip())
        office(temporary, ["save"])
        validation = office(temporary, ["validate"])
        issues = office(temporary, ["view", "issues", "--limit", "200"])
        if "Found 0 issue(s)" not in issues.stdout:
            raise NotesError(f"OfficeCLI reported issues after adding notes:\n{issues.stdout}")
        replace_with_retry(temporary, output)
    finally:
        unlink_with_retry(temporary)

    total_seconds = sum(int(slide["speaker_seconds"]) for slide in slides)
    report = {
        "schema_version": "0.1",
        "operation": "post_qa_speaker_notes",
        "plan": str(plan_path.resolve()),
        "output": str(output),
        "slides": len(slides),
        "target_minutes": plan["project"]["speaker_notes"]["target_minutes"],
        "scripted_seconds": total_seconds,
        "before_sha256": before_sha256,
        "after_sha256": sha256_file(output),
        "validation": validation.stdout.strip(),
        "issues": issues.stdout.strip(),
    }
    report_value = str(plan["project"].get("speaker_notes_report") or "").strip()
    report_path = resolve_from(base, report_value) if report_value else output.with_suffix(".notes.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--pptx", type=Path, help="override project.output_pptx")
    args = parser.parse_args()
    try:
        report = apply_notes(args.plan.resolve(), args.pptx)
    except (NotesError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Applied speaker notes: {report['output']}")
    print(f"Slides: {report['slides']}; scripted time: {report['scripted_seconds'] / 60:.1f} minutes")
    print(f"Report: {report['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
