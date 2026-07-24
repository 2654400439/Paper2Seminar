# Architecture

The project separates model-owned semantic decisions from deterministic execution.

```text
paper PDF
  -> agent: paper inventory + subsection coverage
  -> agent: ordered slide plan + evidence and visual routing
  -> scripts: schema and policy validation
  -> agent/tools: paper crops, TikZ, redraws, conceptual media
  -> scripts: asset approval state
  -> OfficeCLI builder: pristine template -> PPTX
  -> scripts + reviewer: structural, content, visual, and readability QA
```

## Canonical state

`deck-plan.json` is the single machine-readable source of truth for slide order, body runs, speaker notes, visual decisions, source metadata, and approval state. Scripts must not independently summarize the paper or silently choose a visual type.

## Ownership boundary

The agent owns full-paper reading, claim selection, slide budgeting, evidence interpretation, and visual suitability. Python scripts own deterministic rendering, cropping, state transitions, template assembly, and structural checks.

The boundary matters for portability: any capable agent framework can provide the semantic layer, while the same scripts provide reproducible execution. Deterministic validation can detect missing fields and invalid state, but it cannot prove that a paper was understood correctly.

## Packaging

`skills/paper-ppt-orchestrator/` follows the Agent Skills layout and is the only distributable package. `agents/openai.yaml` is an optional Codex adapter. `.agents/` and `.claude/` contain repository-local discovery loaders and are not independent copies of the skill.
