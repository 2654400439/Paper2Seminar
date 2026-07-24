# End-to-end workflow

## Stage artifacts

Treat each stage output as immutable input to the next stage. When upstream content changes, invalidate downstream assets instead of silently reusing them.

```text
paper PDF + template + user brief
  -> run-manifest.json
  -> paper-notes.json + subsection coverage matrix + figure inventory
  -> title sequence
  -> deck-plan.json
  -> filled fixed one-page HTML + PNG
  -> approved visual assets
  -> presentation.pptx
  -> rendered slides + qa/report.md
```

## Stage 0: run manifest and preflight

Create one run directory per paper. Record:

- Input PDF and template paths.
- Input file hashes when practical.
- Output path.
- Build date and tool versions.
- Language, target duration, and target slide count.
- Paper profile and the slide-count range derived from `deck-sizing.md`.
- Available renderers and visual generators.

Inspect the agent's actual tool inventory, then write a capability report before visual routing:

```powershell
python scripts/paper_ppt.py preflight -o RUN/capabilities.json `
  --imagegen unavailable --web-search available
```

Use `available`, `unavailable`, or `unknown`. Python can probe host executables, but it cannot infer whether the current agent session exposes an internal image-generation or web-search tool. Declare those two capabilities from the session inventory. Resolve `unknown` once; do not probe a definitively absent tool through repeated calls.

Verify the PDF contains extractable text. Inspect the template instead of relying on remembered slide numbers.

## Stage 1: paper understanding and content inventory

Read the entire paper before drafting slides. Produce structured notes containing:

- Metadata and bibliographic facts.
- Research problem and why it matters.
- Key concepts and assumptions.
- Method components and their dependencies.
- Datasets, baselines, metrics, and experimental setup.
- Main quantitative results with units and comparison baselines.
- Limitations, threats to validity, and open questions.
- Candidate claims and a small set of exact values that may need data redraw.
- A subsection coverage matrix that maps every core method subsection, named RQ, primary experiment, and limitation to slides, notes, or an approved omission.

When practical, distinguish:

- `paper_claim`: explicitly supported by the paper.
- `presenter_analysis`: interpretation, analogy, criticism, or transfer insight.

Never present the second type as the first.

Prefer CaptionCrop from its repository or installed CLI. If it is unavailable, render only the required PDF pages, crop selected regions with `scripts/crop_image_region.py`, record source page and bounding box in the run manifest, and create a contact sheet with `scripts/make_contact_sheet.py`.

```powershell
python caption_crop.py PAPER.pdf -o OUTPUT --dpi 240 --clean --contact-sheet
```

Parse `metadata.json`, inspect `contact_sheet.png`, and assign review status to every candidate asset. Keep rejected crops in metadata; do not select them for slides.

Crop the paper's author and affiliation band for the paper-information slide:

```powershell
python scripts/paper_ppt.py crop-authors PAPER.pdf -o assets/paper/author-affiliations.png --title "PAPER TITLE"
```

Automatic detection uses the title bottom and Abstract/Introduction start as vertical anchors. If either anchor is wrong, inspect page 1 and rerun with `--bbox x0,y0,x1,y1`; do not fall back to retyping authors unless the PDF is not renderable.

## Stage 2: narrative and deck plan

Create the ordered title sequence before slide body text. The sequence must tell a coherent story when read alone.

Default four-section questions:

1. `background`: What problem exists, and what knowledge is needed to understand it?
2. `method`: What did the authors build or propose, and how does it work?
3. `results`: How was it evaluated, and what evidence supports the claims?
4. `reflection`: What is convincing, limited, reusable, or still unanswered?

Budget slides from paper complexity first and talk duration second. For a full 12-16+ page two-column paper, normally plan 26-32 total slides; for a measurement study plus a new method/system, normally plan 28-32. Reserve time for transitions and questions, but do not compress central methods or experiments merely to hit an arbitrary duration.

Create `deck-plan.json` using `deck-plan.schema.json`. Each content slide must have one purpose, one takeaway, `content_stacked` layout, and an estimated 5-6 body lines. Use 18pt bold titles. Keep the first run of every body bullet black. Write each paper contribution as regular-weight rich-text runs occupying about two lines, with only selected phrases bold. Evidence IDs are optional in P0 and become a P1 requirement for key claims.

Review checkpoint A:

- Title sequence.
- Section balance.
- Major claims and missing evidence.
- Coverage matrix, paper profile, and any approved omissions.
- Proposed visuals and any expensive generated assets.

## Stage 2.5: fixed one-page table

Copy `assets/one-page-summary.html` to the run directory, fill the five paper-specific answer rows, and render the complete `.page` element in a browser. Preserve the canonical CSS and table structure. Use the resulting PNG on slide 3; do not recreate the layout with Matplotlib, Pillow, or a newly designed HTML page.

## Stage 3: visual routing and asset generation

Apply `visual-selection.md`. Record the decision before generating the asset.

Generate assets into source-specific directories:

```text
assets/paper/
assets/tikz/
assets/data-viz/
assets/imagegen/
assets/external/
```

Keep editable sources next to rendered outputs. Do not flatten TikZ to PNG and discard the `.tex` file. Keep image-generation prompts with the chosen PNG.

For conceptual visuals, follow the capability report. Use `imagegen` when available. When it is unavailable and web search is available, use `external_image`, download a reusable original asset, and record the query plus license/provenance fields required by the deck-plan schema. If neither route is available, use a truthful TikZ synthesis or `none`; do not keep retrying image generation.

For `data_redraw`, write the few exact values needed for the slide into `data-viz.json` while reading the paper. Require at least two comparable points and a meaningful comparison, trend, distribution, or matrix. Use paper text or selectable table text only. Do not run OCR or infer values from unlabeled geometry.

Review checkpoint B:

- Reviewed figure-extraction contact sheet and selected crops.
- TikZ PNGs at slide size.
- Generated images and their prompts.
- External images, source pages, and reuse terms.
- Any page using `none`.

After the selected assets pass standalone review, record the transition without manually rewriting plan state:

```powershell
python scripts/paper_ppt.py approve-assets deck-plan.json --all-content `
  --note "standalone assets reviewed"
```

## Stage 4: assembly

Always start from the pristine template. Use the canonical placeholder mapping in `template-contract.md`.

Build in audience order:

```text
cover
paper information
one-page summary
contents
section divider
section content slides
...
closing
```

Clone the correct section-specific content slide for every added content page. Update the presentation slide list instead of overwriting subsequent template slides.

Add speaking context to speaker notes and alt text to every inserted picture. Formal source anchors are optional in P0.

## Stage 5: QA and final approval

Run all required structural gates in `qa-gates.md`. Final-size readability rendering is a separate optional stage with three modes:

- `off` (default): do not export or read slide screenshots.
- `overview`: create one deck-wide image for gross layout defects.
- `full`: create group images containing at most four slides and inspect every group for final-size readability.

Persist the choice with optional `project.final_readability_mode`; absence means `off`. When enabled, the default manifest path is `qa/readability/manifest.json`.

Review checkpoint C:

- Final title sequence and page count.
- Optional readability evidence only when mode is `overview` or `full`.
- Unresolved crop, font, renderer, or citation issues.
- Final PPTX opened in the target presentation viewer.

After review, use `approve-slides` to atomically approve the selected content and visuals and append the audit log. Do not set `qa_status` and review booleans independently.

```powershell
python scripts/paper_ppt.py approve-slides deck-plan.json --all-content `
  --note "final review complete"
```

Preserve the plan, `qa/approval-log.jsonl`, and QA report with the deck. They are part of the deliverable, not temporary build files.
