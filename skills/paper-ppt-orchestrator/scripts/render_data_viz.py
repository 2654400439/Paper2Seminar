#!/usr/bin/env python3
"""Render a constrained paper-data visualization to a slide-ready PNG."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.text import Text
from PIL import Image


PRIMARY = "#194A96"
SECONDARY = "#86A8D5"
ACCENT = "#D97706"
PALETTE = [PRIMARY, SECONDARY, ACCENT]
TEXT = "#222222"
MUTED = "#6B7280"
GRID = "#D9DEE7"
LIGHT = "#F2F5F9"
ALLOWED_TYPES = {
    "bar",
    "horizontal_bar",
    "grouped_bar",
    "line",
    "dot_plot",
    "heatmap",
    "compact_table",
}


class SpecError(ValueError):
    pass


def choose_font() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial", "DejaVu Sans"):
        if candidate in available:
            return candidate
    return "DejaVu Sans"


def load_spec(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict):
        raise SpecError("top-level JSON value must be an object")
    return spec


def require_string(spec: dict[str, Any], key: str, allow_empty: bool = True) -> str:
    value = spec.get(key, "")
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SpecError(f"'{key}' must be a string")
    return value.strip()


def validate_spec(spec: dict[str, Any]) -> None:
    if spec.get("version") != "0.1":
        raise SpecError("version must equal '0.1'")
    chart_type = spec.get("chart_type")
    if chart_type not in ALLOWED_TYPES:
        raise SpecError(f"unsupported chart_type: {chart_type}")

    output = spec.get("output")
    if not isinstance(output, dict):
        raise SpecError("output must be an object")
    width = output.get("width_px")
    height = output.get("height_px")
    dpi = output.get("dpi")
    if not isinstance(width, int) or not 1600 <= width <= 4800:
        raise SpecError("output.width_px must be between 1600 and 4800")
    if not isinstance(height, int) or not 600 <= height <= 2400:
        raise SpecError("output.height_px must be between 600 and 2400")
    if not isinstance(dpi, int) or not 100 <= dpi <= 300:
        raise SpecError("output.dpi must be between 100 and 300")
    ratio = width / height
    if not 2.1 <= ratio <= 2.7:
        raise SpecError("output aspect ratio must be between 2.1:1 and 2.7:1")
    if output.get("background") not in {"white", "transparent"}:
        raise SpecError("output.background must be white or transparent")

    if chart_type == "compact_table":
        table = spec.get("table")
        if not isinstance(table, dict):
            raise SpecError("compact_table requires table")
        columns = table.get("columns")
        rows = table.get("rows")
        if not isinstance(columns, list) or not 2 <= len(columns) <= 5:
            raise SpecError("table.columns must contain 2-5 labels")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 6:
            raise SpecError("table.rows must contain 1-6 rows")
        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(columns):
                raise SpecError(f"table row {index} does not match the column count")
        numeric_points = sum(isinstance(value, (int, float)) for row in rows for value in row)
        if numeric_points < 2:
            raise SpecError("compact_table needs at least two numeric values; keep a lone value as slide text")
        return

    categories = spec.get("categories")
    series = spec.get("series")
    if not isinstance(categories, list) or not 1 <= len(categories) <= 8:
        raise SpecError("categories must contain 1-8 labels")
    if not all(isinstance(item, str) and item.strip() for item in categories):
        raise SpecError("every category must be a non-empty string")
    if not isinstance(series, list) or not 1 <= len(series) <= 3:
        raise SpecError("series must contain 1-3 series")
    for index, item in enumerate(series):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise SpecError(f"series {index} needs a name")
        values = item.get("values")
        if not isinstance(values, list) or len(values) != len(categories):
            raise SpecError(f"series {index} values must match category count")
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise SpecError(f"series {index} contains a non-finite numeric value")
    if sum(len(item["values"]) for item in series) < 2:
        raise SpecError("data redraw needs at least two comparable points; keep a lone value as slide text")
    if chart_type == "bar" and len(series) != 1:
        raise SpecError("bar accepts exactly one series; use grouped_bar for multiple series")


def value_label(value: float, decimals: int, unit: str) -> str:
    text = f"{value:.{decimals}f}"
    return f"{text}{unit}" if unit else text


def style_axis(ax: plt.Axes, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=15)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)


def place_legend(ax: plt.Axes, columns: int) -> None:
    """Keep multi-series legends out of the data region."""
    ax.legend(
        frameon=False,
        fontsize=14,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=max(1, columns),
        borderaxespad=0,
    )


def render_bar(ax: plt.Axes, spec: dict[str, Any], horizontal: bool = False) -> None:
    categories = spec["categories"]
    series = spec["series"]
    decimals = int(spec.get("value_decimals", 1))
    unit = require_string(spec, "unit")
    positions = np.arange(len(categories))
    count = len(series)
    span = 0.72
    bar_width = span / count
    for index, item in enumerate(series):
        values = np.asarray(item["values"], dtype=float)
        offset = (index - (count - 1) / 2) * bar_width
        color = PALETTE[index]
        if horizontal:
            bars = ax.barh(positions + offset, values, height=bar_width * 0.88, color=color, label=item["name"])
            if spec.get("show_values", True):
                ax.bar_label(bars, labels=[value_label(v, decimals, unit) for v in values], padding=8, fontsize=15, color=TEXT)
        else:
            bars = ax.bar(positions + offset, values, width=bar_width * 0.88, color=color, label=item["name"])
            if spec.get("show_values", True):
                ax.bar_label(bars, labels=[value_label(v, decimals, unit) for v in values], padding=5, fontsize=14, color=TEXT)
    if horizontal:
        ax.set_yticks(positions, categories)
        ax.invert_yaxis()
        style_axis(ax, "x")
    else:
        ax.set_xticks(positions, categories)
        style_axis(ax, "y")
    if count > 1:
        place_legend(ax, count)


def render_line(ax: plt.Axes, spec: dict[str, Any]) -> None:
    positions = np.arange(len(spec["categories"]))
    for index, item in enumerate(spec["series"]):
        ax.plot(
            positions,
            item["values"],
            marker="o",
            linewidth=3,
            markersize=8,
            color=PALETTE[index],
            label=item["name"],
        )
    ax.set_xticks(positions, spec["categories"])
    style_axis(ax, "y")
    if len(spec["series"]) > 1:
        place_legend(ax, len(spec["series"]))


def render_dot(ax: plt.Axes, spec: dict[str, Any]) -> None:
    categories = spec["categories"]
    positions = np.arange(len(categories))
    count = len(spec["series"])
    for index, item in enumerate(spec["series"]):
        offset = (index - (count - 1) / 2) * 0.16
        ax.scatter(item["values"], positions + offset, s=130, color=PALETTE[index], label=item["name"], zorder=3)
    ax.set_yticks(positions, categories)
    ax.invert_yaxis()
    style_axis(ax, "x")
    if count > 1:
        place_legend(ax, count)


def render_heatmap(ax: plt.Axes, spec: dict[str, Any]) -> None:
    values = np.asarray([item["values"] for item in spec["series"]], dtype=float)
    cmap = LinearSegmentedColormap.from_list("ppw", ["#EEF3FA", "#7FA6D8", PRIMARY])
    image = ax.imshow(values, cmap=cmap, aspect="auto")
    ax.set_xticks(np.arange(len(spec["categories"])), spec["categories"])
    ax.set_yticks(np.arange(len(spec["series"])), [item["name"] for item in spec["series"]])
    decimals = int(spec.get("value_decimals", 1))
    unit = require_string(spec, "unit")
    midpoint = (values.min() + values.max()) / 2
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            color = "white" if values[row, column] > midpoint else TEXT
            ax.text(column, row, value_label(values[row, column], decimals, unit), ha="center", va="center", color=color, fontsize=14)
    ax.tick_params(length=0, labelsize=14)
    for spine in ax.spines.values():
        spine.set_visible(False)
    image.set_clim(values.min(), values.max())


def render_table(ax: plt.Axes, spec: dict[str, Any]) -> None:
    table_spec = spec["table"]
    columns = [str(value) for value in table_spec["columns"]]
    rows = [[str(value) for value in row] for row in table_spec["rows"]]
    highlights = set(table_spec.get("highlight_rows", []))
    colors = [["#E8F0FA" if index in highlights else "white" for _ in columns] for index, _ in enumerate(rows)]
    table = ax.table(
        cellText=rows,
        colLabels=columns,
        cellColours=colors,
        colColours=[PRIMARY] * len(columns),
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.01, 0.02, 0.98, 0.94],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(15)
    for (row, _column), cell in table.get_celld().items():
        cell.set_edgecolor("#D7DEE8")
        cell.set_linewidth(0.8)
        if row == 0:
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        elif row - 1 in highlights:
            cell.get_text().set_weight("bold")
            cell.get_text().set_color(PRIMARY)
    ax.axis("off")


def apply_labels(ax: plt.Axes, spec: dict[str, Any]) -> None:
    x_label = require_string(spec, "x_label")
    y_label = require_string(spec, "y_label")
    if x_label:
        ax.set_xlabel(x_label, fontsize=16, color=TEXT, labelpad=10)
    if y_label:
        ax.set_ylabel(y_label, fontsize=16, color=TEXT, labelpad=10)


def text_overflow(fig: plt.Figure) -> list[str]:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    figure_box = fig.bbox
    warnings: list[str] = []
    for text in fig.findobj(match=Text):
        content = text.get_text()
        if not text.get_visible() or not content.strip():
            continue
        box = text.get_window_extent(renderer=renderer)
        if box.x1 < figure_box.x0 or box.y1 < figure_box.y0 or box.x0 > figure_box.x1 or box.y0 > figure_box.y1:
            continue
        if box.x0 < figure_box.x0 - 2 or box.y0 < figure_box.y0 - 2 or box.x1 > figure_box.x1 + 2 or box.y1 > figure_box.y1 + 2:
            warnings.append(f"text outside canvas: {content[:60]}")
    return warnings


def render(spec: dict[str, Any], output_path: Path) -> dict[str, Any]:
    validate_spec(spec)
    output = spec["output"]
    width = output["width_px"]
    height = output["height_px"]
    dpi = output["dpi"]
    transparent = output["background"] == "transparent"
    font = choose_font()
    plt.rcParams.update(
        {
            "font.family": font,
            "axes.unicode_minus": False,
            "text.color": TEXT,
            "axes.labelcolor": TEXT,
        }
    )
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi, layout="constrained")
    fig.patch.set_alpha(0 if transparent else 1)
    ax.set_facecolor("none" if transparent else "white")

    chart_type = spec["chart_type"]
    if chart_type == "bar":
        render_bar(ax, spec, horizontal=False)
    elif chart_type == "horizontal_bar":
        render_bar(ax, spec, horizontal=True)
    elif chart_type == "grouped_bar":
        render_bar(ax, spec, horizontal=False)
    elif chart_type == "line":
        render_line(ax, spec)
    elif chart_type == "dot_plot":
        render_dot(ax, spec)
    elif chart_type == "heatmap":
        render_heatmap(ax, spec)
    else:
        render_table(ax, spec)

    if chart_type != "compact_table":
        apply_labels(ax, spec)
    title = require_string(spec, "title")
    if title:
        fig.suptitle(title, fontsize=20, fontweight="bold", color=PRIMARY)

    warnings = text_overflow(fig)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_path,
        dpi=dpi,
        transparent=transparent,
        facecolor="none" if transparent else "white",
        bbox_inches=None,
        pad_inches=0,
    )
    plt.close(fig)

    with Image.open(output_path) as image:
        if image.size != (width, height):
            raise SpecError(f"renderer produced {image.size}, expected {(width, height)}")
        extrema = image.convert("RGB").getextrema()
        if all(low == high for low, high in extrema):
            raise SpecError("renderer produced a blank image")

    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "renderer": "PaperEvidenceViz/0.1",
        "matplotlib": matplotlib.__version__,
        "font": font,
        "chart_type": chart_type,
        "width_px": width,
        "height_px": height,
        "sha256": digest,
        "source_hint": spec.get("source_hint", {}),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.spec.with_suffix(".png")
    try:
        spec = load_spec(args.spec)
        manifest = render(spec, output)
    except (OSError, json.JSONDecodeError, SpecError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rendered: {output}")
    print(f"Manifest: {manifest_path}")
    if manifest["warnings"]:
        print(f"Warnings: {len(manifest['warnings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
