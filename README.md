# Paper2Seminar

[简体中文](README.zh-CN.md) | English

<p align="center"><img src="docs/assets/hero.png" width="920" alt="Paper2Seminar workflow illustration"></p>

<p align="center"><strong>One paper. One prompt. A seminar deck that doesn’t look one-click.</strong></p>
<p align="center">One-click academic-paper PPT generation with editable output and the visual restraint of a real research seminar.</p>

<p align="center">
  <img alt="Agent Skill" src="https://img.shields.io/badge/Agent%20Skill-compatible-194A96">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB">
  <img alt="Output PPTX" src="https://img.shields.io/badge/output-editable%20PPTX-2F855A">
  <img alt="License MIT" src="https://img.shields.io/badge/code%20license-MIT-555555">
</p>

## Why this project exists

One-click AI slide generators solve the blank-page problem, but often create a more awkward one:

- the entire deck is flattened into images and is painful to edit;
- every slide is polished like a product launch, even when the setting is a weekly research seminar;
- the deck looks complete before it has actually understood the paper;
- decorative visuals replace evidence, while important methods and experiments quietly disappear;
- the presenter receives a finished-looking file they cannot confidently explain or revise.

In a research group, those fingerprints are visible immediately. The problem is not simply that AI was used. The problem is that the deck carries the familiar “one-click look”: too generic, too ornamental, too shallow, or impossible to correct. It feels less like a student’s seminar deck and more like an AI presentation demo.

**Paper2Seminar is a dedicated one-request generator for academic-paper presentations.** Give it a paper PDF and one instruction; it reads the paper, budgets the deck, plans every slide, routes the visuals, assembles an editable PPTX, and runs QA.

The target is a solid **80-point seminar deck by default**: complete and polished enough to use directly, but restrained enough to look natural in a lab meeting. It may not be as spectacular as a fully image-generated ChatGPT deck. That is intentional. It should require fact-checking and optional personalization, not a manual rebuild.

> **One-click is the interface, not the aesthetic.**

## What “doesn’t look one-click” means

| Typical one-click deck | Paper2Seminar |
|---|---|
| Prompt in, finished-looking deck out | Full paper inventory, coverage map, slide plan, assets, assembly, and QA |
| Slides or text flattened into images | Editable PPTX text, shapes, pictures, and speaker notes |
| Marketing-style layouts and decorative variety | A restrained seminar template with predictable academic structure |
| Visuals chosen for appearance | Visuals routed by purpose: paper evidence, exact redraw, TikZ synthesis, or concept image |
| Short, generic summary of a long paper | Complexity-aware slide budgeting and subsection-level coverage |
| Fixing one claim may require regeneration | `deck-plan.json` remains the reviewable source of truth |
| “Looks done” is treated as done | Explicit asset approval, slide approval, structural checks, and optional readability review |

The goal is not to inject fake imperfections. The deck feels naturally prepared because it follows familiar seminar conventions: sensible density, restrained styling, paper-grounded figures, ordinary editable objects, and a narrative that reflects the structure of the paper.

## The controls behind the result

There is no single “make it human” prompt. The workflow earns that quality through a sequence of constraints:

```text
paper.pdf
  -> full-paper inventory
  -> subsection coverage matrix
  -> complexity-aware slide budget
  -> ordered deck-plan.json
  -> evidence-aware visual routing
  -> reviewed visual assets
  -> deterministic editable PPTX assembly
  -> structural + content + visual QA
```

### Content control

- Read the complete paper before planning the deck.
- Map core method subsections, research questions, and primary experiments to slides.
- Write the complete title sequence before generating visual assets.
- Separate paper claims from presenter analysis and preserve exact numerical context.

### Visual control

- Prefer original paper figures for methods and experimental evidence.
- Use Matplotlib redraws only for exact, genuinely comparable values.
- Use TikZ for synthesized mechanisms and causal structure.
- Restrict generated or external imagery to conceptual communication, never experimental proof.
- Review crops and generated assets before they are allowed into the deck.

### Format control

- Assemble from a pristine 16:9 seminar template instead of painting every slide into a bitmap.
- Keep body copy, emphasis, slide order, images, notes, and alt text editable in PPTX.
- Use a deliberately restrained fixed layout so the deck reads like research work, not a landing page.

### QA control

- Validate the plan before asset generation, before assembly, and after approval.
- Record capabilities, source paths, hashes, approvals, and output locations per run.
- Keep PowerPoint rendering optional and separate from core assembly.
- Treat script success as necessary but never sufficient for semantic approval.

## What it produces

- A complete Chinese seminar deck with necessary English technical terms.
- An editable `.pptx`, assembled through OfficeCLI from the bundled template.
- A structured `deck-plan.json` containing slide copy, visual decisions, notes, and review state.
- Paper crops, manual-crop provenance, TikZ sources, data-redraw specifications, and manifests.
- A browser-rendered one-page paper summary.
- Optional overview or grouped readability images for final review.

The workflow is currently strongest on 12–16+ page systems, security, networking, and measurement papers. A full paper typically receives 26–32 slides unless the user explicitly asks for a short talk.

## Quick start

Open the repository as the agent working directory, place or reference a paper PDF, and ask:

```text
Use paper-ppt-orchestrator to turn ./paper.pdf into a complete, deliverable Chinese seminar PPT. Follow the default workflow and create a new run directory.
```

For Codex, the explicit form is:

```text
Use $paper-ppt-orchestrator to turn ./paper.pdf into a complete, deliverable Chinese seminar PPT.
```

The repository-local loaders allow Codex and OpenCode to discover `.agents/skills/paper-ppt-orchestrator`, while Claude Code can discover `.claude/skills/paper-ppt-orchestrator`.

## Requirements

Core execution requires:

- A capable tool-using agent with filesystem and shell access.
- Python 3.10+ and packages from `requirements.txt`.
- [OfficeCLI](https://officecli.ai/) for PPTX inspection and assembly.
- A Chromium-family browser for the one-page HTML render.
- XeLaTeX and `pdftoppm` when the full workflow routes a slide to TikZ.

Optional capabilities:

- CaptionCrop for automated figure extraction; a provenance-recorded manual crop path is available as fallback.
- Image generation or licensed web-image search for conceptual imagery.
- Microsoft PowerPoint on Windows for the optional highest-fidelity readability export. Core assembly does not require it.

Run capability preflight before visual routing:

```text
python skills/paper-ppt-orchestrator/scripts/paper_ppt.py preflight -o runs/demo/capabilities.json --imagegen unavailable --web-search unavailable
```

## Framework installation

For standalone installation, copy `skills/paper-ppt-orchestrator/` to the framework’s skill directory:

| Framework | Install destination | Typical invocation |
|---|---|---|
| Codex | `$CODEX_HOME/skills/paper-ppt-orchestrator` or `~/.codex/skills/paper-ppt-orchestrator` | `$paper-ppt-orchestrator` |
| OpenCode | project `.agents/skills/paper-ppt-orchestrator` or its configured skill directory | natural-language request / skill tool |
| Claude Code | `.claude/skills/paper-ppt-orchestrator` or `~/.claude/skills/paper-ppt-orchestrator` | `/paper-ppt-orchestrator` |

`agents/openai.yaml` keeps its standard filename. It is optional Codex-facing metadata, not the portable workflow definition; other frameworks use `SKILL.md`.

See [framework and platform compatibility](docs/compatibility.md) for the exact portability boundary.

## Repository layout

```text
.
|-- .agents/skills/paper-ppt-orchestrator/   # Codex/OpenCode repository loader
|-- .claude/skills/paper-ppt-orchestrator/   # Claude Code repository loader
|-- skills/paper-ppt-orchestrator/           # canonical, self-contained skill
|   |-- SKILL.md
|   |-- agents/openai.yaml
|   |-- assets/
|   |-- references/
|   `-- scripts/
|-- examples/
|-- tests/
`-- docs/
```

`skills/paper-ppt-orchestrator/` is the distributable package. The hidden framework directories are repository-local loaders, not independent copies.

## Current boundaries

- The project produces a strong first deliverable, not an unsupervised final truth.
- Semantic accuracy still depends on the model reading the paper correctly and on human review.
- The default content layout is intentionally fixed and restrained rather than infinitely themeable.
- The bundled template retains its current UCAS identity and presenter/advisor defaults; replace them in Slide Master and the cover/closing slides when needed.
- Source papers, extracted publisher figures, generated decks, and `runs/` are intentionally excluded from version control.

## Development

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python skills/paper-ppt-orchestrator/scripts/validate_deck_plan.py examples/deck-plan.example.json --stage plan
```

Read [architecture](docs/architecture.md) and [contributing](CONTRIBUTING.md) before changing the deck-plan contract, builder, or bundled assets.

## Licensing

Repository-authored code and documentation are licensed under the MIT License. Third-party tools remain under their own licenses. UCAS names and marks in the bundled template are not granted under MIT; replace them when their use is not authorized. See [THIRD_PARTY.md](THIRD_PARTY.md) for the boundary.

If this workflow saves you from choosing between an obviously generated deck and rebuilding everything by hand, consider starring the repository. Stars help us understand whether this problem is shared beyond one research group.
