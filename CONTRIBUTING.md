# Contributing

Keep changes scoped to the staged paper-to-PPT workflow and preserve the boundary between model judgment and deterministic scripts.

Before opening a pull request:

1. Do not commit source-paper PDFs or run directories. Add generated decks or rendered slides only as curated samples under `examples/`, after validation and with an explicit third-party content-rights notice. Changes to the intentionally retained template branding and presenter metadata must be reviewed.
2. Keep `skills/paper-ppt-orchestrator/` self-contained. Repository loaders may point to it, but the canonical skill must work when copied alone.
3. Keep `SKILL.md` concise and move detailed contracts to `references/`.
4. Update JSON schemas, examples, validation code, and tests together when changing `deck-plan.json`.
5. Keep configurable features synchronized across `job-request.schema.json`, every default profile, `feature-registry.json`, Skill references, UI controls, and tests. Reserved features must remain disabled.
6. Preserve cross-platform Python paths. Isolate Windows-only PowerPoint automation as optional functionality.
7. Run `python -m unittest discover -s tests -v` and validate the example plan.

New bundled assets must be accompanied by a clear license, permission statement, or original-work statement in the pull request.
