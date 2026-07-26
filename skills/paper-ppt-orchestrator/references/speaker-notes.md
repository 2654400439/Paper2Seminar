# Post-QA speaker notes

Speaker-note writing is a separate finalization stage. Finish the core deck, complete visual review, and record slide approval before drafting the script. This ordering prevents narration needs from distorting slide structure or visual decisions.

## Source boundary

The agent may use only:

- `deck-plan.json`: titles, body runs, purpose, takeaway, and visual metadata;
- `paper-notes.json`, evidence records, and the paper's extractable text;
- figure/table labels, captions, source pages, and approved data-redraw specifications.

Do not read rendered slide screenshots to write the script. Screenshots are visual-QA evidence, not a semantic source. Do not infer chart values from pixels or introduce a claim that is absent from the paper inventory or evidence records.

## Output contract

When `project.speaker_notes.enabled` is true, use this configuration:

```json
{
  "speaker_notes": {
    "enabled": true,
    "generation_stage": "post_qa",
    "delivery_style": "verbatim",
    "target_minutes": 30,
    "pace_units_per_minute": 220
  }
}
```

After core approval, add `speaker_notes` and `speaker_seconds` to every slide, including cover, paper-information, one-page, contents, section dividers, and closing. The script must be natural spoken prose rather than bullet fragments or instructions to the presenter.

For a normal 30-minute seminar, start with these budgets:

| Slide role | Typical time |
|---|---:|
| Cover | 15-25 seconds |
| Paper information | 45-70 seconds |
| One-page summary | 60-90 seconds |
| Contents | 20-30 seconds |
| Section divider | 8-15 seconds |
| Content slide | 55-95 seconds, adjusted by evidence density |
| Closing | 10-20 seconds |

Allocate the remaining time across content slides by conceptual and evidence density. The validator accepts a total within 15% of the configured target. `pace_units_per_minute` is only a drafting aid for mixed Chinese and English; the explicit `speaker_seconds` values are the timing contract.

## Writing rules

- Open each content page with the question or transition that makes the page necessary.
- Explain the visible figure, table, or mechanism using its recorded caption, source, and rationale.
- State metric, unit, baseline, and condition when presenting a numerical result.
- Preserve uncertainty, limitations, and attribution from the paper notes.
- Do not mechanically read the bullets. Expand them with reasoning and transitions, while keeping the same factual boundary.
- Keep fixed-role slides brief. Section-divider notes should connect the preceding conclusion to the next question.
- Write a complete verbatim script; do not write prompts such as "introduce this figure" or "improvise here".

## Apply and validate

The core builder intentionally does not write notes. After `approve-slides`, update the plan and run:

```text
python scripts/paper_ppt.py apply-notes deck-plan.json
python scripts/validate_deck_plan.py deck-plan.json --stage final
```

`apply-notes` validates the post-QA state, writes every note on a temporary PPTX, runs OfficeCLI validation, and replaces the output only after all checks pass. It writes `presentation.notes.json` beside the deck.
