from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "paper-ppt-orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_paper_assets import (  # noqa: E402
    DocLayoutPredictor,
    ExtractionConfig,
    extract_pdf,
)


MODEL = os.environ.get("PAPER_PPT_TEST_DOCLAYOUT_MODEL")
CLEARING_PDF = os.environ.get("PAPER_PPT_TEST_CLEARING_PDF")
DIFFICULT_PDF = os.environ.get("PAPER_PPT_TEST_DIFFICULT_PDF")
HAS_FIXTURES = all((MODEL, CLEARING_PDF, DIFFICULT_PDF))


@unittest.skipUnless(
    HAS_FIXTURES,
    "set PAPER_PPT_TEST_DOCLAYOUT_MODEL, PAPER_PPT_TEST_CLEARING_PDF, and PAPER_PPT_TEST_DIFFICULT_PDF",
)
class DocLayoutRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output_root = Path(cls.temporary.name)
        cls.config = ExtractionConfig()
        cls.model_path = Path(str(MODEL)).resolve()
        cls.predictor = DocLayoutPredictor(
            cls.model_path,
            cls.config,
            cache_dir=cls.output_root / "cache",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def assert_regression(
        self, pdf: str, name: str, figures: int, tables: int, deduplicated: int
    ) -> None:
        output = self.output_root / name
        summary = extract_pdf(
            Path(pdf),
            output,
            self.predictor,
            self.config,
            model_path=self.model_path,
            model_sha256=self.predictor.model_sha256,
        )
        self.assertEqual((summary["figures"], summary["tables"]), (figures, tables))
        self.assertEqual(summary["deduplicated_detections"], deduplicated)
        self.assertEqual(
            [item["reason"] for item in summary["rejected_detections"]],
            ["algorithm_block"],
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest), figures + tables)
        self.assertTrue((output / "contact_sheet.jpg").is_file())
        for entry in manifest:
            self.assertFalse(Path(entry["file"]).is_absolute())
            self.assertNotIn("absolute_file", entry)
            with Image.open(output / entry["file"]) as image:
                self.assertEqual(image.size, (entry["width"], entry["height"]))

    def test_clearing_the_clutter_baseline(self) -> None:
        self.assert_regression(str(CLEARING_PDF), "clearing", 7, 3, 0)

    def test_difficult_paper_baseline(self) -> None:
        self.assert_regression(str(DIFFICULT_PDF), "difficult", 10, 12, 1)


if __name__ == "__main__":
    unittest.main()
