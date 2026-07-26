from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "paper-ppt-orchestrator"
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_speaker_notes import apply_notes  # noqa: E402
from validate_deck_plan import Reporter, validate  # noqa: E402


class SpeakerNotesTests(unittest.TestCase):
    def source_plan(self) -> dict:
        return json.loads((ROOT / "examples" / "deck-plan.example.json").read_text(encoding="utf-8"))

    def test_notes_are_optional_during_planning_and_required_post_qa(self) -> None:
        plan = self.source_plan()
        plan["project"]["speaker_notes"] = {
            "enabled": True,
            "generation_stage": "post_qa",
            "delivery_style": "verbatim",
            "target_minutes": 15,
            "pace_units_per_minute": 220,
        }
        for slide in plan["slides"]:
            slide.pop("speaker_notes", None)
            slide.pop("speaker_seconds", None)

        planning = Reporter()
        validate(plan, "plan", ROOT / "examples" / "deck-plan.example.json", planning)
        self.assertFalse(any("speaker_notes" in error for error in planning.errors))

        post_qa = Reporter()
        validate(plan, "notes", ROOT / "examples" / "deck-plan.example.json", post_qa)
        note_errors = [error for error in post_qa.errors if "speaker_notes" in error]
        self.assertEqual(len(note_errors), len(plan["slides"]))

    def test_apply_notes_updates_every_slide_on_a_temporary_copy(self) -> None:
        plan = deepcopy(self.source_plan())
        plan["project"]["speaker_notes"] = {
            "enabled": True,
            "generation_stage": "post_qa",
            "delivery_style": "verbatim",
            "target_minutes": 5,
            "pace_units_per_minute": 220,
        }
        for index, slide in enumerate(plan["slides"]):
            slide["speaker_notes"] = f"第 {index + 1} 页的完整逐字稿，用于确定性备注写入测试。"
            slide["speaker_seconds"] = 40 if index == len(plan["slides"]) - 1 else 20

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pptx = root / "presentation.pptx"
            pptx.write_bytes(b"test-pptx")
            plan["project"]["output_pptx"] = str(pptx)
            plan_path = root / "deck-plan.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            calls: list[tuple[Path, list[str]]] = []

            def fake_office(path: Path, arguments: list[str], check: bool = True) -> CompletedProcess[str]:
                calls.append((path, arguments))
                if arguments[:2] == ["view", "issues"]:
                    stdout = "Found 0 issue(s)"
                elif arguments[:2] == ["view", "stats"]:
                    stdout = f"Slides: {len(plan['slides'])}\n"
                else:
                    stdout = "OK"
                return CompletedProcess([], 0, stdout, "")

            with patch("apply_speaker_notes.run_command", return_value=CompletedProcess([], 0, "", "")), patch(
                "apply_speaker_notes.office", side_effect=fake_office
            ):
                report = apply_notes(plan_path)

            note_writes = [arguments for _, arguments in calls if arguments[0] in {"set", "add"}]
            self.assertEqual(len(note_writes), len(plan["slides"]))
            self.assertEqual(report["slides"], len(plan["slides"]))
            self.assertEqual(report["scripted_seconds"], 300)
            self.assertTrue(pptx.with_suffix(".notes.json").is_file())


if __name__ == "__main__":
    unittest.main()
