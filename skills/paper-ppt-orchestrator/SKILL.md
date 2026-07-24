---
name: paper-ppt-orchestrator
description: Build complete fixed-layout academic-paper presentations from a PDF with bundled PPTX and one-page HTML templates. Use for full paper reading, complexity-aware slide budgeting, subsection coverage mapping, figure extraction, TikZ or Matplotlib evidence visuals, deterministic PPTX assembly, and final QA. Trigger for requests to turn a paper PDF into a discussion-group deck, especially 12-16+ page systems, security, networking, or measurement papers.
---

# Paper2Seminar

Produce a reviewable research-talk deck through staged artifacts. Do not edit the PPTX while still deciding what the paper says.

## Required inputs

The paper PDF is the only input the user must provide. Use these defaults unless the user overrides them:

- Academic paper PDF.
- PPTX template: `assets/seminar-template.pptx`.
- One-page template: `assets/one-page-summary.html`.
- Language: Chinese slide copy with necessary English technical terms.
- Output: a new paper-specific directory under `runs/`.
- Slide count: derive from `references/deck-sizing.md`; do not ask the user to choose a count unless they want an abbreviated talk.

Use a clean run directory. Never derive a new deck from a previous generated deck.

## Read references progressively

1. Read `references/workflow.md` for every end-to-end run.
2. Read `references/template-contract.md` before inspecting or modifying the template.
3. Read `references/content-design.md` while creating the title sequence and slide copy.
4. Read `references/deck-sizing.md` before choosing a slide count. This is mandatory for every full-paper run.
5. Read `references/one-page-template.md` before producing slide 3.
6. Read `references/figure-extraction.md` before extracting paper figures or tables.
7. Read `references/visual-selection.md` before assigning or generating visuals.
8. Read `references/tikz-layout.md` only when at least one slide uses TikZ.
9. Read `references/data-viz.schema.json` when at least one slide uses `data_redraw`.
10. Read `references/qa-gates.md` before assembly and final delivery.
11. Use `references/deck-plan.schema.json` as the machine-readable plan contract.
12. Read `references/environment-compatibility.md` when running preflight, browser rendering, PowerPoint export, or PowerShell scripts.

If the environment provides separate CaptionCrop, TikZ, Office/PPTX, or image-generation skills, load the relevant skill before invoking that capability. The bundled DocLayout extractor does not require a separate skill.

## Mandatory workflow

### 1. Preflight

- Preserve the original PDF and template.
- Verify the paper is text-extractable.
- Inspect template slide roles, placeholder tokens, shape names, fonts, and renderability.
- Create `run-manifest.json` with input paths, hashes when practical, tool versions, and output paths.
- Inspect the actual tool inventory, then create `capabilities.json` with `paper_ppt.py preflight`. Declare agent-only `imagegen` and `web-search` capabilities explicitly; a skill being installed is not proof that its execution tool is available.
- Resolve an `unknown` media capability once before visual routing. If image generation is absent or returns a definitive unavailable/authentication error, mark it unavailable and move to the recorded fallback instead of retrying the same path.
- Stop if the template contract is ambiguous.

```text
python scripts/paper_ppt.py preflight -o RUN/capabilities.json --imagegen available|unavailable --web-search available|unavailable
```

### 2. Build the paper inventory

- Read the complete paper, including appendix material needed for claims.
- Record paper metadata, section summaries, contributions, limitations, candidate slide claims, and the small set of exact values that may need data redraw.
- Create the mandatory subsection coverage matrix defined in `references/deck-sizing.md`. Do not plan slides until every core method subsection, research question, and primary experiment has a coverage status.
- Write each contribution as rich-text runs that occupy about two lines. Keep the statement regular-weight and mark only key phrases `bold`; do not use accent color.
- Use the bundled DocLayout backend by default for slide-ready figure/table extraction, metadata, annotated pages, and a contact sheet. Keep CaptionCrop as the explicit lightweight alternative with `--backend captioncrop`; if neither automatic route is available, render only required pages and make provenance-recorded manual crops.
- Crop the author and affiliation band from below the paper title with `paper_ppt.py crop-authors`; keep the title and abstract outside the crop. Use `--bbox` when automatic anchors are unreliable.
- Review the contact sheet. Mark each crop `approved`, `rejected`, or `needs_adjustment`; detection alone is not approval.

### 3. Plan before generating assets

- Write the complete ordered title sequence first.
- Map every content slide to one of the four sections: `background`, `method`, `results`, `reflection`.
- Derive the total count from paper complexity. A full 12-16+ page two-column paper normally requires 26-32 total slides; a paper combining measurement and a new system/defense normally requires 28-32. Fewer than 26 requires an explicit short-talk request or approved omission list.
- Budget method and results from their actual subsection structure. Do not cap either section at three pages because the template contains one seed slide.
- Create `deck-plan.json`; every content slide must include purpose, takeaway, body runs, speaker notes, `content_stacked` layout, and visual decision. Target 5-6 rendered body lines, normally across three complete bullets. Evidence references are optional in P0.
- Treat visual diversity as a deck-level completeness requirement. Before generating assets, route at least one suitable conceptual content slide to `imagegen` when available, or to `external_image` when capability preflight records image generation as unavailable and licensed web-image search as available. Also route at least one slide to `tikz` and one to `data_redraw`. These are minimum counts across the complete deck, not requirements for every slide, and they do not override evidence fidelity.
- Structure each body bullet as rich-text runs. Keep the opening lead phrase black and bold, then mark genuinely important method names, decisive values, outcomes, or boundary conditions later in the sentence as `accent`. A P0 `accent` run is bold dark blue; use it selectively, normally 1-3 highlighted phrases per content slide.
- Run:

```powershell
python scripts/validate_deck_plan.py deck-plan.json --stage plan
```

- Resolve all errors before asset generation. Present the title sequence and visual routing for review when the user wants checkpoints.

### 4. Fill and render the fixed one-page table

- Copy `assets/one-page-summary.html` into the run directory.
- Replace only the answer/example content defined in `references/one-page-template.md`; preserve the HTML structure and CSS.
- Render the complete `.page` element in a browser to `assets/one-page/one-page.png`.
- Never substitute a new one-page design when rendering fails.

### 5. Generate and approve visuals

- Prefer paper assets for faithful method and result evidence.
- Use TikZ for synthesized mechanisms, processes, comparisons, or causal structure.
- Use `data_redraw` only when at least two exact, comparable values form a real comparison, trend, distribution, or matrix. Keep a lone headline number as emphasized slide text. Write a constrained data-viz spec and run `render_data_viz.py`; do not use OCR or estimate values from an unlabeled chart.
- Use image generation only for conceptual background or metaphor; never use it as experimental evidence or a precise architecture source.
- When image generation is unavailable, use `external_image` only after capability preflight selects that fallback. Search for a visually relevant image with explicit reuse terms, download the original asset rather than a search thumbnail, and record query, source page, creator/provider, license name and URL, retrieval date, hash when practical, and transformations. Store it under `assets/external/`.
- Across a complete deck, include at least one approved conceptual visual (`imagegen`, or `external_image` only through the recorded fallback), one compiled and approved TikZ visual, and one faithful `data_redraw` visual based on exact paper values. Choose semantically appropriate slides for these modes; do not force them onto result evidence or precise architecture slides where they would mislead.
- This diversity floor is a planning constraint in P0. Do not add an extra automated validation or rerender cycle solely to count the three modes.
- Use `none` sparingly and normally only in reflection or discussion.
- Store prompts, source files, outputs, and QA status in the deck plan. Add formal source anchors in P1 when requested.
- Compile and visually inspect every TikZ artifact. Inspect every generated image, external image, and paper crop at the size it will occupy on the slide.
- After standalone asset review, record the explicit transition to `ready` instead of editing QA fields by hand:

```text
python scripts/paper_ppt.py approve-assets deck-plan.json --all-content --note "standalone assets reviewed"
```

### 6. Assemble from a pristine template

- Copy the original template to the run output.
- Replace fixed slides by semantic placeholder mapping.
- Clone the section-specific content template for each content slide; never overwrite later template slides to simulate insertion.
- Preserve theme, master, section navigation, slide relationships, and aspect ratio.
- Set content titles to 18pt bold and body text to 18pt; do not inherit placeholder defaults.
- Preserve rich-text emphasis when filling body paragraphs. The bullet lead-in stays black bold; later `accent` runs must remain bold and use the template's dark-blue accent. Dark red may be used sparingly for risks, failures, or negative findings when the Office editing path supports explicit run color, but never color the bullet lead-in or marker.
- Insert diagrams and paper screenshots with `contain`; crop only conceptual photos intended for `cover` treatment.
- Add speaker notes and alt text.
- Recompute presentation order and page numbers after insertion.

Run the whole deterministic execution stage:

```text
python scripts/paper_ppt.py run deck-plan.json
```

Final-size readability rendering is optional and defaults to `off`; the core build does not launch PowerPoint or produce slide screenshots. Set `project.final_readability_mode` or pass `--readability-mode` only when requested:

```text
python scripts/paper_ppt.py readability --mode overview --pptx build/presentation.pptx -o qa/readability

python scripts/paper_ppt.py readability --mode full --pptx build/presentation.pptx -o qa/readability --group-size 4
```

`overview` produces one deck-wide image for gross layout defects. `full` produces review images containing at most four slides each for final-size readability inspection. Keep the legacy `overview` command only for backward compatibility.

### 7. Validate and iterate

- Execute the required structural gates in `references/qa-gates.md`.
- Keep final-size readability mode `off` unless the user or frontend explicitly selects `overview` or `full`. Do not read rendered slide groups in the default mode.
- Use `overview` only for gross layout defects. Use `full` when fine readability confirmation is worth the rendering and image-review cost; inspect every generated group image once.
- Record final approval atomically after content and visual review. This command sets `visual.qa_status=approved`, `content_approved=true`, and `visual_approved=true` together and appends `qa/approval-log.jsonl`:

```text
python scripts/paper_ppt.py approve-slides deck-plan.json --all-content --note "final content and visual review complete"
```

When readability mode is `overview` or `full`, `approve-slides` requires the matching readability manifest and evidence files.
- Run final plan validation only after approvals are recorded:

```powershell
python scripts/validate_deck_plan.py deck-plan.json --stage final
```

## Non-negotiable rules

- Do not invent claims, numbers, authors, venues, or citations.
- Do not use generated or external conceptual imagery on result slides.
- Do not declare extraction successful without reviewing the contact sheet.
- Do not shrink body text below 18pt to solve overflow; shorten or split the slide.
- Do not color the first run of a bullet. Use black bold text at the start so the bullet marker remains black.
- Do not leave all body text black after the lead phrases. Every content slide should normally contain at least one later `accent` run for a real keyword, decisive value, result, or limitation; avoid coloring filler words or entire sentences.
- Do not deliver a complete deck that lacks all three deck-level visual categories: at least one conceptual visual (`imagegen`, or `external_image` when the capability report requires fallback), one TikZ synthesis diagram, and one faithful exact-value data redraw. This is a planning rule, not a counting-only P0 QA gate.
- Do not label a searched or downloaded image as `imagegen`. Use `external_image` and preserve auditable provenance and license metadata.
- Do not edit QA status fields in bulk with ad hoc text replacement. Use the audited transition commands.
- Do not treat optional final-size readability rendering as a default gate. Asset review, structural validation, and explicit final approval remain required when readability mode is `off`.
- Do not submit a content slide with less than five or more than six estimated body lines.
- Do not plan a full 12-16+ page paper below 26 total slides without an explicit short-talk request or approved coverage omissions.
- Do not omit a main method subsection, named research question, primary baseline/ablation, robustness result, usability result, or overhead result without recording and approving the omission.
- Do not redesign the one-page summary. Use the bundled HTML table, preserve its CSS and structure, and replace only its paper-specific answer content.
- Do not replace the author/affiliation screenshot with a retyped author list in P0.
- Do not use any content layout other than `content_stacked` in P0.
- Do not use OCR or visual estimation to recover values for data redraw.
- Do not draw a chart for one isolated number; use text emphasis or the original paper asset.
- Do not leave placeholder tokens, missing assets, or unapproved visuals in the deliverable.

## Deliverables

Keep these together in the run directory:

```text
run-manifest.json
capabilities.json
paper-notes.json
deck-plan.json
assets/paper/
assets/one-page/one-page.html
assets/one-page/one-page.png
assets/tikz/
assets/data-viz/
assets/imagegen/
assets/external/
build/presentation.pptx
qa/overview.png              # optional
qa/approval-log.jsonl
qa/readability/manifest.json # optional; only overview/full
qa/readability/groups/       # optional; full mode only
```

Report what was automated, what was manually reviewed, unresolved risks, and the final deck path.
