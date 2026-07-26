#!/usr/bin/env python3
"""Build the fixed-layout paper presentation from deck-plan.json."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image


SECTION_ORDER = ["background", "method", "results", "reflection"]
TEMPLATE_CONTENT_SLIDES = {
    "background": 6,
    "method": 8,
    "results": 10,
    "reflection": 12,
}
EMU_PER_CM = 360000.0
EMU_PER_INCH = 914400.0
EMU_PER_PT = 12700.0

# Generated text sizes are explicit so template placeholder defaults cannot silently change them.
CONTENT_TITLE_SIZE = "18pt"
CONTENT_BODY_SIZE = "18pt"
CONTRIBUTION_SIZE = "18pt"


class BuildError(RuntimeError):
    pass


def run_command(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if check and completed.returncode != 0:
        output = completed.stderr.strip() or completed.stdout.strip()
        raise BuildError(f"command failed ({completed.returncode}): {' '.join(command[:4])}\n{output}")
    return completed


def office(pptx: Path, arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(["officecli", *arguments[:1], str(pptx), *arguments[1:]], check=check)


def office_get_json(pptx: Path, path: str, depth: int = 1) -> dict[str, Any]:
    completed = office(pptx, ["get", path, "--depth", str(depth), "--json"])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BuildError(f"officecli returned invalid JSON for {path}: {exc}") from exc


def office_query_json(pptx: Path, selector: str) -> dict[str, Any]:
    completed = office(pptx, ["query", selector, "--json"])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BuildError(f"officecli returned invalid JSON for selector {selector}: {exc}") from exc


def load_plan(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            plan = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"cannot read plan: {exc}") from exc
    if not isinstance(plan, dict):
        raise BuildError("deck plan must be a JSON object")
    return plan


def resolve_from(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def plan_content(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    content = {section: [] for section in SECTION_ORDER}
    for slide in plan.get("slides", []):
        if slide.get("type") == "content":
            section = slide.get("section_id")
            if section not in content:
                raise BuildError(f"content slide {slide.get('id')} has invalid section {section}")
            if slide.get("layout") != "content_stacked":
                raise BuildError(f"P0 supports only content_stacked: {slide.get('id')}")
            content[section].append(slide)
    for section, slides in content.items():
        if not slides:
            raise BuildError(f"section {section} has no content slide")
    return content


def validate_plan(plan_path: Path) -> None:
    validator = Path(__file__).with_name("validate_deck_plan.py")
    run_command([sys.executable, str(validator), str(plan_path), "--stage", "assembly"])


def clone_content_slides(pptx: Path, content: dict[str, list[dict[str, Any]]]) -> None:
    for section in reversed(SECTION_ORDER):
        base_slide = TEMPLATE_CONTENT_SLIDES[section]
        extras = content[section][1:]
        for _slide in reversed(extras):
            office(
                pptx,
                [
                    "add",
                    "/",
                    "--from",
                    f"/slide[{base_slide}]",
                    "--index",
                    str(base_slide),
                ],
            )


def slide_children(pptx: Path, slide_number: int) -> list[dict[str, Any]]:
    document = office_get_json(pptx, f"/slide[{slide_number}]", depth=1)
    results = document.get("data", {}).get("results", [])
    if not results:
        raise BuildError(f"slide {slide_number} was not found")
    return results[0].get("children", [])


def find_marker(pptx: Path, slide_number: int, marker: str) -> dict[str, Any]:
    matches = [child for child in slide_children(pptx, slide_number) if marker in str(child.get("text", ""))]
    if len(matches) != 1:
        raise BuildError(f"slide {slide_number}: expected one '{marker}' marker, found {len(matches)}")
    return matches[0]


def parse_length(value: str) -> float:
    match = re.fullmatch(r"\s*(-?[0-9.]+)\s*(emu|cm|pt|in|px)\s*", value, flags=re.IGNORECASE)
    if not match:
        raise BuildError(f"unsupported OfficeCLI length: {value}")
    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "emu":
        return number
    if unit == "cm":
        return number * EMU_PER_CM
    if unit == "pt":
        return number * EMU_PER_PT
    if unit == "in":
        return number * EMU_PER_INCH
    return number * EMU_PER_INCH / 96.0


def contain_frame(format_data: dict[str, Any], image_path: Path) -> dict[str, int]:
    x = parse_length(str(format_data["x"]))
    y = parse_length(str(format_data["y"]))
    width = parse_length(str(format_data["width"]))
    height = parse_length(str(format_data["height"]))
    with Image.open(image_path) as image:
        image_width, image_height = image.size
    if image_width <= 0 or image_height <= 0:
        raise BuildError(f"invalid image dimensions: {image_path}")
    scale = min(width / image_width, height / image_height)
    placed_width = image_width * scale
    placed_height = image_height * scale
    return {
        "x": round(x + (width - placed_width) / 2),
        "y": round(y + (height - placed_height) / 2),
        "width": round(placed_width),
        "height": round(placed_height),
    }


def set_shape_text(
    pptx: Path,
    path: str,
    text: str,
    size: str,
    bold: bool = False,
    align: str | None = None,
) -> None:
    props = [
        "--prop",
        f"text={text}",
        "--prop",
        f"size={size}",
        "--prop",
        "font=Arial",
        "--prop",
        "font.ea=微软雅黑",
        "--prop",
        "autoFit=none",
    ]
    if bold:
        props += ["--prop", "bold=true"]
    if align:
        props += ["--prop", f"align={align}"]
    office(pptx, ["set", path, *props])


def replace_all(pptx: Path, find: str, replace: str) -> None:
    office(pptx, ["set", "/", "--find", find, "--replace", replace])


def replace_fixed_slides(plan: dict[str, Any], plan_base: Path, pptx: Path) -> list[str]:
    project = plan["project"]
    paper = plan["paper"]
    replace_all(pptx, "{{TITLE_CN}}", paper["title_cn"])
    replace_all(pptx, "{{TITLE_EN}}", paper["title_en"])
    replace_all(pptx, "{{Source Year}}", f"{paper['venue']} {paper['year']}")
    if project.get("presenter"):
        replace_all(pptx, "程逸飞", project["presenter"])
    if project.get("advisor"):
        replace_all(pptx, "朱宇佳", project["advisor"])

    contribution_shape = find_marker(pptx, 2, "{{Contributions}}")
    fill_contributions(pptx, contribution_shape["path"], paper["contributions"])

    author_shape = find_marker(pptx, 2, "{{IMG_author}}")
    author_visual = project["author_visual"]
    inserted_assets: list[str] = []
    author_path = resolve_from(plan_base, author_visual)
    if not author_path.is_file():
        raise BuildError(f"author_visual does not exist: {author_path}")
    insert_picture(pptx, 2, author_shape, author_path, "论文作者与机构信息", "PPW_AUTHOR_VISUAL")
    inserted_assets.append(str(author_path))

    one_page_shape = find_marker(pptx, 3, "{{IMG_YY_one_page}}")
    one_page_path = resolve_from(plan_base, project["one_page_image"])
    if not one_page_path.is_file():
        raise BuildError(f"one_page_image does not exist: {one_page_path}")
    insert_picture(pptx, 3, one_page_shape, one_page_path, "论文一页纸总结", "PPW_ONE_PAGE_IMAGE")
    inserted_assets.append(str(one_page_path))
    return inserted_assets


def insert_picture(
    pptx: Path,
    slide_number: int,
    placeholder: dict[str, Any],
    image_path: Path,
    alt_text: str,
    name: str,
) -> None:
    frame = contain_frame(placeholder["format"], image_path)
    office(pptx, ["remove", placeholder["path"]])
    office(
        pptx,
        [
            "add",
            f"/slide[{slide_number}]",
            "--type",
            "picture",
            "--prop",
            f"src={image_path}",
            "--prop",
            f"x={frame['x']}emu",
            "--prop",
            f"y={frame['y']}emu",
            "--prop",
            f"width={frame['width']}emu",
            "--prop",
            f"height={frame['height']}emu",
            "--prop",
            f"name={name}",
            "--prop",
            f"alt={alt_text}",
        ],
    )


def style_body_runs(pptx: Path, body_path: str, body_points: list[dict[str, Any]]) -> None:
    for paragraph_index, point in enumerate(body_points, start=1):
        paragraph_path = f"{body_path}/paragraph[{paragraph_index}]"
        office(pptx, ["set", paragraph_path, "--prop", "color=000000"])
        for run_index, run in enumerate(point.get("runs", [])):
            emphasis = run.get("emphasis")
            if emphasis not in {"bold", "accent"}:
                continue
            props = ["--prop", "bold=true"]
            if emphasis == "accent" and run_index > 0:
                props += ["--prop", "color=194A96"]
            office(pptx, ["set", paragraph_path, "--find", str(run["text"]), *props])


def fill_contributions(pptx: Path, shape_path: str, contributions: list[dict[str, Any]]) -> None:
    paragraph_props = [
        "--prop",
        "list=□",
        "--prop",
        "level=1",
        "--prop",
        "marginLeft=58.5pt",
        "--prop",
        "indent=-22.5pt",
        "--prop",
        "lineSpacing=1.15x",
        "--prop",
        f"size={CONTRIBUTION_SIZE}",
        "--prop",
        "bold=false",
        "--prop",
        "color=000000",
    ]
    for index, contribution in enumerate(contributions, start=2):
        text = "".join(str(run["text"]) for run in contribution["runs"])
        paragraph_path = f"{shape_path}/paragraph[{index}]"
        if index == 2:
            office(pptx, ["set", paragraph_path, "--prop", f"text={text}", *paragraph_props])
        else:
            office(
                pptx,
                ["add", shape_path, "--type", "paragraph", "--prop", f"text={text}", *paragraph_props],
            )
        for run in contribution["runs"]:
            if run.get("emphasis") == "bold":
                office(pptx, ["set", paragraph_path, "--find", str(run["text"]), "--prop", "bold=true"])


def fill_content_slide(
    pptx: Path,
    slide_number: int,
    slide: dict[str, Any],
    plan_base: Path,
) -> str | None:
    title_shape = find_marker(pptx, slide_number, "{{sub_title_en}}")
    body_shape = find_marker(pptx, slide_number, "{{something_en}}")
    visual_shape = find_marker(pptx, slide_number, "{{IMG_padding}}")

    set_shape_text(pptx, title_shape["path"], slide["title"], CONTENT_TITLE_SIZE, bold=True)
    office(pptx, ["set", title_shape["path"], "--prop", "height=2cm"])
    body_points = slide["body"]
    body_text = "\n".join("".join(str(run["text"]) for run in point["runs"]) for point in body_points)
    set_shape_text(pptx, body_shape["path"], body_text, CONTENT_BODY_SIZE)
    office(
        pptx,
        [
            "set",
            body_shape["path"],
            "--prop",
            "y=4.85cm",
            "--prop",
            "height=5.3cm",
            "--prop",
            "lineSpacing=1.15x",
        ],
    )
    style_body_runs(pptx, body_shape["path"], body_points)
    visual = slide["visual"]
    if visual["mode"] == "none":
        office(pptx, ["remove", visual_shape["path"]])
        return None
    asset_path = resolve_from(plan_base, visual["asset_ref"])
    if not asset_path.is_file():
        raise BuildError(f"visual asset does not exist: {asset_path}")
    insert_picture(
        pptx,
        slide_number,
        visual_shape,
        asset_path,
        visual.get("alt_text") or slide["title"],
        f"PPW_VISUAL_{slide['id']}",
    )
    return str(asset_path)


def final_slide_mapping(content: dict[str, list[dict[str, Any]]]) -> list[tuple[int, dict[str, Any]]]:
    mapping: list[tuple[int, dict[str, Any]]] = []
    cursor = 5
    for section in SECTION_ORDER:
        cursor += 1
        for slide in content[section]:
            mapping.append((cursor, slide))
            cursor += 1
    return mapping


def update_page_numbers(pptx: Path, total_slides: int) -> None:
    for slide_number in range(1, total_slides + 1):
        for child in slide_children(pptx, slide_number):
            if child.get("type") == "placeholder" and child.get("format", {}).get("phType") == "slidenum":
                office(pptx, ["set", child["path"], "--prop", f"text={slide_number}"])


def fill_template_picture_alt_text(pptx: Path) -> int:
    """Mark inherited template pictures that do not carry paper content."""
    document = office_query_json(pptx, "picture:no-alt")
    results = document.get("data", {}).get("results", [])
    for result in results:
        office(
            pptx,
            [
                "set",
                str(result["path"]),
                "--prop",
                "alt=模板装饰图形（不承载论文内容）",
            ],
        )
    return len(results)


def build(plan_path: Path, output_override: Path | None = None) -> dict[str, Any]:
    validate_plan(plan_path)
    plan = load_plan(plan_path)
    base = plan_path.resolve().parent
    project = plan["project"]
    template = resolve_from(base, project["template_pptx"])
    output = output_override.resolve() if output_override else resolve_from(base, project["output_pptx"])
    if not template.is_file():
        raise BuildError(f"template does not exist: {template}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, output)

    content = plan_content(plan)
    clone_content_slides(output, content)
    assets = replace_fixed_slides(plan, base, output)
    mapping = final_slide_mapping(content)
    for slide_number, slide in mapping:
        asset = fill_content_slide(output, slide_number, slide, base)
        if asset:
            assets.append(asset)

    total_slides = 4 + 4 + sum(len(slides) for slides in content.values()) + 1
    update_page_numbers(output, total_slides)
    decorative_alt_filled = fill_template_picture_alt_text(output)
    office(output, ["save"])

    validation = office(output, ["validate"])
    issues = office(output, ["view", "issues", "--limit", "200"])
    text_dump = office(output, ["view", "text", "--max-lines", "5000"])
    if "{{" in text_dump.stdout or "}}" in text_dump.stdout:
        raise BuildError("unresolved template placeholder remains in the output deck")
    if "Found 0 issue(s)" not in issues.stdout:
        raise BuildError(f"OfficeCLI reported issues:\n{issues.stdout}")

    report = {
        "builder": "paper-ppt-orchestrator/0.3.0",
        "plan": str(plan_path.resolve()),
        "template": str(template),
        "output": str(output),
        "slides": total_slides,
        "section_content_counts": {section: len(content[section]) for section in SECTION_ORDER},
        "assets": sorted(set(assets)),
        "template_pictures_alt_filled": decorative_alt_filled,
        "validation": validation.stdout.strip(),
        "issues": issues.stdout.strip(),
    }
    report_path = output.with_suffix(".build.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        report = build(args.plan.resolve(), args.output)
    except (BuildError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Built: {report['output']}")
    print(f"Slides: {report['slides']}")
    print(f"Report: {report['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
