# Template contract

## Current template inventory

The bundled template is 16:9 and contains 13 slides:

| Template slide | Role | Canonical use |
|---:|---|---|
| 1 | Cover | Replace Chinese and English paper titles plus presenter metadata |
| 2 | Paper information | Paper title, author/affiliation screenshot, venue/year, contributions |
| 3 | One-page summary | Insert a browser render of the bundled fixed HTML table |
| 4 | Contents | Keep the four fixed sections unless the user changes the talk structure |
| 5 | Section 1 divider | Background divider |
| 6 | Section 1 content | Clone for every background content slide |
| 7 | Section 2 divider | Method divider |
| 8 | Section 2 content | Clone for every method content slide |
| 9 | Section 3 divider | Results divider |
| 10 | Section 3 content | Clone for every results content slide |
| 11 | Section 4 divider | Reflection divider |
| 12 | Section 4 content | Clone for every reflection content slide |
| 13 | Closing | Closing text and presenter metadata |

Do not rely on these numbers without preflight. Verify the roles against tokens and visual structure for every template version.

## Canonical placeholder mapping

The current template uses legacy text tokens. Treat canonical names as the public contract and legacy tokens as an adapter:

| Canonical name | Current token | Role |
|---|---|---|
| `PPW_TITLE_CN` | `{{TITLE_CN}}` | Chinese paper title |
| `PPW_TITLE_EN` | `{{TITLE_EN}}` | English paper title |
| `PPW_SOURCE_YEAR` | `{{Source Year}}` | Venue and year |
| `PPW_CONTRIBUTIONS` | `{{Contributions}}` | Level-1 hollow-square contribution bullets under the preserved `本文贡献：` heading |
| `PPW_AUTHOR_VISUAL` | `{{IMG_author}}` | Required author and affiliation screenshot |
| `PPW_ONE_PAGE_IMAGE` | `{{IMG_YY_one_page}}` | One-page summary image |
| `PPW_CONTENT_TITLE` | `{{sub_title_en}}` | Content-slide title, not necessarily English |
| `PPW_CONTENT_BODY` | `{{something_en}}` | Rich-text bullet region, not necessarily English |
| `PPW_CONTENT_VISUAL` | `{{IMG_padding}}` | Main visual region |

Preflight must find exactly one required token in each applicable template slide. Zero or multiple matches are errors.

## One-page HTML template

- Canonical source: `assets/one-page-summary.html`.
- Preserve its three columns, five required dimensions, CSS, title, subtitle, warning rule, and footer.
- Modify only a per-run copy and replace only paper-specific answer/example content.
- Render the `.page` element in a browser and insert the PNG with `contain`.
- Reject a one-page image produced from an alternative dashboard, poster, card, Matplotlib, or free-form HTML design.

## Current content-slide geometry

Measured from slide 6:

- Slide title: x `374669 EMU`, y `1016420 EMU`, width `9895727 EMU`, height `458908 EMU`.
- Body placeholder: x `374668 EMU`, y `1470294 EMU`, width `11680697 EMU`, height `456535 EMU`.
- Visual placeholder: x `2817125 EMU`, y `3934835 EMU`, width `6557749 EMU`, height `2695432 EMU`, approximately `18.2 cm x 7.5 cm`.
- Template content-title placeholder may inherit 28pt. Generated titles must explicitly use 18pt bold.
- Template body placeholder effective size: 28pt. Generated body must explicitly use 18pt unless a tested template variant specifies otherwise.

The body placeholder height is only a seed. The builder may expand it using bounded layout rules, but it must preserve the top navigation and page footer.

## P0 layout

P0 supports only `content_stacked`: an 18pt bold title, normally 3 body bullets totaling 5-6 rendered lines at 18pt, and one lower visual region. Body bullet markers remain black; the first run may be black bold but never accent-colored. The builder expands the title and body seed boxes to fixed safe dimensions but does not change the overall composition. Unsupported layouts are rejected during plan validation.

## Mutation rules

- Copy the source template before mutation.
- Clone a section's content template; do not repaint another section's navigation state.
- Preserve slide master/layout relationships, theme, aspect ratio, and transition unless intentionally changed.
- Generate new unique slide and shape IDs.
- Update `[Content_Types].xml`, presentation relationships, slide relationships, notes relationships, and media relationships when working at raw OOXML level.
- Insert new slides into `presentation.xml` in audience order.
- Recompute visible page numbers after all insertions.
- Use stable semantic shape names in template v2; do not rely on names such as `矩形 45`.

## Image placement

- Paper crop, table, screenshot, logo, and TikZ: `contain`, centered, never stretched.
- Conceptual full-bleed image: `cover` only when the selected layout explicitly supports it.
- Keep a paper caption inside the crop or add a readable PPT caption with source reference.
- Reject assets whose effective text becomes unreadable at the actual placeholder size.

## Template preflight output

Write a template inventory containing:

- File hash and slide size.
- Slide count and role mapping.
- Token-to-shape mapping with IDs and geometry.
- Fonts used and missing-font warnings.
- Supported layouts.
- Renderer used for the preview.
- Schema and visual-check results.
