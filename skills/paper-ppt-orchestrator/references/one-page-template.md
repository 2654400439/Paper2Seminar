# Fixed one-page HTML contract

## Canonical asset

Use `assets/one-page-summary.html` as the only P0 one-page template. It is a fixed three-column table with five required dimensions:

1. 问题归类
2. 威胁模型
3. 边界与局限
4. 组内启发
5. 算法学习

Do not replace this table with a dashboard, poster, card grid, Matplotlib composition, or newly designed HTML.

## Per-run procedure

1. Copy the pristine asset to `RUN/assets/one-page/one-page.html`.
2. Preserve the CSS, page width, header, subtitle, table columns, row order, row labels, warning rule, and footer.
3. Keep the second-column questions unchanged.
4. Replace only the example/answer content in the third column with paper-specific material. Replace the problem tags in the first answer row as needed, but keep the tag styling.
5. Fill every dimension with specific content grounded in the paper. Do not leave blanks, underscores, placeholder examples, or generic advice.
6. Render the completed HTML in a real browser and screenshot the complete `.page` element at high resolution, preferably at 2x device scale.
7. Save the rendered asset as `RUN/assets/one-page/one-page.png` and use it for `project.one_page_image`.

Use the bundled deterministic renderer after filling the per-run HTML:

```powershell
python scripts/paper_ppt.py render-one-page-html RUN/assets/one-page/one-page.html `
  -o RUN/assets/one-page/one-page.png
```

The renderer discovers Chromium-family browsers through `--browser`, `PAPER_PPT_BROWSER`, `CHROME_PATH`/`EDGE_PATH`, `PATH`, and common Windows, macOS, and Linux install locations. It validates the five required rows, tries modern headless mode once and a compatibility mode once per discovered browser, screenshots at 2x scale, removes the gray outer page background, and writes the selected browser, strategy, and attempt diagnostics to the manifest. Use `--allow-no-sandbox` only for an isolated CI container that requires it; it is never enabled by default.

## Content expectations

- **问题归类**: identify the paper's actual research theme, not merely “other.”
- **威胁模型**: state attacker, target, capabilities/knowledge, attack path, and the authors' offensive or defensive role.
- **边界与局限**: state operating assumptions, unsupported cases, and evidence limits.
- **组内启发**: connect the work to the group's research, reusable mechanisms, data/tool requirements, and realistic adoption cost.
- **算法学习**: name the central algorithmic or optimization ideas, explain the learning route, cite related families when useful, and state what could be reproduced or improved.

## Render QA

- The screenshot contains exactly one complete table with three columns and five body rows.
- No table edge, footer, warning rule, or row content is clipped.
- The screenshot does not include browser chrome or the gray outer page background.
- The rendered style matches the canonical asset; visual differences are limited to natural row-height changes caused by replacement text.
- The image remains readable when contained in slide 3's image region.

If the HTML cannot be rendered, stop and report the renderer blocker. Do not silently create a substitute design.
