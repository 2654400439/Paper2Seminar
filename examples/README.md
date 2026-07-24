# Sample decks

This directory contains complete, editable outputs from Paper2Seminar and the images used by the README gallery.

| Sample | Source paper | Slides | PPTX | Full overview |
|---|---|---:|---|---|
| WebCloak | *WebCloak: Characterizing and Mitigating Threats from LLM-Driven Web Agents as Intelligent Scrapers* · IEEE S&P 2026 | 32 | [Download](decks/webcloak-seminar.pptx) | [Open](gallery/webcloak-overview.png) |
| Beyond RTT | *Beyond RTT: An Adversarially Robust Two-Tiered Approach for Residential Proxy Detection* · NDSS 2026 | 30 | [Download](decks/beyond-rtt-seminar.pptx) | [Open](gallery/beyond-rtt-overview.png) |

## Validation

Both sample decks were checked with:

```text
officecli validate <sample.pptx>
officecli view <sample.pptx> issues
officecli view <sample.pptx> stats
```

At the time of inclusion:

- both files passed OpenXML validation;
- OfficeCLI reported zero issues;
- WebCloak contained 32 slides and Beyond RTT contained 30 slides;
- all inserted pictures had alt text.

The gallery images are direct slide renders and deck overviews. They are not separate redesigns made for marketing.

## Content and rights

The sample decks are generated research-discussion materials. They summarize the named papers and include selected paper figures, tables, and bibliographic information for educational demonstration. Copyright in the source papers and their figures remains with the respective authors and publishers; those materials are not relicensed under this repository’s MIT License.

Do not treat these samples as official author presentations or authoritative summaries. Verify claims against the original papers before reuse, presentation, or redistribution.
