# QA gates

Gates 0-3 are required. Gate 4 final-size readability rendering is optional and defaults to `off`.

## QA state contract

- `planned`: the visual route is selected, but the asset is not approved for assembly.
- `ready`: the asset exists and passed standalone crop/render/source review.
- `approved`: an explicit final slide approval was recorded.
- `rejected`: the asset must be replaced or rerouted before it can return to review.

Use `approve-assets` for `planned -> ready`. Use `approve-slides` for `ready -> approved`; it sets both final review booleans in the same atomic plan update and appends `qa/approval-log.jsonl`. It refuses to approve `planned` or `rejected` visuals. Do not infer approval from file existence or automatically promote state after rendering.

Final-size readability mode changes the evidence used for final visual approval, not the required asset checks:

- `off`: approve from the fixed template contract, standalone assets, structural gates, and explicit human/agent review without slide screenshot export.
- `overview`: additionally inspect one deck-wide overview for gross defects.
- `full`: additionally inspect all group images, with at most four slides per image.

## Gate 0: reproducibility

- Run manifest exists.
- Capability report exists and records agent-declared `imagegen` and `web_search` states before visual routing.
- Input PDF and template paths resolve.
- Tool versions and template hash are recorded.
- Build starts from the pristine template.
- All generated assets are inside the run directory or referenced by stable paths.
- The one-page HTML is a per-run copy of the bundled canonical template.

Failure blocks assembly.

## Gate 1: plan

Run:

```powershell
python scripts/validate_deck_plan.py deck-plan.json --stage plan
```

Then verify:

- Title sequence is coherent when read alone.
- Paper profile and complexity-derived slide range are recorded.
- A full 12-16+ page two-column paper has 26-32 total slides by default; a lower count has an explicit short-talk request or approved omission list.
- The subsection coverage matrix maps every core method subsection, named RQ, primary experiment, and limitation to slides or notes.
- All four sections have content.
- Every content slide is estimated at 5-6 rendered body lines.
- Every contribution statement occupies about two lines in the paper-information template.
- The `本文贡献：` heading remains intact; every contribution is a separate hollow-square item with regular-weight body text and selective bold emphasis.
- Every content title is 18pt bold, and every body bullet marker is black.
- Numerical claims include metric, unit, baseline, and condition where applicable.
- Generated or external conceptual-image use obeys the factual boundary and the capability report.

Evidence IDs are optional in P0. P1 may require source anchors for key numerical and experimental claims.

Failure returns to planning, not slide assembly.

## Gate 2: asset quality

### Fixed one-page HTML

- Source HTML is `assets/one-page-summary.html` or a byte-identical pristine copy before content replacement.
- CSS, title, subtitle, three columns, five row labels, warning rule, and footer are preserved.
- Only paper-specific answer/example content is replaced.
- Browser screenshot contains the complete `.page` element with no outer gray background, browser chrome, placeholder examples, blanks, or clipping.
- Alternative one-page layouts are rejected even if visually polished.

### Paper assets

- Author/affiliation crop contains the full names and institutions but excludes the paper title and Abstract/body text.
- Figure extraction metadata and a reviewed contact sheet exist, whether produced by the default DocLayout backend, CaptionCrop compatibility mode, or the documented manual-crop fallback.
- The extraction backend, parameters, PDF hash, and model hash when applicable are recorded.
- Duplicate same-class detections and `Algorithm N` false tables are absent from selected assets.
- Every selected crop is reviewed.
- Crop contains the intended figure/table and no unrelated paragraph or page header.
- Axis labels, legends, and table text remain readable at slide size.
- Source page and label are recorded.

### TikZ

- `.tex`, `.pdf`, `.png`, and log exist.
- XeLaTeX exits successfully.
- Log contains no critical `Overfull`, `Missing`, `Error`, or relevant `Warning`.
- PNG has no node, arrow, label, note, or text overlap.
- Effective aspect ratio matches the selected slide layout.

### Generated images

- Prompt and chosen output are recorded.
- No accidental text, logo, watermark, malformed focal object, or misleading technical detail appears.
- Image is not used as factual evidence.

Failure regenerates or reroutes the visual.

### External images

- Capability preflight records image generation as unavailable and web search as available.
- Search query, source page, reuse license, license URL, and retrieval date are present in the deck plan.
- The downloaded original or derivative exists inside `assets/external/`; a search thumbnail or hotlink is rejected.
- Creator/provider, direct asset URL, SHA-256, and transformations are recorded when available.
- No unintended watermark, misleading brand cue, personal data beyond the configured presenter/advisor fields, or detail that could be mistaken for paper evidence appears.
- The image is used only as conceptual context, never as experimental evidence or a precise method diagram.

### Data redraw

- Values come from paper text or selectable table text, not OCR.
- At least two comparable values are present and the visual communicates a comparison, trend, distribution, or matrix; a lone number is rejected.
- `data-viz.json`, PNG, and manifest exist.
- Chart type, category count, series count, canvas ratio, and finite-value checks pass.
- If exact values cannot be established, use the paper crop instead.

## Gate 3: assembly structure

Run the installed PPTX backend's schema validation. At minimum verify:

- PPTX opens without repair prompt.
- Slide order matches the deck plan.
- Every section divider precedes its content.
- Page numbers are sequential.
- No slide or relationship ID collision exists.
- All picture relationships resolve.
- Notes and alt text exist where required.
- No placeholder token remains.
- No missing font or fallback changes the expected layout.

When OfficeCLI is available:

```powershell
officecli validate presentation.pptx
officecli view presentation.pptx issues
officecli view presentation.pptx text
officecli query presentation.pptx 'picture:no-alt'
```

Any schema error, issue, placeholder token, or missing alt text blocks delivery.

## Optional Gate 4: final-size readability

Default mode is `off`. Do not render the deck or read slide images in this mode.

Use `overview` when the user wants a low-cost gross-layout check. Render every slide once and combine all pages into one high-resolution overview image.

Use `full` only when final-size text and embedded-label readability justify the extra cost. Render every slide once, group at most four slides per review image, and inspect each group exactly once. A 30-slide deck normally produces eight group images instead of 30 separate reads.

Run either mode explicitly:

```powershell
python scripts/paper_ppt.py readability --mode overview `
  --pptx build/presentation.pptx -o qa/readability

python scripts/paper_ppt.py readability --mode full `
  --pptx build/presentation.pptx -o qa/readability --group-size 4
```

Preferred order:

1. Microsoft PowerPoint PDF/image export.
2. LibreOffice headless export.
3. OfficeCLI screenshot.
4. HTML/text fallback only as an explicitly incomplete check.

Use the overview to inspect:

- Shape, text, image, caption, and footer overlap.
- Text or image clipping.
- Narrow boxes creating excessive wraps.
- Grossly unreadable embedded visuals.
- Low contrast.
- Stretched or incorrectly cropped images.
- Missing arrowheads or ambiguous flow direction.
- Captions colliding with page numbers.
- Uneven margins, gaps, alignment, or visual weight.
- Inconsistent section-navigation state.
- Wrong order or duplicated slides.

The overview is effective for 30-40 slides when kept at roughly 4K width with 6 columns and slide-number labels. It is not a replacement for `full` fine-text proofreading.

Write one line per obvious problem:

```text
slide 08: paper table text is unreadable at the current 18.2 cm width
slide 14: TikZ feedback arrow overlaps the result node
```

Only rerender when the overview reveals an obvious failure. Do not run an automatic multi-cycle visual loop by default.

## Gate 5: final content review

- Open the deck in the presentation viewer used for the talk.
- Confirm charts, fonts, transitions, notes, and page numbers.
- Read all titles in order.
- Spot-check every numerical claim against the paper.
- Confirm discussion and limitation statements are correctly attributed.
- Confirm the deck fits the target talk duration.

Record approvals through the transition command, then run:

```powershell
python scripts/paper_ppt.py approve-slides deck-plan.json --all-content `
  --note "final review complete"
```

When `project.final_readability_mode` is `overview` or `full`, the command and final validator require the matching readability manifest and evidence files. Then run:

```powershell
python scripts/validate_deck_plan.py deck-plan.json --stage final
```

Only then mark the run complete.
