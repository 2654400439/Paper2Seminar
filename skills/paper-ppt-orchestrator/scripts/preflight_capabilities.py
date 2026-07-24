#!/usr/bin/env python3
"""Inspect host tools and record agent-visible media capabilities."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from render_one_page_html import browser_candidates, browser_version


DECLARED_STATES = ("available", "unavailable", "unknown")


def command_version(path: str | Path, arguments: tuple[str, ...] = ("--version",)) -> str:
    try:
        completed = subprocess.run(
            [str(path), *arguments],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    payload = completed.stdout.strip() or completed.stderr.strip()
    lines = [
        line.strip()
        for line in payload.splitlines()
        if line.strip() and " INFO " not in line and " ERROR " not in line
    ]
    return (lines[0] if lines else "unknown")[:300]


def executable_record(
    names: tuple[str, ...],
    version_arguments: tuple[str, ...] = ("--version",),
) -> dict[str, Any]:
    for name in names:
        path = shutil.which(name)
        if path:
            return {
                "status": "available",
                "path": str(Path(path).resolve()),
                "version": command_version(path, version_arguments),
            }
    return {"status": "unavailable", "path": None, "version": None}


def module_record(name: str) -> dict[str, Any]:
    return {"status": "available" if importlib.util.find_spec(name) else "unavailable"}


def find_powerpoint() -> Path | None:
    direct = shutil.which("POWERPNT") or shutil.which("POWERPNT.EXE")
    if direct:
        return Path(direct).resolve()
    if platform.system() != "Windows":
        return None
    roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")]
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "Microsoft Office" / "root" / "Office16" / "POWERPNT.EXE"
        if candidate.is_file():
            return candidate.resolve()
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\POWERPNT.EXE",
        ) as key:
            value, _ = winreg.QueryValueEx(key, None)
            candidate = Path(value)
            return candidate.resolve() if candidate.is_file() else None
    except (ImportError, FileNotFoundError, OSError):
        return None


def choose_conceptual_mode(imagegen: str, web_search: str) -> dict[str, str]:
    if imagegen == "available":
        return {
            "selected": "imagegen",
            "reason": "image generation was declared available",
        }
    if imagegen == "unavailable" and web_search == "available":
        return {
            "selected": "external_image",
            "reason": "image generation is unavailable and licensed image search is available",
        }
    if imagegen == "unavailable" and web_search == "unavailable":
        return {
            "selected": "tikz_or_none",
            "reason": "neither image generation nor web image search is available",
        }
    return {
        "selected": "unresolved",
        "reason": "declare imagegen and web-search capability before visual routing",
    }


def build_report(imagegen: str, web_search: str) -> dict[str, Any]:
    browsers = browser_candidates()
    powerpoint = find_powerpoint()
    warnings: list[str] = []
    if not browsers:
        warnings.append("No Chromium-family browser was found; fixed one-page rendering is unavailable.")
    if platform.system() == "Windows" and powerpoint is None:
        warnings.append("PowerPoint was not found; use LibreOffice or OfficeCLI for slide rendering.")
    if imagegen == "unknown" or web_search == "unknown":
        warnings.append("Agent-only media capabilities remain unknown; do not retry blindly before declaring them.")

    return {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "executable": sys.executable,
        },
        "agent_declared": {
            "imagegen": imagegen,
            "web_search": web_search,
        },
        "routing": {
            "conceptual_visual": choose_conceptual_mode(imagegen, web_search),
            "fallback_order": ["imagegen", "external_image", "tikz_or_none"],
        },
        "tools": {
            "browsers": [
                {"path": str(browser), "version": browser_version(browser)} for browser in browsers
            ],
            "officecli": executable_record(("officecli",)),
            "xelatex": executable_record(("xelatex",)),
            "pdftoppm": executable_record(("pdftoppm",), ("-v",)),
            "libreoffice": executable_record(("libreoffice", "soffice")),
            "powershell_7": executable_record(("pwsh",)),
            "windows_powershell": executable_record(
                ("powershell", "powershell.exe"),
                ("-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"),
            ),
            "powerpoint": {
                "status": "installed" if powerpoint else "unavailable",
                "path": str(powerpoint) if powerpoint else None,
                "runtime_access": "not_probed",
            },
        },
        "python_modules": {
            name: module_record(name) for name in ("fitz", "PIL", "matplotlib", "jsonschema")
        },
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--imagegen", choices=DECLARED_STATES, default="unknown")
    parser.add_argument("--web-search", choices=DECLARED_STATES, default="unknown")
    args = parser.parse_args()
    report = build_report(args.imagegen, args.web_search)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Capability report: {args.output.resolve()}")
    else:
        print(payload)
    selected = report["routing"]["conceptual_visual"]["selected"]
    print(f"Conceptual visual route: {selected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
