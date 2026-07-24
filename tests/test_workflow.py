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
from extract_paper_assets import (  # noqa: E402
    Detection,
    ExtractionConfig,
    ExtractionError,
    build_parser as build_extraction_parser,
    deduplicate,
    extract_pdf,
    intersection_over_union,
    run_captioncrop,
    verify_model,
)


class FakeLayoutPredictor:
    def __init__(self, pages: list[list[Detection]]) -> None:
        self.pages = pages
        self.calls = 0

    def predict(self, _image: Image.Image) -> list[Detection]:
        result = self.pages[self.calls]
        self.calls += 1
        return result


class WorkflowTests(unittest.TestCase):
    def test_doclayout_is_the_default_extraction_backend(self) -> None:
        args = build_extraction_parser().parse_args(["paper.pdf", "-o", "assets"])
        self.assertEqual(args.backend, "doclayout")
        self.assertEqual(args.confidence, 0.18)
        self.assertEqual(args.detection_dpi, 144)
        self.assertEqual(args.crop_dpi, 300)

    def test_detection_deduplication_is_same_class_and_confidence_ordered(self) -> None:
        figure = Detection("figure", 0.95, (10, 10, 110, 110))
        duplicate = Detection("figure", 0.70, (12, 12, 108, 108))
        overlapping_table = Detection("table", 0.80, (10, 10, 110, 110))
        self.assertGreater(intersection_over_union(figure.bbox_pixels, duplicate.bbox_pixels), 0.75)
        retained = deduplicate([duplicate, overlapping_table, figure], 0.75)
        self.assertEqual({(item.kind, item.confidence) for item in retained}, {("figure", 0.95), ("table", 0.80)})

    def test_doclayout_extraction_writes_complete_portable_qa_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "paper.pdf"
            output = root / "assets"
            document = fitz.open()
            first = document.new_page(width=612, height=792)
            first.insert_text((58, 326), "Algorithm 1 Example procedure", fontsize=11)
            second = document.new_page(width=612, height=792)
            second.insert_text((58, 126), "Table I Results", fontsize=11)
            document.save(pdf)
            document.close()

            predictor = FakeLayoutPredictor(
                [
                    [
                        Detection("figure", 0.95, (100, 100, 300, 250)),
                        Detection("figure", 0.70, (102, 102, 298, 248)),
                        Detection("figure", 0.88, (320, 100, 550, 250)),
                        Detection("table", 0.92, (50, 300, 300, 420)),
                    ],
                    [Detection("table", 0.90, (50, 100, 560, 300))],
                ]
            )
            config = ExtractionConfig(detection_dpi=72, crop_dpi=144)
            summary = extract_pdf(pdf, output, predictor, config)

            self.assertEqual(predictor.calls, 2)
            self.assertEqual(summary["figures"], 2)
            self.assertEqual(summary["tables"], 1)
            self.assertEqual(summary["total"], 3)
            self.assertEqual(summary["deduplicated_detections"], 1)
            self.assertEqual(summary["rejected_detections"][0]["reason"], "algorithm_block")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in manifest], ["figure_01", "figure_02", "table_01"])
            self.assertTrue(all(item["review_status"] == "unreviewed" for item in manifest))
            self.assertTrue(all(not Path(item["file"]).is_absolute() for item in manifest))
            self.assertTrue(all("absolute_file" not in item for item in manifest))
            self.assertEqual(manifest[0]["bbox_pdf_points"], [95.0, 95.0, 305.0, 255.0])
            for item in manifest:
                crop = output / item["file"]
                self.assertTrue(crop.is_file())
                with Image.open(crop) as image:
                    self.assertEqual(image.size, (item["width"], item["height"]))
            self.assertTrue((output / "manifest.csv").is_file())
            self.assertTrue((output / "contact_sheet.jpg").is_file())
            self.assertEqual(len(list((output / "annotated_pages").glob("*.jpg"))), 2)

            with self.assertRaisesRegex(ExtractionError, "pass --clean"):
                extract_pdf(pdf, output, predictor, config)

    def test_unverified_model_and_captioncrop_compatibility_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            untrusted = root / "model.pt"
            untrusted.write_bytes(b"not a model")
            with self.assertRaisesRegex(ExtractionError, "SHA-256 mismatch"):
                verify_model(untrusted)
            self.assertEqual(len(verify_model(untrusted, allow_unverified=True)), 64)

            capture = root / "args.json"
            script = root / "caption_crop.py"
            script.write_text(
                "import json, pathlib, sys\n"
                f"pathlib.Path({str(capture)!r}).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n",
                encoding="utf-8",
            )
            run_captioncrop(
                root / "paper.pdf",
                root / "output",
                command=script,
                dpi=260,
                clean=True,
            )
            arguments = json.loads(capture.read_text(encoding="utf-8"))
            self.assertIn("--contact-sheet", arguments)
            self.assertIn("--clean", arguments)
            self.assertEqual(arguments[arguments.index("--dpi") + 1], "260")

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
