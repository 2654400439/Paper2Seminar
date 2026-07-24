# Third-party components

This repository integrates with, but does not redistribute, OfficeCLI, CaptionCrop, Chromium-family browsers, TeX distributions, Poppler, LibreOffice, Microsoft PowerPoint, DocLayout-YOLO, or its model weights. Installations of those tools and their licenses are managed separately.

The optional default figure/table extraction backend uses the `doclayout-yolo` package and the `doclayout_yolo_ft.pt` model from OpenDataLab's PDF-Extract-Kit-1.0. Both sources declare AGPL-3.0 licensing. The repository downloader fetches a revision-pinned model and verifies its SHA-256; it does not grant additional model rights. The backend is imported only when selected, but users remain responsible for confirming that installation, deployment, and distribution comply with the applicable licenses.

Python dependencies are declared in `requirements.txt` and remain under their respective licenses.

The MIT License in this repository covers repository-authored code and documentation. The bundled PPTX retains UCAS names and marks and default presenter/advisor metadata; those elements are not relicensed under MIT. The repository also does not grant rights to source papers, publisher figures, externally downloaded images, model-generated assets, or presentations produced by users.
