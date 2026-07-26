# Content design rules

Read `deck-sizing.md` before using this file. Per-slide brevity does not justify whole-deck incompleteness.

## Build the title sequence first

Write all slide titles in order before body text or visuals. Use one title grammar throughout: concise topic phrases or concise conclusion statements. Do not mix styles randomly.

The title sequence must answer:

- What is the problem?
- Why do existing approaches fall short?
- What is the paper's central idea?
- How does the method work?
- What evidence supports it?
- What should the audience believe, question, or reuse?

Split a slide when it has two independent takeaways.

Before accepting the title sequence, compare it with the subsection coverage matrix. Every core method subsection, named RQ, primary experiment, and limitation that supports the conclusion must appear in a slide title or be deliberately assigned to speaker notes.

## Four-section responsibilities

### Background

- Teach only the concepts required to understand the paper.
- Establish the concrete failure, cost, or research gap.
- End with the paper's research question or design target.

Avoid a generic literature lecture that is not used later.

### Method

- Explain the system or algorithm in dependency order.
- Separate overview, key mechanism, special cases, and complexity when each matters.
- Preserve the difference between what the authors implement and what the presenter uses as analogy.
- For a multi-module method, allocate an overview plus separate slides for each module and any independent optimization, restoration, training, or implementation mechanism. Three method pages are not a default target.

### Results

- State dataset, baseline, metric, and comparison condition before interpreting numbers.
- Put units and directionality on every numerical claim.
- Do not claim causality when the experiment only shows association.
- Include negative, sensitivity, or overhead evidence when it affects the conclusion.
- Give experimental setup and metrics their own visible treatment before interpreting results.
- Map each named research question to at least one slide. Split primary effectiveness, baseline/ablation, adaptive or sensitivity analysis, generalization, usability, and overhead when they answer different claims.

### Reflection

- Separate paper-stated limitations from presenter criticism.
- Identify reusable design patterns, not vague praise.
- State what evidence would change the conclusion.
- Use discussion questions only when they create a real decision or unresolved issue.

## Slide copy budget

For the current template:

- One purpose and one takeaway per content slide.
- Prefer 3 complete bullets; allow 2-5 only when the estimated rendered total remains 5-6 lines.
- Target 5-6 rendered body lines. A practical Chinese draft is usually 180-250 characters, but line count takes precedence over raw character count.
- Use 18pt body text; do not solve overflow by shrinking.
- Use short, parallel bullet grammar.
- Begin each bullet with a short black bold lead phrase so the bullet marker remains black.
- After the lead phrase, split genuinely important method names, decisive numbers, outcomes, or boundary conditions into `accent` runs. The P0 builder renders `accent` as bold dark blue (`#194A96`). Normally use 1-3 accent phrases per content slide; highlight meaning, not sentence structure.
- Dark red may be used sparingly for risks, failures, regressions, or negative findings when the Office editing path supports explicit run-level color. Keep it bold, never apply it to the first run or bullet marker, and do not mix blue and red without a semantic reason.
- Do not color whole bullets, routine connective text, citations, or decorative words. Contributions on the paper-information slide remain black with selective bold only.
- Keep citations and detailed qualifications in speaker notes when the slide would become crowded.

The body is not a transcript. Do not draft the verbatim script while designing slide copy. Add it only in the post-QA stage defined by `speaker-notes.md`, using the approved plan, visual metadata, paper notes, evidence records, and paper text.

## Paper-information contributions

- Prefer 3 contribution statements.
- Make each statement occupy about two rendered lines in the current template.
- Preserve the template's `本文贡献：` heading and place each statement in its own level-1 hollow-square paragraph.
- Keep contribution statements regular-weight and black; express selected key phrases as `bold` runs.
- Include the method or artifact, what it changes, and the evidence or capability it enables.
- Do not use fragments such as "proposes Nano" or restate the abstract as a single long paragraph.

## Optional P1 evidence contract

Create evidence records with unique IDs. Each record contains:

- `claim`: normalized factual statement.
- `kind`: `paper_claim` or `presenter_analysis`.
- `paper_page`: 1-based PDF page when applicable.
- `paper_section`: section or appendix name.
- `artifact_label`: figure/table identifier when applicable.
- `quote_or_summary`: concise support, not a long copyrighted quotation.
- `confidence`: `high`, `medium`, or `low`.

P0 does not require evidence IDs. In P1, key numerical results and author claims reference evidence IDs; reflection bullets may reference `presenter_analysis`.

## Human-sounding checks

- Prefer specific nouns and verbs over abstract filler.
- Avoid hype words, generic transition phrases, and repeated sentence frames.
- Do not start every title with “为什么”, “如何”, or “关键”.
- Preserve useful technical terms rather than replacing them with vague summaries.
- Let a result number or mechanism carry emphasis; do not manufacture drama.
- Read the title sequence aloud. If it sounds like generated headings rather than a talk, rewrite it.
