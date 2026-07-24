#!/usr/bin/env python3
"""Command-line entry point for the paper-PPT prototype pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def resolve_from(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def render_planned_data(plan_path: Path) -> None:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    base = plan_path.parent
    for slide in plan.get("slides", []):
        visual = slide.get("visual", {})
        if visual.get("mode") != "data_redraw":
            continue
        spec = resolve_from(base, visual["data_spec_ref"])
        output = resolve_from(base, visual["asset_ref"])
        run([sys.executable, str(SCRIPT_DIR / "render_data_viz.py"), str(spec), "-o", str(output)])


def ensure_author_visual(plan_path: Path) -> None:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    base = plan_path.parent
    project = plan["project"]
    output = resolve_from(base, project["author_visual"])
    if output.is_file():
        return
    paper_pdf = resolve_from(base, project["paper_pdf"])
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "crop_author_block.py"),
            str(paper_pdf),
            "-o",
            str(output),
            "--title",
            str(plan["paper"]["title_en"]),
        ]
    )


def plan_output(plan_path: Path) -> Path:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return resolve_from(plan_path.parent, plan["project"]["output_pptx"])


def plan_readability_mode(plan_path: Path) -> str:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return plan.get("project", {}).get("final_readability_mode", "off")


def plan_readability_output_dir(plan_path: Path) -> Path:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = plan.get("project", {}).get(
        "readability_manifest", "qa/readability/manifest.json"
    )
    return resolve_from(plan_path.parent, manifest).parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate deck-plan.json")
    validate.add_argument("plan", type=Path)
    validate.add_argument("--stage", choices=("plan", "assembly", "final"), default="plan")

    preflight = subparsers.add_parser("preflight", help="record host and agent-visible capabilities")
    preflight.add_argument("-o", "--output", type=Path)
    preflight.add_argument("--imagegen", choices=("available", "unavailable", "unknown"), default="unknown")
    preflight.add_argument("--web-search", choices=("available", "unavailable", "unknown"), default="unknown")

    data = subparsers.add_parser("render-data", help="render one PaperEvidenceViz spec")
    data.add_argument("spec", type=Path)
    data.add_argument("-o", "--output", type=Path)

    one_page = subparsers.add_parser("render-one-page-html", help="render a filled one-page HTML file")
    one_page.add_argument("html", type=Path)
    one_page.add_argument("-o", "--output", type=Path, required=True)
    one_page.add_argument("--browser", type=Path)
    one_page.add_argument("--temp-dir", type=Path)
    one_page.add_argument("--timeout", type=int, default=30)
    one_page.add_argument("--allow-no-sandbox", action="store_true")

    crop_image = subparsers.add_parser("crop-image", help="create a focused crop from an extracted raster asset")
    crop_image.add_argument("input", type=Path)
    crop_image.add_argument("-o", "--output", type=Path, required=True)
    crop_image.add_argument("--bbox", required=True, help="normalized x0,y0,x1,y1")
    crop_image.add_argument("--source-label", default="")

    authors = subparsers.add_parser("crop-authors", help="crop paper authors and affiliations")
    authors.add_argument("pdf", type=Path)
    authors.add_argument("-o", "--output", type=Path, required=True)
    authors.add_argument("--page", type=int, default=1)
    authors.add_argument("--title", default="")
    authors.add_argument("--dpi", type=int, default=260)
    authors.add_argument("--bbox", help="manual x0,y0,x1,y1 override in PDF points")

    build = subparsers.add_parser("build", help="build PPTX from a prepared plan")
    build.add_argument("plan", type=Path)
    build.add_argument("-o", "--output", type=Path)

    for qa_action in ("approve-assets", "approve-slides"):
        qa = subparsers.add_parser(qa_action, help=f"apply audited {qa_action} QA transition")
        qa.add_argument("plan", type=Path)
        selection = qa.add_mutually_exclusive_group(required=True)
        selection.add_argument("--slides", nargs="+")
        selection.add_argument("--all-content", action="store_true")
        qa.add_argument("--note", default="")
        qa.add_argument("--actor")
        qa.add_argument("--log", type=Path)
        if qa_action == "approve-slides":
            qa.add_argument("--readability-mode", choices=("off", "overview", "full"))
            qa.add_argument("--readability-manifest", type=Path)

    execute = subparsers.add_parser("run", help="render planned data assets, build PPTX, optionally create overview")
    execute.add_argument("plan", type=Path)
    execute.add_argument("--overview", action="store_true")
    execute.add_argument("--overview-output", type=Path)
    execute.add_argument("--readability-mode", choices=("off", "overview", "full"))
    execute.add_argument("--readability-output-dir", type=Path)
    execute.add_argument("--readability-group-size", type=int, default=4)

    overview = subparsers.add_parser("overview", help="render a PPTX to one overview PNG")
    overview.add_argument("pptx", type=Path)
    overview.add_argument("-o", "--output", type=Path, required=True)
    overview.add_argument("--columns", type=int, default=0)
    overview.add_argument("--thumb-width", type=int, default=720)

    readability = subparsers.add_parser(
        "readability", help="create an optional final-size readability review package"
    )
    readability.add_argument("--mode", choices=("off", "overview", "full"), default="off")
    source = readability.add_mutually_exclusive_group()
    source.add_argument("--pptx", type=Path)
    source.add_argument("--slides-dir", type=Path)
    readability.add_argument("-o", "--output-dir", type=Path, required=True)
    readability.add_argument("--dpi", type=int, default=120)
    readability.add_argument("--group-size", type=int, default=4)

    args = parser.parse_args()
    if args.command == "validate":
        run(
            [
                sys.executable,
                str(SCRIPT_DIR / "validate_deck_plan.py"),
                str(args.plan.resolve()),
                "--stage",
                args.stage,
            ]
        )
    elif args.command == "preflight":
        command = [
            sys.executable,
            str(SCRIPT_DIR / "preflight_capabilities.py"),
            "--imagegen",
            args.imagegen,
            "--web-search",
            args.web_search,
        ]
        if args.output:
            command += ["-o", str(args.output.resolve())]
        run(command)
    elif args.command == "render-data":
        command = [sys.executable, str(SCRIPT_DIR / "render_data_viz.py"), str(args.spec.resolve())]
        if args.output:
            command += ["-o", str(args.output.resolve())]
        run(command)
    elif args.command == "render-one-page-html":
        command = [
            sys.executable,
            str(SCRIPT_DIR / "render_one_page_html.py"),
            str(args.html.resolve()),
            "-o",
            str(args.output.resolve()),
        ]
        if args.browser:
            command += ["--browser", str(args.browser.resolve())]
        if args.temp_dir:
            command += ["--temp-dir", str(args.temp_dir.resolve())]
        command += ["--timeout", str(args.timeout)]
        if args.allow_no_sandbox:
            command += ["--allow-no-sandbox"]
        run(command)
    elif args.command == "crop-image":
        command = [
            sys.executable,
            str(SCRIPT_DIR / "crop_image_region.py"),
            str(args.input.resolve()),
            "-o",
            str(args.output.resolve()),
            "--bbox",
            args.bbox,
        ]
        if args.source_label:
            command += ["--source-label", args.source_label]
        run(command)
    elif args.command == "crop-authors":
        command = [
            sys.executable,
            str(SCRIPT_DIR / "crop_author_block.py"),
            str(args.pdf.resolve()),
            "-o",
            str(args.output.resolve()),
            "--page",
            str(args.page),
            "--dpi",
            str(args.dpi),
        ]
        if args.title:
            command += ["--title", args.title]
        if args.bbox:
            command += ["--bbox", args.bbox]
        run(command)
    elif args.command == "build":
        command = [sys.executable, str(SCRIPT_DIR / "build_ppt.py"), str(args.plan.resolve())]
        if args.output:
            command += ["-o", str(args.output.resolve())]
        run(command)
    elif args.command in {"approve-assets", "approve-slides"}:
        command = [
            sys.executable,
            str(SCRIPT_DIR / "update_qa_status.py"),
            args.command,
            str(args.plan.resolve()),
        ]
        if args.slides:
            command += ["--slides", *args.slides]
        else:
            command += ["--all-content"]
        if args.note:
            command += ["--note", args.note]
        if args.actor:
            command += ["--actor", args.actor]
        if args.log:
            command += ["--log", str(args.log.resolve())]
        if args.command == "approve-slides":
            if args.readability_mode:
                command += ["--readability-mode", args.readability_mode]
            if args.readability_manifest:
                command += [
                    "--readability-manifest",
                    str(args.readability_manifest.resolve()),
                ]
        run(command)
    elif args.command == "overview":
        run(
            [
                sys.executable,
                str(SCRIPT_DIR / "render_deck_overview.py"),
                "--pptx",
                str(args.pptx.resolve()),
                "-o",
                str(args.output.resolve()),
                "--columns",
                str(args.columns),
                "--thumb-width",
                str(args.thumb_width),
            ]
        )
    elif args.command == "readability":
        command = [
            sys.executable,
            str(SCRIPT_DIR / "render_readability.py"),
            "--mode",
            args.mode,
            "-o",
            str(args.output_dir.resolve()),
            "--dpi",
            str(args.dpi),
            "--group-size",
            str(args.group_size),
        ]
        if args.pptx:
            command += ["--pptx", str(args.pptx.resolve())]
        if args.slides_dir:
            command += ["--slides-dir", str(args.slides_dir.resolve())]
        run(command)
    else:
        plan = args.plan.resolve()
        readability_mode = args.readability_mode or plan_readability_mode(plan)
        if args.overview and readability_mode != "off":
            raise SystemExit(
                "--overview and --readability-mode cannot be combined; use readability mode overview"
            )
        ensure_author_visual(plan)
        render_planned_data(plan)
        run([sys.executable, str(SCRIPT_DIR / "build_ppt.py"), str(plan)])
        if args.overview:
            pptx = plan_output(plan)
            overview_output = args.overview_output or pptx.with_suffix(".overview.png")
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "render_deck_overview.py"),
                    "--pptx",
                    str(pptx),
                    "-o",
                    str(overview_output.resolve()),
                ]
            )
        elif readability_mode != "off":
            readability_output = (
                args.readability_output_dir.resolve()
                if args.readability_output_dir
                else plan_readability_output_dir(plan)
            )
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "render_readability.py"),
                    "--mode",
                    readability_mode,
                    "--pptx",
                    str(plan_output(plan)),
                    "-o",
                    str(readability_output),
                    "--group-size",
                    str(args.readability_group_size),
                ]
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
