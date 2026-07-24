# Repository guidance

- Treat `skills/paper-ppt-orchestrator/` as the canonical skill package.
- Keep `.agents/` and `.claude/` as thin repository-local loaders; do not duplicate scripts or assets there.
- Never commit paper PDFs, extracted figures, generated decks, or `runs/` contents.
- Keep Windows-only PowerPoint automation optional. Core validation and tests must remain runnable without PowerPoint.
- When changing the deck-plan contract, update its schema, validator, example, and tests in the same change.
