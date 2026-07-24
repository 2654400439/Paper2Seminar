#!/usr/bin/env python3
"""Render the bundled one-page HTML template to a tightly cropped PNG."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops


REQUIRED_LABELS = ["问题归类", "威胁模型", "边界与局限", "组内启发", "算法学习"]
BROWSER_COMMANDS = (
    "msedge",
    "microsoft-edge",
    "microsoft-edge-stable",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)


class RenderError(RuntimeError):
    pass


def _append_candidate(candidates: list[Path], value: str | Path | None) -> None:
    if not value:
        return
    path = Path(value).expanduser()
    if path.is_file():
        resolved = path.resolve()
        if resolved not in candidates:
            candidates.append(resolved)


def browser_candidates(override: Path | None = None) -> list[Path]:
    if override:
        browser = override.resolve()
        if browser.is_file():
            return [browser]
        raise RenderError(f"browser executable does not exist: {browser}")

    candidates: list[Path] = []
    for variable in ("PAPER_PPT_BROWSER", "CHROME_PATH", "EDGE_PATH"):
        _append_candidate(candidates, os.environ.get(variable))
    for command in BROWSER_COMMANDS:
        _append_candidate(candidates, shutil.which(command))

    system = platform.system()
    if system == "Windows":
        roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        relative_paths = (
            "Microsoft/Edge/Application/msedge.exe",
            "Google/Chrome/Application/chrome.exe",
            "Chromium/Application/chrome.exe",
        )
        for root in roots:
            if root:
                for relative in relative_paths:
                    _append_candidate(candidates, Path(root) / relative)
    elif system == "Darwin":
        for candidate in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ):
            _append_candidate(candidates, candidate)
    else:
        for candidate in (
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/microsoft-edge",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ):
            _append_candidate(candidates, candidate)
    return candidates


def find_browser(override: Path | None) -> Path:
    candidates = browser_candidates(override)
    if candidates:
        return candidates[0]
    raise RenderError(
        "no Chromium-family browser found; set PAPER_PPT_BROWSER or pass --browser"
    )


def browser_version(browser: Path) -> str:
    try:
        completed = subprocess.run(
            [str(browser), "--version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    combined = "\n".join((completed.stdout, completed.stderr))
    for line in combined.splitlines():
        if "ERROR:" not in line and re.search(r"(?:Chrome|Chromium|Edge).*[0-9]+\.[0-9]+", line):
            return line.strip()[:240]
    return "unknown"


def build_browser_attempts(
    profile: Path,
    screenshot: Path,
    allow_no_sandbox: bool = False,
) -> list[tuple[str, list[str]]]:
    common = [
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-device-scale-factor=2",
        "--window-size=1100,1600",
        f"--user-data-dir={profile}",
        f"--screenshot={screenshot}",
    ]
    if platform.system() == "Linux":
        common.append("--disable-dev-shm-usage")
    attempts = [
        ("modern-headless", ["--headless=new", "--disable-gpu", *common]),
        (
            "compatibility-headless",
            [
                "--headless",
                "--disable-gpu",
                "--disable-gpu-compositing",
                "--disable-software-rasterizer",
                "--disable-features=Vulkan,UseSkiaRenderer",
                *common,
            ],
        ),
    ]
    if allow_no_sandbox:
        attempts.append(("no-sandbox-fallback", ["--no-sandbox", *attempts[-1][1]]))
    return attempts


def run_browser_command(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    popen_options: dict[str, object] = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        popen_options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_options["start_new_session"] = True
    process = subprocess.Popen(command, **popen_options)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "nt" and shutil.which("taskkill"):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        elif os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            process.kill()
        except OSError:
            pass
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def choose_temp_root(output: Path, override: Path | None = None) -> Path:
    candidates = [override, output.parent, Path(tempfile.gettempdir())]
    failures: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        root = candidate.expanduser().resolve()
        if root in seen:
            continue
        seen.add(root)
        try:
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="paper-ppt-probe-", dir=root):
                pass
            return root
        except OSError as exc:
            failures.append(f"{root}: {exc}")
    raise RenderError("no writable temporary directory: " + "; ".join(failures))


def validate_html(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if 'class="page"' not in text:
        raise RenderError("HTML does not contain the canonical .page element")
    for label in REQUIRED_LABELS:
        if label not in text:
            raise RenderError(f"HTML is missing required row label: {label}")
    if text.count("<tr") != 6:
        raise RenderError("canonical one-page HTML must contain one header row and five body rows")


def crop_page(screenshot: Path, output: Path) -> tuple[int, int]:
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
        background = Image.new("RGB", image.size, (245, 247, 250))
        difference = ImageChops.difference(image, background).convert("L")
        mask = difference.point(lambda value: 255 if value > 5 else 0)
        bbox = mask.getbbox()
        if not bbox:
            raise RenderError("browser screenshot is blank")
        left, top, right, bottom = bbox
        if right - left < 1200 or bottom - top < 600:
            raise RenderError(f"detected page region is unexpectedly small: {bbox}")
        cropped = image.crop((left, top, right, bottom))
        output.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(output, format="PNG", optimize=True)
        return cropped.size


def render(
    html: Path,
    output: Path,
    browser_override: Path | None = None,
    *,
    temp_dir: Path | None = None,
    timeout_seconds: int = 30,
    allow_no_sandbox: bool = False,
) -> dict[str, object]:
    html = html.resolve()
    output = output.resolve()
    validate_html(html)
    browsers = browser_candidates(browser_override)
    if not browsers:
        raise RenderError(
            "no Chromium-family browser found; set PAPER_PPT_BROWSER or pass --browser"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = choose_temp_root(output, temp_dir)
    attempt_log: list[dict[str, object]] = []
    selected_browser: Path | None = None
    selected_strategy = ""
    output_size: tuple[int, int] | None = None

    for browser in browsers:
        browser_timed_out = False
        with tempfile.TemporaryDirectory(prefix="paper-ppt-one-page-", dir=temp_root) as directory:
            temporary = Path(directory)
            screenshot = temporary / "viewport.png"
            profile = temporary / "browser-profile"
            for strategy, flags in build_browser_attempts(
                profile, screenshot, allow_no_sandbox=allow_no_sandbox
            ):
                screenshot.unlink(missing_ok=True)
                command = [str(browser), *flags, html.as_uri()]
                try:
                    completed = run_browser_command(command, timeout_seconds)
                    detail = (completed.stderr.strip() or completed.stdout.strip())[:1200]
                    status = "failed"
                    if completed.returncode == 0 and screenshot.is_file():
                        try:
                            output_size = crop_page(screenshot, output)
                            status = "succeeded"
                        except RenderError as exc:
                            detail = str(exc)
                    attempt_log.append(
                        {
                            "browser": str(browser),
                            "strategy": strategy,
                            "returncode": completed.returncode,
                            "status": status,
                            "detail": detail,
                        }
                    )
                except subprocess.TimeoutExpired:
                    browser_timed_out = True
                    attempt_log.append(
                        {
                            "browser": str(browser),
                            "strategy": strategy,
                            "returncode": None,
                            "status": "timeout",
                            "detail": f"exceeded {timeout_seconds} seconds",
                        }
                    )
                except OSError as exc:
                    attempt_log.append(
                        {
                            "browser": str(browser),
                            "strategy": strategy,
                            "returncode": None,
                            "status": "launch_error",
                            "detail": str(exc),
                        }
                    )
                if output_size is not None:
                    selected_browser = browser
                    selected_strategy = strategy
                    break
                if browser_timed_out:
                    break
        if output_size is not None:
            break

    if output_size is None or selected_browser is None:
        summary = "; ".join(
            f"{Path(str(item['browser'])).name}/{item['strategy']}: {item['status']} {item['detail']}"
            for item in attempt_log
        )
        raise RenderError(f"all headless browser render attempts failed: {summary}")

    manifest = {
        "renderer": "paper-ppt-one-page-html/0.3.0",
        "html": str(html),
        "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
        "browser": str(selected_browser),
        "browser_version": browser_version(selected_browser),
        "strategy": selected_strategy,
        "platform": platform.platform(),
        "attempts": attempt_log,
        "output": str(output),
        "output_size": list(output_size),
        "required_rows": REQUIRED_LABELS,
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--allow-no-sandbox",
        action="store_true",
        help="allow a final Chromium --no-sandbox attempt for isolated CI containers",
    )
    args = parser.parse_args()
    try:
        manifest = render(
            args.html,
            args.output,
            args.browser,
            temp_dir=args.temp_dir,
            timeout_seconds=args.timeout,
            allow_no_sandbox=args.allow_no_sandbox,
        )
    except (OSError, RenderError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Rendered fixed one-page HTML: {manifest['output']}")
    print(f"Size: {manifest['output_size'][0]}x{manifest['output_size'][1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
