# Visual selection

## Decision order

Choose the visual after the slide purpose and evidence are fixed.

1. Does the paper contain the exact evidence or method image the audience must inspect? Use `paper_asset`.
2. Does the slide explain a synthesized process, mechanism, relationship, or comparison not available as a readable paper figure? Use `tikz`.
3. Does the paper provide at least two comparable exact values in text or a selectable table, and does their relationship matter? Use `data_redraw`.
4. Is the slide conceptual background where a realistic visual improves orientation without carrying factual detail? Use `imagegen` when capability preflight marks it available. Otherwise, if licensed web-image search is available, use `external_image`.
5. Is the slide a reflection, limitation, discussion, quote, or question that is clearer without a main image? Use `none`.

For a complete deck, satisfy a small diversity floor across the deck: at least one conceptual visual (`imagegen`, or `external_image` only when the capability report selects the fallback), one `tikz` visual, and one faithful `data_redraw` visual. Meet this requirement during visual routing by choosing semantically appropriate slides. Do not force a mode onto an unsuitable slide or weaken evidence fidelity. P0 records this as a planning constraint and does not add a separate counting-only gate.

## `paper_asset`

Use for:

- Original method overview diagrams.
- Experimental charts and tables.
- Qualitative examples that must remain faithful to the paper.
- Results where values, axes, or legends are evidence.

Requirements:

- Asset must exist in CaptionCrop metadata or have an explicit manual crop record.
- Review the crop at the final slide size.
- Preserve or restate the source caption.
- Use `contain`; never distort.
- Record paper page and figure/table label.
- If the full table is unreadable, prefer a focused crop plus a textual takeaway. Do not silently redraw numbers without a verified data-redraw workflow.

## `tikz`

Use for:

- Multi-stage pipelines.
- Architecture summaries.
- Causal chains and threat models.
- Before/after or mechanism comparisons.
- Presenter-created synthesis across multiple paper sections.

Requirements:

- Read `tikz-layout.md` before generating.
- Declare the diagram as presenter synthesis when it is not copied from the paper.
- Keep `.tex`, `.pdf`, `.png`, and compile log.
- Compile with XeLaTeX and inspect the PNG.
- Prefer 6-10 nodes at most; move detailed explanation to slide text or notes.

Do not use TikZ to fabricate an experimental chart from visual estimation.

## `imagegen`

Use for:

- Conceptual background.
- A non-literal setting or metaphor.
- A cover or section opener when the template and user permit it.

Requirements:

- Never use on `results` slides.
- Avoid method slides unless the image is clearly decorative and cannot be mistaken for system structure.
- Prompt for no text, labels, logos, watermark, or numerical content.
- Save the prompt, chosen output, generation date/capability, and hash when practical.
- Inspect for misleading details, malformed objects, accidental text, and brand conflicts.
- Add alt text based on what the final image actually contains, not only the prompt.

If the execution tool is absent or returns a definitive unavailable/authentication error, record `imagegen: unavailable` and stop retrying that route. Use the capability report's next route.

## `external_image`

Use only as the conceptual-image fallback selected by capability preflight. It is not a substitute for a paper figure, experimental chart, or precise architecture diagram.

Requirements:

- Never use on `results` slides. Avoid method slides unless clearly decorative.
- Search for the intended concept, then open the source page and verify explicit reuse terms. Do not use a search-results thumbnail as the asset or source record.
- Prefer public-domain, Creative Commons, or clearly licensed stock sources. Do not assume that an image being publicly reachable grants reuse rights.
- Record `search_query` and an `external_source` object containing `page_url`, `license_name`, `license_url`, and `retrieved_at`. Record provider, creator, direct asset URL, SHA-256, and transformations when available.
- Download the original or a suitably high-resolution derivative into `assets/external/`; crop or resize without changing its factual meaning.
- Inspect for watermarks, visible personal data, misleading brands, accidental text, and details that could be mistaken for paper evidence.
- Credit the source in notes, a small caption, or the QA/source manifest when the license or context requires it.

## `none`

Use for:

- Limitations and open questions.
- Presenter reflection.
- A short quote, code fragment, or decision question.
- A transition where an image would add no information.

Requirements:

- Provide a rationale in the deck plan.
- Keep `none` below 20% of content slides unless the user explicitly requests a discussion-heavy deck.
- Do not leave an empty image placeholder on the final slide.

## `data_redraw`

Use only for a small set of exact values already available while the agent reads the paper and only when the chart communicates a relationship.

- Write a `data-viz.json` conforming to `data-viz.schema.json`.
- Require at least two comparable data points. Prefer a cross-method comparison, cross-dataset comparison, trend, distribution, heatmap, or compact result table.
- Keep one isolated value such as "up to 219x" in the slide text; a one-bar chart adds no information.
- Use paper text or selectable PDF table text. Do not use OCR.
- Do not estimate values from line height, bar length, or unlabeled geometry.
- Render with `render_data_viz.py` to a 2.1:1-2.7:1 PNG.
- If the spec exceeds 8 categories, 3 series, 6 table rows, or 5 table columns, simplify or use the paper asset.
- Prefer the original paper figure when it is already readable and carries axes, confidence intervals, or experimental context that a redraw would discard.
- Keep the spec and generated manifest beside the PNG.
- At least one `data_redraw` in a complete deck must be a faithful redraw of exact selectable paper values, with the original comparison semantics preserved. It may simplify presentation, but it must not estimate, interpolate, or alter the source values.

## P0 layout

All modes use `content_stacked`. Generate or crop visuals for the fixed lower image region rather than changing slide layout.
