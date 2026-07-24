# Deck sizing and coverage

## Principle

Derive slide count from paper complexity and coverage, not from the number of template content slides. Treat target duration as a pacing constraint, not permission to omit central methods or experiments.

The bundled template contributes nine non-content slides: cover, paper information, one-page table, contents, four section dividers, and closing. Count these separately from content slides.

## Default ranges

| Paper profile | Typical evidence | Total deck | Content slides |
|---|---|---:|---:|
| Short paper, 6-8 pages | One main idea and compact evaluation | 18-24 | 9-15 |
| Standard paper, 9-11 pages | One method plus normal evaluation | 22-28 | 13-19 |
| Full paper, 12-16+ two-column pages | Multi-module method or substantial measurement/evaluation | 26-32 | 17-23 |
| Measurement plus new system/defense | Two substantial contributions and multiple RQs | 28-32 | 19-23 |

For a full-length paper, do not produce fewer than 26 total slides unless the user explicitly requests a short talk. If a shorter deck is requested, record the omitted subsections and describe the result as an abbreviated deck.

## Section budgets for a full systems/security paper

Use these as starting ranges, then adapt to the paper:

- Background, threat model, benchmark, or measurement context: 4-6 content slides.
- Method: 5-7 content slides. Allocate an overview, at least one slide per substantive module, and separate slides for algorithms, optimization loops, restoration logic, or implementation details when they carry independent ideas.
- Results: 6-9 content slides. Separate experimental setup, primary effectiveness, baseline/ablation, robustness or sensitivity, generalization, usability, and overhead when present.
- Reflection: 2-3 content slides.

Do not force equal section lengths. Do not interpret the template's one seed content slide per section as a three-page or four-page cap.

## Mandatory coverage matrix

Before writing slide bodies, create a matrix in `paper-notes.json` with one row per main paper subsection:

```json
{
  "paper_section": "7.3 Robustness",
  "importance": "core",
  "planned_slide_ids": ["S24", "S25"],
  "status": "covered",
  "omission_reason": ""
}
```

Allowed status values are `covered`, `notes_only`, and `omitted`. Every abstract contribution, main method subsection, research question, primary experiment, limitation, and major appendix result used by the paper's claims must be `covered` or `notes_only`. A core item cannot be `omitted` without explicit user approval.

Run these checks before asset generation:

- Every paper contribution maps to at least two content slides when it contains multiple stages, modules, or studies.
- Every substantive method module maps to at least one slide.
- Experimental setup and metrics are visible before result interpretation.
- Every named RQ maps to at least one result slide.
- Baselines/ablations, adaptive or sensitivity tests, usability, and overhead are not silently collapsed when they support different claims.
- Reading only the title sequence still exposes the full argument and evidence chain.

## Per-slide budget

Keep the existing fixed layout:

- One idea and one takeaway per content slide.
- Normally three bullets totaling 5-6 rendered lines at 18pt.
- Split a slide instead of shrinking text or combining independent claims.
- Use speaker notes for qualifications and transitions, not for hiding an entire omitted subsection.
