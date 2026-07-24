# Environment compatibility

## Capability preflight

Run `paper_ppt.py preflight` before visual routing. The script automatically records host tools and Python modules. Pass the agent-session states for `--imagegen` and `--web-search`; these capabilities cannot be inferred reliably from installed files or environment variables.

Treat `unknown` as unresolved, not as a reason to repeatedly invoke a missing tool. After one definitive unavailable or authentication failure, record `unavailable` and follow the reported route:

```text
imagegen -> external_image -> tikz_or_none
```

The fallback changes only conceptual imagery. Paper evidence still uses `paper_asset`, `data_redraw`, or a clearly labeled TikZ synthesis.

## Browser rendering

Prefer an explicit `--browser` or `PAPER_PPT_BROWSER` in managed environments. Otherwise the renderer searches PATH and common Chromium-family install locations on Windows, macOS, and Linux.

The renderer uses two bounded attempts per browser:

1. Modern Chromium headless mode with conservative flags.
2. Legacy/compatibility headless mode with GPU and Vulkan/Skia workarounds.

Each attempt defaults to a 30-second timeout. A timeout terminates the browser process tree and skips the second strategy for that browser, preventing a blocked desktop or sandbox session from multiplying retries. Override the timeout only for demonstrably slow CI hosts.

It uses a unique browser profile and a writable temporary directory near the requested output before falling back to the system temp directory. Set `--temp-dir` when policy requires a specific location. `--no-sandbox` is never automatic; enable `--allow-no-sandbox` only inside an isolated CI container.

## PowerPoint rendering

Detecting `POWERPNT.EXE` proves installation, not COM runtime access. Desktop-session, sandbox, and service-account restrictions may still block export. Keep overview rendering separate from the core build and fall back in this order: PowerPoint, LibreOffice, OfficeCLI, then an explicitly incomplete text/HTML check.

## PowerShell and UTF-8

- Prefer PowerShell 7 (`pwsh`) for new automation.
- Windows PowerShell 5.1 may parse UTF-8 files without a BOM using the active code page. Keep `.ps1` source ASCII when practical, or save non-ASCII scripts as UTF-8 with BOM.
- Read and write JSON with explicit UTF-8 APIs. Do not round-trip structured JSON through default `Get-Content | Set-Content` encoding.
- Keep user-visible non-ASCII strings in UTF-8 JSON or HTML resources when a PowerShell helper can remain ASCII.
- Invoke Python through `sys.executable` from Python orchestration so the same interpreter and environment are preserved.
- On Windows locales where a third-party Python utility calls `Path.read_text()` without an explicit encoding, run it with `PYTHONUTF8=1`. The bundled paper-PPT scripts already specify UTF-8 for their text and JSON files.
