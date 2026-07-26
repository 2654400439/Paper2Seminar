from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy

import fitz


ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "skills" / "paper-ppt-orchestrator" / "webapp"
sys.path.insert(0, str(WEBAPP))

from backend import (  # noqa: E402
    CodexAdapter,
    build_agent_prompt,
    create_job,
    inspect_pdf,
)
from job_runner import agent_environment  # noqa: E402
from job_request import (  # noqa: E402
    JobRequestError,
    confirm_request,
    execution_brief,
    load_contract,
    validate_request,
    write_request,
)


def sample_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((60, 72), "A Reliable System for Paper Presentations", fontsize=22)
    page.insert_text((120, 126), "Alice Example and Bob Example", fontsize=10)
    page.insert_text((48, 190), "Abstract. This paper presents a test system.", fontsize=9)
    payload = document.tobytes()
    document.close()
    return payload


class WebAppTests(unittest.TestCase):
    def configuration(self) -> dict:
        return {
            "title_en": "A Reliable System for Paper Presentations",
            "title_cn": "可靠的论文演示系统",
            "presenter": "Test Presenter",
            "advisor": "Test Advisor",
            "language": "zh-CN",
            "target_minutes": 30,
            "slide_count_mode": "auto",
            "target_slide_count": None,
            "extraction": {
                "backend": "doclayout",
                "device": "cpu",
                "confidence": 0.18,
                "crop_dpi": 300,
                "captioncrop_command": "",
            },
            "visual_capabilities": {"imagegen": "unavailable", "web_search": "unavailable"},
            "readability_mode": "overview",
            "speaker_notes": {
                "enabled": True,
                "generation_stage": "post_qa",
                "delivery_style": "verbatim",
                "target_minutes": 30,
                "pace_units_per_minute": 220,
            },
        }

    def test_pdf_title_is_detected_without_a_model(self) -> None:
        inspection = inspect_pdf(sample_pdf())
        self.assertEqual(inspection["title"], "A Reliable System for Paper Presentations")
        self.assertEqual(inspection["page_count"], 1)
        self.assertTrue(inspection["text_extractable"])

    def test_job_creation_isolated_inputs_and_encodes_post_qa_notes_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = create_job(
                sample_pdf(),
                "unsafe name.pdf",
                self.configuration(),
                jobs_root=Path(directory),
                template_payload=b"test-template",
            )
            job_dir = Path(request["execution"]["paths"]["job_dir"])
            self.assertTrue((job_dir / "input" / "paper.pdf").is_file())
            self.assertTrue((job_dir / "input" / "template.pptx").is_file())
            self.assertEqual(
                json.loads((job_dir / "job-request.json").read_text(encoding="utf-8"))["job"]["id"],
                request["job"]["id"],
            )
            self.assertEqual(request["interaction"]["source"], "web_ui")
            self.assertEqual(request["interaction"]["mode"], "non_interactive")
            self.assertTrue(request["interaction"]["confirmed"])
            self.assertTrue(request["features"]["speaker_notes"]["enabled"])
            self.assertEqual(request["features"]["readability"]["config"]["mode"], "overview")
            validate_request(request)
            prompt = (job_dir / "agent-prompt.txt").read_text(encoding="utf-8")
            self.assertIn("job-request.json", prompt)
            self.assertIn("不要重复询问用户", prompt)
            self.assertIn("status=reserved", prompt)

    def test_unconfirmed_prompt_does_not_bypass_intake_confirmation(self) -> None:
        request = json.loads(
            (ROOT / "examples" / "job-request.example.json").read_text(encoding="utf-8")
        )
        prompt = build_agent_prompt(request)
        self.assertIn("\u5c1a\u672a\u786e\u8ba4", prompt)
        self.assertIn("\u4e0d\u8981\u5f00\u59cb\u5b8c\u6574\u5de5\u4f5c\u6d41\u7a0b", prompt)
        self.assertNotIn("\u8be5\u4efb\u52a1\u5df2\u7ecf\u7531 skill_chat \u5165\u53e3\u786e\u8ba4", prompt)

    def test_feature_registry_and_default_profile_are_synchronized(self) -> None:
        _schema, defaults, registry = load_contract()
        profile = defaults["profiles"][defaults["default_profile"]]
        self.assertEqual(set(profile["features"]), set(registry["features"]))
        for feature_id, metadata in registry["features"].items():
            self.assertEqual(profile["features"][feature_id]["status"], metadata["status"])
            self.assertEqual(
                profile["features"][feature_id]["enabled"], metadata["default_enabled"]
            )

    def test_unregistered_or_reserved_feature_cannot_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = create_job(
                sample_pdf(),
                "paper.pdf",
                self.configuration(),
                jobs_root=Path(directory),
                template_payload=b"test-template",
            )
            unknown = deepcopy(request)
            unknown["features"]["future_magic"] = {
                "enabled": True,
                "status": "available",
                "config": {},
            }
            with self.assertRaisesRegex(JobRequestError, "unregistered feature"):
                validate_request(unknown)

            reserved = deepcopy(request)
            reserved["features"]["layout_selection"]["enabled"] = True
            with self.assertRaisesRegex(JobRequestError, "reserved feature"):
                validate_request(reserved)

    def test_confirm_once_request_has_one_intake_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = create_job(
                sample_pdf(),
                "paper.pdf",
                self.configuration(),
                jobs_root=Path(directory),
                template_payload=b"test-template",
            )
            request["interaction"] = {
                "source": "skill_chat",
                "mode": "confirm_once",
                "confirmed": False,
                "confirmed_at": None,
                "review_checkpoints": ["intake", "final"],
            }
            request["input"]["paper"]["title_confirmed"] = False
            request_path = Path(directory) / "job-request.json"
            write_request(request_path, request)
            self.assertIn("等待确认", execution_brief(request))

            confirmed = confirm_request(request_path)
            self.assertTrue(confirmed["interaction"]["confirmed"])
            self.assertIsNotNone(confirmed["interaction"]["confirmed_at"])
            self.assertTrue(confirmed["input"]["paper"]["title_confirmed"])

    def test_cli_init_compiles_a_confirmed_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            paper_path = temporary / "paper.pdf"
            paper_path.write_bytes(sample_pdf())
            request_path = temporary / "job-request.json"
            run_dir = temporary / "run"
            script = ROOT / "skills" / "paper-ppt-orchestrator" / "scripts" / "paper_ppt.py"
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "job-request",
                    "init",
                    "--paper",
                    str(paper_path),
                    "--run-dir",
                    str(run_dir),
                    "--title",
                    "A Reliable System for Paper Presentations",
                    "--job-id",
                    "cli-example",
                    "--interaction-mode",
                    "non_interactive",
                    "--confirmed",
                    "-o",
                    str(request_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            request = json.loads(request_path.read_text(encoding="utf-8"))
            validate_request(request)
            self.assertEqual(request["interaction"]["source"], "skill_chat")
            self.assertTrue(request["input"]["paper"]["title_confirmed"])

    def test_interaction_state_must_be_semantically_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = create_job(
                sample_pdf(),
                "paper.pdf",
                self.configuration(),
                jobs_root=Path(directory),
                template_payload=b"test-template",
            )
            inconsistent = deepcopy(request)
            inconsistent["interaction"]["confirmed"] = False
            inconsistent["interaction"]["confirmed_at"] = None
            with self.assertRaisesRegex(JobRequestError, "must already be confirmed"):
                validate_request(inconsistent)

            wrong_checkpoints = deepcopy(request)
            wrong_checkpoints["interaction"]["review_checkpoints"] = ["intake", "final"]
            with self.assertRaisesRegex(JobRequestError, "review_checkpoints"):
                validate_request(wrong_checkpoints)

    def test_codex_adapter_uses_argv_and_workspace_sandbox(self) -> None:
        with patch("backend.shutil.which", side_effect=lambda name: "C:/Tools/codex.cmd" if name == "codex.cmd" else None):
            command = CodexAdapter.command(ROOT)
        self.assertEqual(command[0], "C:/Tools/codex.cmd")
        self.assertIn("workspace-write", command)
        self.assertEqual(command[-1], "-")

    def test_codex_authentication_distinguishes_installation_and_login(self) -> None:
        with patch("backend.shutil.which", return_value="C:/Tools/codex.cmd"), patch(
            "backend.subprocess.run"
        ) as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = "Not logged in"
            status = CodexAdapter.authentication()
        self.assertTrue(status["installed"])
        self.assertFalse(status["authenticated"])
        self.assertEqual(status["detail"], "Not logged in")

    def test_runner_keeps_mutable_tool_caches_inside_the_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_dir = Path(directory) / "job"
            environment = agent_environment(job_dir)
            self.assertEqual(
                Path(environment["YOLO_CONFIG_DIR"]).parent,
                (job_dir / ".cache").resolve(),
            )
            self.assertEqual(
                Path(environment["MPLCONFIGDIR"]).parent,
                (job_dir / ".cache").resolve(),
            )
            self.assertTrue(Path(environment["YOLO_CONFIG_DIR"]).is_dir())


if __name__ == "__main__":
    unittest.main()
