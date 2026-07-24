#!/usr/bin/env python3
"""Render the bilingual README workflow animation as deterministic GIF assets."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1200
HEIGHT = 560
SCALE = 2
FPS_DURATION_MS = 80
FORWARD_FRAMES = 60
RESET_FRAMES = 12
TOTAL_FRAMES = FORWARD_FRAMES + RESET_FRAMES

INK = "#172033"
MUTED = "#667085"
FAINT = "#98A2B3"
SURFACE = "#FFFFFF"
BACKGROUND = "#F5F7FA"
GRID = "#E4E7EC"
RAIL = "#D0D5DD"
STAGES = (
    {"code": "READ", "accent": "#2457C5", "icon": "document", "maximum": 14},
    {"code": "PLAN", "accent": "#0F766E", "icon": "matrix", "maximum": 32},
    {"code": "ROUTE", "accent": "#B45309", "icon": "route", "maximum": 12},
    {"code": "BUILD", "accent": "#B33A3A", "icon": "slide", "maximum": 96},
    {"code": "QA", "accent": "#18794E", "icon": "shield", "maximum": 3},
)

COPY = {
    "zh": {
        "title": "从论文证据到可编辑组会 PPT",
        "eyebrow": "PAPER2SEMINAR / 受控证据流水线",
        "principle": "证据优先  ·  确定性组装  ·  审批可追溯",
        "stage": "阶段",
        "active": "处理中",
        "complete": "已锁定",
        "queued": "等待中",
        "iterate": "下一轮迭代",
        "trace": "实时轨迹",
        "stages": (
            ("全文理解", ("读取全文与附录", "提取章节、结论与限制"), "正在核对章节与论文主张", "章节"),
            ("覆盖规划", ("映射方法小节与实验", "按复杂度确定页数"), "正在建立小节覆盖矩阵", "页"),
            ("视觉路由", ("论文原图 / TikZ / 重绘", "证据优先，概念图受控"), "正在为每页选择可信视觉", "资产"),
            ("可编辑组装", ("固定模板确定性装配", "文字、图形与讲稿可编辑"), "正在写入可编辑 PPTX 对象", "对象"),
            ("多阶段 QA", ("资产、页面与结构检查", "审批状态全程可追溯"), "正在执行最终质量门禁", "门禁"),
        ),
        "reset_message": "QA 结论回流到下一轮内容修订",
        "output_ready": "PRESENTATION.PPTX / 已通过",
    },
    "en": {
        "title": "From paper evidence to an editable seminar deck",
        "eyebrow": "PAPER2SEMINAR / CONTROLLED EVIDENCE PIPELINE",
        "principle": "EVIDENCE FIRST  ·  DETERMINISTIC BUILD  ·  AUDITABLE APPROVAL",
        "stage": "STAGE",
        "active": "ACTIVE",
        "complete": "LOCKED",
        "queued": "QUEUED",
        "iterate": "NEXT ITERATION",
        "trace": "LIVE TRACE",
        "stages": (
            ("Full-paper\nreading", ("Read sections + appendix", "Extract claims, results, limits"), "Verifying sections and paper claims", "sections"),
            ("Coverage\nplanning", ("Map methods and experiments", "Budget slides by complexity"), "Building the subsection coverage map", "slides"),
            ("Visual routing", ("Paper / TikZ / exact redraw", "Keep concept visuals controlled"), "Selecting a truthful visual for each slide", "assets"),
            ("Editable\nassembly", ("Assemble from a fixed template", "Keep every object editable"), "Writing editable objects into PPTX", "objects"),
            ("Multi-stage\nQA", ("Review assets, slides, structure", "Keep approvals auditable"), "Running the final quality gates", "gates"),
        ),
        "reset_message": "QA evidence feeds the next content revision",
        "output_ready": "PRESENTATION.PPTX / APPROVED",
    },
}


def scaled_box(values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(round(value * SCALE) for value in values)  # type: ignore[return-value]


def scaled_points(values: list[tuple[float, float]]) -> list[tuple[int, int]]:
    return [(round(x * SCALE), round(y * SCALE)) for x, y in values]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    windows = Path("C:/Windows/Fonts")
    candidates = (
        [windows / "msyhbd.ttc", windows / "seguisb.ttf", windows / "arialbd.ttf"]
        if bold
        else [windows / "msyh.ttc", windows / "segoeui.ttf", windows / "arial.ttf"]
    )
    candidates += [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size * SCALE)
    raise RuntimeError("No suitable TrueType font found for README animation")
def blend(first: str, second: str, amount: float) -> str:
    first_rgb = tuple(int(first[index : index + 2], 16) for index in (1, 3, 5))
    second_rgb = tuple(int(second[index : index + 2], 16) for index in (1, 3, 5))
    values = [round(a + (b - a) * amount) for a, b in zip(first_rgb, second_rgb)]
    return "#" + "".join(f"{value:02X}" for value in values)


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    value: str,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    anchor: str | None = None,
) -> None:
    draw.text(
        (round(position[0] * SCALE), round(position[1] * SCALE)),
        value,
        font=font,
        fill=fill,
        anchor=anchor,
    )


def draw_icon(draw: ImageDraw.ImageDraw, icon: str, x: float, y: float, color: str) -> None:
    width = 2 * SCALE
    if icon == "document":
        draw.rounded_rectangle(scaled_box((x + 5, y + 1, x + 35, y + 41)), radius=4 * SCALE, outline=color, width=width)
        draw.line(scaled_points([(x + 13, y + 12), (x + 28, y + 12)]), fill=color, width=width)
        draw.line(scaled_points([(x + 13, y + 20), (x + 29, y + 20)]), fill=color, width=width)
        draw.line(scaled_points([(x + 13, y + 28), (x + 24, y + 28)]), fill=color, width=width)
    elif icon == "matrix":
        for row in range(3):
            for column in range(3):
                left = x + 3 + column * 13
                top = y + 3 + row * 13
                fill = color if (row, column) in {(0, 0), (1, 1), (2, 1)} else None
                draw.rounded_rectangle(
                    scaled_box((left, top, left + 9, top + 9)),
                    radius=2 * SCALE,
                    outline=color,
                    fill=fill,
                    width=width,
                )
    elif icon == "route":
        nodes = [(x + 5, y + 21), (x + 22, y + 8), (x + 37, y + 8), (x + 22, y + 34), (x + 37, y + 34)]
        for end in nodes[1:]:
            draw.line(scaled_points([nodes[0], end]), fill=color, width=width)
        for index, (node_x, node_y) in enumerate(nodes):
            radius = 5 if index == 0 else 4
            draw.ellipse(scaled_box((node_x - radius, node_y - radius, node_x + radius, node_y + radius)), fill=color)
    elif icon == "slide":
        draw.rounded_rectangle(scaled_box((x + 1, y + 5, x + 41, y + 35)), radius=3 * SCALE, outline=color, width=width)
        draw.rectangle(scaled_box((x + 7, y + 11, x + 20, y + 29)), fill=color)
        draw.line(scaled_points([(x + 25, y + 13), (x + 35, y + 13)]), fill=color, width=width)
        draw.line(scaled_points([(x + 25, y + 20), (x + 35, y + 20)]), fill=color, width=width)
        draw.line(scaled_points([(x + 25, y + 27), (x + 32, y + 27)]), fill=color, width=width)
        draw.line(scaled_points([(x + 21, y + 35), (x + 21, y + 41)]), fill=color, width=width)
    elif icon == "shield":
        polygon = [(x + 21, y + 1), (x + 38, y + 8), (x + 35, y + 28), (x + 21, y + 41), (x + 7, y + 28), (x + 4, y + 8)]
        draw.polygon(scaled_points(polygon), outline=color)
        draw.line(scaled_points([(x + 13, y + 21), (x + 19, y + 27), (x + 30, y + 15)]), fill=color, width=3 * SCALE, joint="curve")


def active_stage(frame_index: int) -> tuple[int, int, bool]:
    if frame_index < FORWARD_FRAMES:
        return min(4, frame_index // 12), frame_index % 12, False
    return 4, frame_index - FORWARD_FRAMES, True


def packet_position(frame_index: int, centers: list[float], rail_y: float) -> tuple[float, float, float]:
    stage_index, local, resetting = active_stage(frame_index)
    if resetting:
        progress = ease(local / (RESET_FRAMES - 1))
        x = centers[-1] + (centers[0] - centers[-1]) * progress
        y = rail_y - math.sin(math.pi * progress) * 310
        return x, y, 1.0
    if stage_index < 4 and local >= 8:
        progress = ease((local - 8) / 4)
        return centers[stage_index] + (centers[stage_index + 1] - centers[stage_index]) * progress, rail_y, 1.0
    return centers[stage_index], rail_y, 1.0


def draw_card(
    draw: ImageDraw.ImageDraw,
    copy: dict[str, object],
    stage_index: int,
    current_stage: int,
    local_frame: int,
    resetting: bool,
    card: tuple[float, float, float, float],
) -> None:
    stage = STAGES[stage_index]
    title, description, _message, unit = copy["stages"][stage_index]  # type: ignore[index]
    accent = str(stage["accent"])
    is_complete = stage_index < current_stage or resetting
    is_active = stage_index == current_stage and not resetting
    border = accent if is_active else (blend(accent, SURFACE, 0.48) if is_complete else RAIL)
    x0, y0, x1, y1 = card

    draw.rounded_rectangle(
        scaled_box((x0 + 2, y0 + 4, x1 + 2, y1 + 5)),
        radius=8 * SCALE,
        fill="#E4E7EC",
    )
    draw.rounded_rectangle(
        scaled_box(card),
        radius=8 * SCALE,
        fill=SURFACE,
        outline=border,
        width=(3 if is_active else 1) * SCALE,
    )
    if is_active:
        draw.rectangle(scaled_box((x0, y0, x1, y0 + 5)), fill=accent)

    small = load_font(10, bold=True)
    title_lines = str(title).split("\n")
    title_font = load_font(15 if len(title_lines) > 1 else 17, bold=True)
    body_font = load_font(11)
    metric_font = load_font(11, bold=True)
    draw_text(draw, (x0 + 15, y0 + 18), f"{stage_index + 1:02d} / {stage['code']}", small, accent if is_active or is_complete else MUTED)

    icon_color = accent if is_active or is_complete else FAINT
    draw_icon(draw, str(stage["icon"]), x0 + 15, y0 + 49, icon_color)
    title_y = y0 + (48 if len(title_lines) > 1 else 55)
    for line_index, line in enumerate(title_lines):
        draw_text(draw, (x0 + 66, title_y + line_index * 19), line, title_font, INK)
    for line_index, line in enumerate(description):
        draw_text(draw, (x0 + 15, y0 + 113 + line_index * 22), str(line), body_font, MUTED)

    if is_active:
        state_label = str(copy["active"])
        state_fill = blend(accent, SURFACE, 0.88)
        state_text = accent
        progress = min(1.0, (local_frame + 1) / 8)
        value = max(1, round(float(stage["maximum"]) * progress))
    elif is_complete:
        state_label = str(copy["complete"])
        state_fill = blend(accent, SURFACE, 0.9)
        state_text = accent
        progress = 1.0
        value = int(stage["maximum"])
    else:
        state_label = str(copy["queued"])
        state_fill = "#F2F4F7"
        state_text = MUTED
        progress = 0.0
        value = 0

    tag_box = (x0 + 15, y0 + 172, x0 + 78, y0 + 196)
    draw.rounded_rectangle(scaled_box(tag_box), radius=5 * SCALE, fill=state_fill)
    draw_text(draw, ((tag_box[0] + tag_box[2]) / 2, tag_box[1] + 12), state_label, small, state_text, anchor="mm")
    metric = f"{value} / {stage['maximum']} {str(unit).upper()}" if stage_index in {0, 4} else f"{value} {str(unit).upper()}"
    draw_text(draw, (x1 - 15, y0 + 184), metric, metric_font, INK if is_active else MUTED, anchor="rm")

    draw.rounded_rectangle(scaled_box((x0 + 15, y1 - 24, x1 - 15, y1 - 18)), radius=3 * SCALE, fill="#EAECF0")
    if progress > 0:
        draw.rounded_rectangle(
            scaled_box((x0 + 15, y1 - 24, x0 + 15 + (x1 - x0 - 30) * progress, y1 - 18)),
            radius=3 * SCALE,
            fill=accent,
        )

    if is_complete:
        check_x, check_y = x1 - 20, y0 + 21
        draw.ellipse(scaled_box((check_x - 8, check_y - 8, check_x + 8, check_y + 8)), fill=accent)
        draw.line(
            scaled_points([(check_x - 4, check_y), (check_x - 1, check_y + 3), (check_x + 5, check_y - 4)]),
            fill="white",
            width=2 * SCALE,
            joint="curve",
        )


def render_frame(language: str, frame_index: int) -> Image.Image:
    copy = COPY[language]
    canvas = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    for x in range(24, WIDTH, 32):
        for y in range(20, HEIGHT, 32):
            draw.ellipse(scaled_box((x, y, x + 1.5, y + 1.5)), fill=GRID)

    stage_index, local_frame, resetting = active_stage(frame_index)
    accent = str(STAGES[stage_index]["accent"])
    eyebrow_font = load_font(10, bold=True)
    header_font = load_font(27, bold=True)
    principle_font = load_font(10, bold=True)
    status_font = load_font(10, bold=True)

    draw_text(draw, (40, 24), str(copy["eyebrow"]), eyebrow_font, MUTED)
    draw_text(draw, (40, 48), str(copy["title"]), header_font, INK)
    draw_text(draw, (40, 91), str(copy["principle"]), principle_font, MUTED)

    header_label = str(copy["iterate"]) if resetting else f"{copy['stage']} {stage_index + 1} / 5"
    header_box = (1000, 28, 1160, 60)
    draw.rounded_rectangle(scaled_box(header_box), radius=6 * SCALE, fill=blend(accent, SURFACE, 0.9), outline=accent, width=SCALE)
    draw_text(draw, ((header_box[0] + header_box[2]) / 2, (header_box[1] + header_box[3]) / 2), header_label, status_font, accent, anchor="mm")

    margin = 40
    card_width = 188
    card_gap = 45
    card_top = 128
    card_bottom = 394
    centers = [margin + card_width / 2 + index * (card_width + card_gap) for index in range(5)]
    rail_y = 430

    draw.line(scaled_points([(centers[0], rail_y), (centers[-1], rail_y)]), fill=RAIL, width=3 * SCALE)
    packet_x, packet_y, _opacity = packet_position(frame_index, centers, rail_y)
    if not resetting:
        draw.line(scaled_points([(centers[0], rail_y), (packet_x, rail_y)]), fill=accent, width=3 * SCALE)

    for index, center in enumerate(centers):
        state_color = str(STAGES[index]["accent"]) if index <= stage_index or resetting else RAIL
        draw.line(scaled_points([(center, card_bottom), (center, rail_y)]), fill=state_color, width=2 * SCALE)
        draw.ellipse(scaled_box((center - 4, rail_y - 4, center + 4, rail_y + 4)), fill=state_color)

    for index in range(5):
        x0 = margin + index * (card_width + card_gap)
        draw_card(
            draw,
            copy,
            index,
            stage_index,
            local_frame,
            resetting,
            (x0, card_top, x0 + card_width, card_bottom),
        )

    trail_color = blend(accent, BACKGROUND, 0.55)
    for offset, radius in ((3, 5), (6, 4), (9, 3)):
        previous_frame = max(0, frame_index - offset)
        previous_x, previous_y, _ = packet_position(previous_frame, centers, rail_y)
        draw.ellipse(scaled_box((previous_x - radius, previous_y - radius, previous_x + radius, previous_y + radius)), fill=trail_color)
    draw.ellipse(scaled_box((packet_x - 9, packet_y - 9, packet_x + 9, packet_y + 9)), fill=blend(accent, SURFACE, 0.72))
    draw.ellipse(scaled_box((packet_x - 5, packet_y - 5, packet_x + 5, packet_y + 5)), fill=accent)
    draw.ellipse(scaled_box((packet_x - 1.5, packet_y - 2.5, packet_x + 1.5, packet_y + 0.5)), fill="white")

    trace_font = load_font(10, bold=True)
    message_font = load_font(13, bold=True)
    output_font = load_font(10, bold=True)
    current_message = str(copy["reset_message"] if resetting else copy["stages"][stage_index][2])  # type: ignore[index]
    draw.rectangle(scaled_box((40, 484, 44, 525)), fill=accent)
    draw_text(draw, (58, 486), str(copy["trace"]), trace_font, accent)
    draw_text(draw, (58, 505), current_message, message_font, INK)

    if stage_index == 4 or resetting:
        output_label = str(copy["output_ready"])
        output_color = str(STAGES[4]["accent"])
        output_fill = blend(output_color, SURFACE, 0.9)
    else:
        next_code = str(STAGES[stage_index + 1]["code"])
        output_label = f"NEXT / {next_code}"
        output_color = MUTED
        output_fill = "#EAECF0"
    output_box = (932, 487, 1160, 522)
    draw.rounded_rectangle(scaled_box(output_box), radius=6 * SCALE, fill=output_fill, outline=output_color, width=SCALE)
    draw_text(draw, ((output_box[0] + output_box[2]) / 2, (output_box[1] + output_box[3]) / 2), output_label, output_font, output_color, anchor="mm")

    return canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def render_animation(language: str, output: Path, preview_dir: Path | None = None) -> dict[str, object]:
    frames = [render_frame(language, index) for index in range(TOTAL_FRAMES)]
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=FPS_DURATION_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    if preview_dir:
        preview_dir.mkdir(parents=True, exist_ok=True)
        for frame_index in (0, 18, 42, 59, 65, 71):
            frames[frame_index].save(preview_dir / f"{language}-frame-{frame_index:02d}.png", optimize=True)
    return {
        "language": language,
        "output": str(output.resolve()),
        "frames": TOTAL_FRAMES,
        "duration_seconds": round(TOTAL_FRAMES * FPS_DURATION_MS / 1000, 2),
        "width": WIDTH,
        "height": HEIGHT,
        "bytes": output.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("zh", "en", "both"), default="both")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "assets")
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()
    languages = ("zh", "en") if args.language == "both" else (args.language,)
    filenames = {"zh": "workflow-pipeline.zh-CN.gif", "en": "workflow-pipeline.en.gif"}
    for language in languages:
        result = render_animation(language, args.output_dir / filenames[language], args.preview_dir)
        print(
            f"{result['language']}: {result['output']} | {result['frames']} frames | "
            f"{result['duration_seconds']}s | {result['bytes']} bytes"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
