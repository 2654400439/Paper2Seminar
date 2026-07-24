# Framework and platform compatibility

## Agent frameworks

| Environment | Discovery in this repository | Standalone installation | Notes |
|---|---|---|---|
| Codex | `.agents/skills/paper-ppt-orchestrator` | Copy the canonical skill to `$CODEX_HOME/skills` | Reads optional `agents/openai.yaml`; `$paper-ppt-orchestrator` invocation is Codex-specific. |
| OpenCode | `.agents/skills/paper-ppt-orchestrator` | Copy the canonical skill to a supported project or user skill directory | Uses `SKILL.md`; ignores `agents/openai.yaml`. |
| Claude Code | `.claude/skills/paper-ppt-orchestrator` | Copy the canonical skill to `.claude/skills` or `~/.claude/skills` | Typical explicit invocation is `/paper-ppt-orchestrator`; ignores `agents/openai.yaml`. |
| Plain model API | None | Requires an agent loop and tools | A chat-only model cannot read PDFs, execute scripts, inspect assets, or build PPTX files by itself. |

Framework compatibility does not guarantee equal deck quality. A model needs long-context paper comprehension, reliable tool use, structured JSON generation, and visual judgment. The validators enforce contracts and workflow state, not factual correctness.

## Host platforms

The core Python utilities and browser renderer support Windows, macOS, and Linux. OfficeCLI must be available for PPTX assembly.

TikZ slides require XeLaTeX and `pdftoppm`. The bundled PowerPoint COM exporter is Windows-only and optional; use it only for final-size rendering when the host supports desktop PowerPoint automation. Core assembly and structural validation do not require Microsoft PowerPoint.

CaptionCrop is recommended but not bundled. When it is unavailable, the skill requires page rendering, explicit manual bounding boxes, provenance recording, and contact-sheet review instead of silently skipping figure QA.

## Tool-name adaptation

`imagegen` and `web-search` in the workflow are capability labels, not portable API names. Each framework should map them to its available image-generation and browsing tools, then record only `available` or `unavailable` in `capabilities.json`. Do not infer availability merely because a related skill file is installed.
