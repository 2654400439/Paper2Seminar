# Architecture

The project separates model-owned semantic decisions from deterministic execution.

```text
paper PDF
  -> UI / Skill / CLI: validated job-request.json
  -> agent: paper inventory + subsection coverage
  -> agent: ordered slide plan + evidence and visual routing
  -> scripts: schema and policy validation
  -> agent/tools: paper crops, TikZ, redraws, conceptual media
  -> scripts: asset approval state
  -> OfficeCLI builder: pristine template -> PPTX
  -> scripts + reviewer: structural, content, visual, and readability QA
  -> agent: post-QA verbatim script from text plan, evidence, and paper notes
  -> scripts: atomic speaker-note insertion + final validation
```

## Canonical state

`job-request.json` is the immutable source of truth for user configuration and interaction policy. `deck-plan.json` is the source of truth for slide order, body runs, speaker notes, visual decisions, source metadata, and approval state. Scripts must not independently summarize the paper or silently choose a visual type.

## Ownership boundary

The agent owns full-paper reading, claim selection, slide budgeting, evidence interpretation, and visual suitability. Python scripts own deterministic rendering, cropping, state transitions, template assembly, and structural checks.

The boundary matters for portability: any capable agent framework can provide the semantic layer, while the same scripts provide reproducible execution. Deterministic validation can detect missing fields and invalid state, but it cannot prove that a paper was understood correctly.

Speaker-script generation deliberately sits after core slide approval. It consumes structured text and visual metadata, never slide screenshots, and the deterministic notes writer mutates a temporary copy of the finished deck before replacing the output.

## Packaging

`skills/paper-ppt-orchestrator/` follows the Agent Skills layout and is the only distributable package. `agents/openai.yaml` is an optional Codex adapter. `.agents/` and `.claude/` contain repository-local discovery loaders and are not independent copies of the skill.

## README workflow animation

The localized GIFs under `docs/assets/workflow-pipeline.*.gif` are generated assets, not hand-edited binaries. Rebuild both deterministic 1200x560 animations with:

```text
python docs/render_workflow_animation.py
```

Use `--preview-dir` to export representative PNG frames for visual QA. The source keeps module geometry, timing, localized copy, and the evidence-packet return loop in one file so the Chinese and English README visuals stay structurally aligned.
