from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import fitz
import jsonschema
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "paper-ppt-orchestrator"
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_contact_sheet import build_contact_sheet  # noqa: E402
from crop_author_block import crop_author_block  # noqa: E402
from render_data_viz import SpecError, render  # noqa: E402
from preflight_capabilities import choose_conceptual_mode  # noqa: E402
from render_readability import create_package  # noqa: E402
from render_one_page_html import (  # noqa: E402
    browser_candidates,
    build_browser_attempts,
    crop_page,
    validate_html,
)
from validate_deck_plan import Reporter, validate  # noqa: E402
from update_qa_status import QAError, apply_action  # noqa: E402


class WorkflowTests(unittest.TestCase):
    def test_qa_transitions_are_explicit_atomic_and_audited(self) -> None:
        source_plan = json.loads(
            (ROOT / "examples" / "deck-plan.example.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "deck-plan.json"
            slide = next(item for item in source_plan["slides"] if item["id"] == "S13")
            slide["visual"]["qa_status"] = "planned"
            source_plan["project"]["final_readability_mode"] = "full"
            plan_path.write_text(json.dumps(source_plan, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(QAError, "requires visual qa_status ready"):
                apply_action(
                    plan_path,
                    "approve-slides",
                    slide_ids=["S13"],
                    readability_mode="off",
                )

            first = apply_action(
                plan_path,
                "approve-assets",
                slide_ids=["S13"],
                actor="unit-test",
                note="standalone asset review",
            )
            self.assertEqual(first["changes"][0]["after"]["qa_status"], "ready")

            evidence = root / "qa" / "readability" / "groups" / "group-01.png"
            evidence.parent.mkdir(parents=True)
            Image.new("RGB", (100, 100), "white").save(evidence)
            evidence_files = [str(evidence)]
            for index in range(2, 5):
                path = evidence.parent / f"group-{index:02d}.png"
                Image.new("RGB", (100, 100), "white").save(path)
                evidence_files.append(str(path))
            manifest = root / "qa" / "readability" / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "mode": "full",
                        "rendered_slide_count": 14,
                        "group_size": 4,
                        "evidence_files": evidence_files,
                    }
                ),
                encoding="utf-8",
            )
            second = apply_action(
                plan_path,
                "approve-slides",
                slide_ids=["S13"],
                actor="unit-test",
                note="final slide approval",
            )
            self.assertEqual(second["readability"]["mode"], "full")
            final_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            final_slide = next(item for item in final_plan["slides"] if item["id"] == "S13")
            self.assertEqual(final_slide["visual"]["qa_status"], "approved")
            self.assertTrue(final_slide["review"]["content_approved"])
            self.assertTrue(final_slide["review"]["visual_approved"])
            audit_lines = (root / "qa" / "approval-log.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(audit_lines), 2)

    def test_readability_modes_default_off_and_full_groups_four_slides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            off = create_package("off", root / "off")
            self.assertEqual(off["expected_review_calls"], 0)
            self.assertEqual(off["evidence_files"], [])

            slides = root / "slides"
            slides.mkdir()
            for index in range(9):
                image = Image.new("RGB", (640, 360), "white")
                ImageDraw.Draw(image).text((20, 20), f"Slide {index + 1}", fill="black")
                image.save(slides / f"slide-{index + 1:02d}.png")
            full = create_package("full", root / "full", slides_dir=slides)
            self.assertEqual(full["rendered_slide_count"], 9)
            self.assertEqual(full["expected_review_calls"], 3)
            self.assertEqual(len(full["evidence_files"]), 3)
            self.assertTrue(all(Path(path).is_file() for path in full["evidence_files"]))

    def test_capability_routing_uses_external_image_without_retries(self) -> None:
        self.assertEqual(
            choose_conceptual_mode("available", "available")["selected"], "imagegen"
        )
        self.assertEqual(
            choose_conceptual_mode("unavailable", "available")["selected"],
            "external_image",
        )
        self.assertEqual(
            choose_conceptual_mode("unavailable", "unavailable")["selected"],
            "tikz_or_none",
        )
        self.assertEqual(
            choose_conceptual_mode("unknown", "available")["selected"], "unresolved"
        )

    def test_browser_override_and_render_strategies_are_portable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            browser = root / "browser-test"
            browser.touch()
            self.assertEqual(browser_candidates(browser), [browser.resolve()])
            attempts = build_browser_attempts(root / "profile", root / "shot.png")
            self.assertEqual([name for name, _ in attempts], ["modern-headless", "compatibility-headless"])
            self.assertIn("--headless=new", attempts[0][1])
            self.assertIn("--headless", attempts[1][1])
            self.assertNotIn("--no-sandbox", attempts[0][1])

    def test_external_image_plan_requires_auditable_provenance(self) -> None:
        plan_path = ROOT / "examples" / "deck-plan.example.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        external_plan = deepcopy(plan)
        slide = next(item for item in external_plan["slides"] if item["id"] == "S06")
        slide["visual"] = {
            "mode": "external_image",
            "rationale": "Licensed search fallback for conceptual background only.",
            "asset_ref": "assets/external/concept.png",
            "caption": "Concept photo",
            "alt_text": "A conceptual network operations scene",
            "expected_aspect_ratio": "wide",
            "search_query": "network operations conceptual photo",
            "external_source": {
                "provider": "Example Library",
                "creator": "Example Creator",
                "page_url": "https://example.com/photo",
                "asset_url": "https://example.com/photo.jpg",
                "license_name": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "retrieved_at": "2026-07-23",
                "sha256": "a" * 64,
                "transformation": "16:9 crop",
            },
            "qa_status": "ready",
        }
        reporter = Reporter()
        validate(external_plan, "plan", plan_path, reporter)
        self.assertEqual(reporter.errors, [])
        schema = json.loads(
            (SKILL_ROOT / "references" / "deck-plan.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(external_plan, schema)

        del slide["visual"]["external_source"]["license_url"]
        reporter = Reporter()
        validate(external_plan, "plan", plan_path, reporter)
        self.assertTrue(any("license_url" in error for error in reporter.errors))
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(external_plan, schema)

    def test_fixed_one_page_html_has_required_structure(self) -> None:
        validate_html(SKILL_ROOT / "assets" / "one-page-summary.html")

    def test_fixed_one_page_screenshot_crop_removes_outer_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "viewport.png"
            output = Path(directory) / "page.png"
            image = Image.new("RGB", (2000, 1400), (245, 247, 250))
            draw = ImageDraw.Draw(image)
            draw.rectangle((150, 200, 1849, 1199), fill="white")
            image.save(source)
            size = crop_page(source, output)
            self.assertEqual(size, (1700, 1000))
            with Image.open(output) as cropped:
                self.assertEqual(cropped.getpixel((0, 0)), (255, 255, 255))

    def test_data_viz_has_fixed_slide_ratio(self) -> None:
        spec = json.loads((ROOT / "examples" / "data-viz.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "chart.png"
            manifest = render(spec, output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (2400, 1000))
            self.assertEqual(manifest["warnings"], [])

    def test_all_supported_data_viz_types_render(self) -> None:
        output_contract = {
            "width_px": 2400,
            "height_px": 1000,
            "dpi": 200,
            "background": "white",
        }
        chart_specs = {
            "bar": {"categories": ["A", "B", "C"], "series": [{"name": "Score", "values": [2, 4, 3]}]},
            "horizontal_bar": {
                "categories": ["A", "B", "C"],
                "series": [{"name": "Score", "values": [2, 4, 3]}],
            },
            "grouped_bar": {
                "categories": ["A", "B", "C"],
                "series": [
                    {"name": "Baseline", "values": [2, 4, 3]},
                    {"name": "Method", "values": [3, 5, 4]},
                ],
            },
            "line": {
                "categories": ["1", "2", "3"],
                "series": [
                    {"name": "Baseline", "values": [2, 3, 3]},
                    {"name": "Method", "values": [3, 4, 5]},
                ],
            },
            "dot_plot": {
                "categories": ["A", "B", "C"],
                "series": [{"name": "Score", "values": [2, 4, 3]}],
            },
            "heatmap": {
                "categories": ["A", "B", "C"],
                "series": [
                    {"name": "Dataset 1", "values": [2, 4, 3]},
                    {"name": "Dataset 2", "values": [3, 5, 4]},
                ],
            },
            "compact_table": {
                "table": {
                    "columns": ["Method", "Accuracy", "Latency"],
                    "rows": [["Baseline", 91.2, 24], ["Method", 94.8, 18]],
                    "highlight_rows": [1],
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            for chart_type, payload in chart_specs.items():
                with self.subTest(chart_type=chart_type):
                    spec = {
                        "version": "0.1",
                        "chart_type": chart_type,
                        "title": "Stable rendering smoke test",
                        "output": output_contract,
                        **payload,
                    }
                    output = Path(directory) / f"{chart_type}.png"
                    manifest = render(spec, output)
                    with Image.open(output) as image:
                        self.assertEqual(image.size, (2400, 1000))
                        self.assertNotEqual(image.convert("RGB").getbbox(), None)
                    self.assertEqual(manifest["chart_type"], chart_type)

    def test_single_data_point_is_rejected(self) -> None:
        spec = {
            "version": "0.1",
            "chart_type": "horizontal_bar",
            "categories": ["Peak"],
            "series": [{"name": "Reduction", "values": [219]}],
            "output": {"width_px": 2400, "height_px": 1000, "dpi": 200, "background": "white"},
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SpecError, "at least two comparable points"):
                render(spec, Path(directory) / "meaningless-single-value.png")

    def test_author_affiliation_band_is_cropped_between_title_and_abstract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "paper.pdf"
            output = root / "authors.png"
            document = fitz.open()
            page = document.new_page(width=612, height=792)
            page.insert_text((90, 62), "A Stable Paper Title", fontsize=24)
            page.insert_text((145, 126), "Alice Example, Bob Example", fontsize=11)
            page.insert_text((115, 148), "Department of Systems, Example University", fontsize=10)
            page.insert_text((48, 192), "Abstract - This text must not enter the crop.", fontsize=9)
            document.save(pdf)
            document.close()

            manifest = crop_author_block(pdf, output, title="A Stable Paper Title")
            self.assertEqual(manifest["detection"]["confidence"], "high")
            self.assertLess(manifest["crop_bbox"][1], 126)
            self.assertGreater(manifest["crop_bbox"][3], 148)
            self.assertLess(manifest["crop_bbox"][3], 192)
            with Image.open(output) as image:
                self.assertGreater(image.width, image.height * 2)
                self.assertIsNotNone(image.convert("RGB").getbbox())

    def test_forty_slide_overview_uses_six_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            paths: list[Path] = []
            for index in range(40):
                image = Image.new("RGB", (640, 360), "white")
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, 640, 48), fill="#194A96")
                draw.text((20, 140), f"Slide {index + 1}", fill="black")
                path = directory_path / f"slide-{index + 1:02d}.png"
                image.save(path)
                paths.append(path)
            output = directory_path / "overview.png"
            result = build_contact_sheet(paths, output)
            self.assertEqual(result["slides"], 40)
            self.assertEqual(result["columns"], 6)
            self.assertEqual(result["rows"], 7)
            self.assertGreaterEqual(result["width"], 4000)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
