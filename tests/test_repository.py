from __future__ import annotations

import hashlib
import re
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "paper-ppt-orchestrator"


class RepositoryTests(unittest.TestCase):
    def test_canonical_skill_has_required_frontmatter(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", content, flags=re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1) if match else ""
        self.assertRegex(frontmatter, r"(?m)^name: paper-ppt-orchestrator$")
        self.assertRegex(frontmatter, r"(?m)^description: .+$")
        keys = [line.split(":", 1)[0] for line in frontmatter.splitlines() if ":" in line]
        self.assertEqual(keys, ["name", "description"])

    def test_bundled_assets_match_published_contract(self) -> None:
        html = (SKILL_ROOT / "assets" / "one-page-summary.html").read_text(encoding="utf-8")
        for value in ("CartoX", "YY讨论班"):
            with self.subTest(value=value):
                self.assertNotIn(value, html)

        template = SKILL_ROOT / "assets" / "seminar-template.pptx"
        self.assertEqual(
            hashlib.sha256(template.read_bytes()).hexdigest().upper(),
            "EB13C0DB98C43AE5660381D0D7BC2ECE33E7D9796CD7FCFA111137F08C3B99A6",
        )
        with zipfile.ZipFile(template) as archive:
            self.assertEqual(
                len([name for name in archive.namelist() if name.startswith("ppt/media/")]),
                8,
            )
            checked_parts = [
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ]
            package_text = "\n".join(
                "".join(ET.fromstring(archive.read(name)).itertext()) for name in checked_parts
            )
        self.assertIn("程逸飞", package_text)
        self.assertIn("朱宇佳", package_text)
        self.assertIn("{{IMG_author}}", package_text)
        self.assertIn("{{IMG_YY_one_page}}", package_text)

    def test_repository_loaders_point_to_canonical_skill(self) -> None:
        expected = "../../../skills/paper-ppt-orchestrator/SKILL.md"
        for loader in (
            ROOT / ".agents" / "skills" / "paper-ppt-orchestrator" / "SKILL.md",
            ROOT / ".claude" / "skills" / "paper-ppt-orchestrator" / "SKILL.md",
        ):
            with self.subTest(loader=loader):
                self.assertIn(expected, loader.read_text(encoding="utf-8"))

    def test_doclayout_backend_is_self_contained_without_bundled_weights(self) -> None:
        required = (
            SKILL_ROOT / "scripts" / "extract_paper_assets.py",
            SKILL_ROOT / "references" / "figure-extraction.md",
            SKILL_ROOT / "requirements-doclayout.txt",
        )
        self.assertTrue(all(path.is_file() for path in required))
        requirements = required[2].read_text(encoding="utf-8")
        self.assertIn("doclayout-yolo==0.0.4", requirements)
        self.assertIn("torchvision==0.23.0", requirements)
        self.assertEqual(list(SKILL_ROOT.rglob("*.pt")), [])

    def test_curated_examples_are_complete(self) -> None:
        decks = {
            ROOT / "examples" / "decks" / "webcloak-seminar.pptx": 32,
            ROOT / "examples" / "decks" / "beyond-rtt-seminar.pptx": 30,
        }
        for deck, expected_slides in decks.items():
            with self.subTest(deck=deck):
                self.assertTrue(deck.is_file())
                with zipfile.ZipFile(deck) as archive:
                    slides = [
                        name
                        for name in archive.namelist()
                        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                    ]
                self.assertEqual(len(slides), expected_slides)

        gallery = ROOT / "examples" / "gallery"
        expected_images = {
            "webcloak-paper-evidence.png",
            "webcloak-method.png",
            "beyond-rtt-tikz.png",
            "beyond-rtt-results.png",
            "webcloak-overview.png",
            "beyond-rtt-overview.png",
        }
        self.assertEqual({path.name for path in gallery.glob("*.png")}, expected_images)
        for name in expected_images:
            self.assertGreater((gallery / name).stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
