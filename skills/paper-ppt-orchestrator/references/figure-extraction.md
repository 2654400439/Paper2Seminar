# Figure and table extraction

## Backend policy

`doclayout` is the default backend. It detects `figure` and `table` regions with DocLayout-YOLO, then renders those PDF regions at high resolution. It does not use OCR, caption interpretation, table-structure recovery, or an LLM.

`captioncrop` remains an explicit lightweight alternative. Select it only when the user requests the legacy route, model inference is unavailable, or its caption-driven crops are known to work better for the paper. Manual page crops remain the final fallback.

Run capability preflight first. A backend is usable only when its runtime, model, and command are actually available; the selected backend name is not evidence that extraction succeeded.

## Install and model setup

From the repository root, install the optional default backend and download the pinned model:

```powershell
python -m pip install -r requirements-doclayout.txt
python skills/paper-ppt-orchestrator/scripts/paper_ppt.py download-layout-model
```

For a standalone copied skill, install `requirements-doclayout.txt` inside the skill directory. The downloader stores the model in the platform user cache by default. Override it with `-o`, `PAPER_PPT_DOCLAYOUT_MODEL`, or `PAPER_PPT_CACHE_DIR` in managed environments.

The downloader uses a revision-pinned URL and verifies this SHA-256 before replacing the destination:

```text
9A2EE0220FE3D9AD31B47E1D9F1282F46959A54E4618FCE9CFFCC9715B8286E2
```

The `.pt` format uses PyTorch pickle loading. Do not load an untrusted file. `--allow-unverified-model` exists only for an explicitly trusted custom model and must not be used to bypass an unexplained mismatch.

## Default extraction

```powershell
python scripts/paper_ppt.py extract-assets PAPER.pdf -o RUN/assets/paper/extracted --clean
```

Defaults:

| Parameter | Value | Purpose |
| --- | ---: | --- |
| `--confidence` | `0.18` | Favor recall before review and filtering |
| `--image-size` | `1024` | Match the tested CPU inference profile |
| `--detection-dpi` | `144` | Bound page-render memory and inference time |
| `--crop-dpi` | `300` | Keep labels and thin lines readable in slides |
| `--padding-points` | `5` | Avoid clipping borders, arrows, and legends |
| `--dedupe-iou` | `0.75` | Remove only near-identical same-class boxes |
| `--device` | `cpu` | Portable default; use a verified accelerator explicitly |

The model is loaded once per command and reused for every page. Detection uses the 144 DPI page image; accepted boxes are mapped back to PDF points and rendered directly from the PDF clip at 300 DPI. Tables whose native PDF text begins with `Algorithm N` are rejected as common false positives. This filter does not work on image-only scans.

## CaptionCrop compatibility

```powershell
python scripts/paper_ppt.py extract-assets PAPER.pdf -o RUN/assets/paper/extracted `
  --backend captioncrop --captioncrop-command PATH/TO/caption_crop.py --clean
```

When `--captioncrop-command` is omitted, the wrapper searches PATH for `caption-crop`, `captioncrop`, or `caption_crop.py`. It passes `--dpi 240 --contact-sheet` and preserves CaptionCrop's native metadata contract. Do not reinterpret that metadata as a DocLayout manifest.

## DocLayout output contract

```text
extracted/
|-- crops/
|-- annotated_pages/
|-- contact_sheet.jpg
|-- manifest.csv
|-- manifest.json
`-- summary.json
```

Every accepted `manifest.json` record includes a stable per-kind ID, 1-based page, confidence, padded PDF-point box, original detection-pixel box, output dimensions, relative file path, and `unreviewed` status. It intentionally omits absolute crop paths. `summary.json` records the PDF and model hashes, parameters, totals, the deduplicated count, and rejected invalid/Algorithm detections.

Review `contact_sheet.jpg`, then inspect extreme aspect ratios at original size. Detection is candidate generation, not approval. Record every selected asset's paper label and page in the paper inventory/deck plan, and mark rejected or adjusted crops explicitly.

## Known limits

- Multi-page tables remain separate page crops.
- Adjacent non-overlapping subfigures are not merged.
- A 5-point margin may include a small amount of caption or nearby text.
- Scanned PDFs do not support the native-text Algorithm filter.
- Non-standard layouts can still produce missed or incorrect boxes.
- DocLayout-YOLO, its package, and the pinned PDF-Extract-Kit model are AGPL-3.0 components. Confirm that their use and deployment fit the project before distributing a combined service or environment.

## Optional real-model regression

The ordinary suite uses a fake predictor and does not require model downloads. Maintainers with the two non-redistributed regression papers can run the real baseline by setting `PAPER_PPT_TEST_DOCLAYOUT_MODEL`, `PAPER_PPT_TEST_CLEARING_PDF`, and `PAPER_PPT_TEST_DIFFICULT_PDF`, then running:

```powershell
python -m unittest discover -s tests -p test_doclayout_regression.py -v
```

The expected results are `7 figures + 3 tables` with no duplicate removed, and `10 figures + 12 tables` with one duplicate removed. Each paper must also record exactly one rejected `algorithm_block`.
