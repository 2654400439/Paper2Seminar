# Local Web UI

The Streamlit application is a local task console. It stores every uploaded paper, template, configuration, prompt, log, and output in an isolated `runs/ui-*` directory.

The UI compiles all confirmed fields into the same versioned `job-request.json` used by Skill and CLI entry points. It does not maintain private defaults or ask the agent to reinterpret form values.

## Run

```text
python -m pip install -r requirements-ui.txt
streamlit run skills/paper-ppt-orchestrator/webapp/streamlit_app.py
```

The current execution adapter uses an installed and authenticated Codex CLI. The UI invokes `codex exec` with an argument array, sends the generated task prompt through standard input, uses the repository as the writable workspace, and records JSONL output in `agent.log`. It never accepts an arbitrary shell command from the browser.

Before the first complete job, authenticate the CLI and install the default extraction model:

```text
codex login
python skills/paper-ppt-orchestrator/scripts/paper_ppt.py download-layout-model
```

On Windows systems where PowerShell blocks the npm `.ps1` shim, run `& "$env:APPDATA\npm\codex.CMD" login`. The UI checks login status before creating a background job. Mutable YOLO and Matplotlib caches are scoped to `runs/<job>/.cache/`, while the verified model remains in the platform user cache.

## Implemented controls

- PDF upload, text-extractability check, fast title detection, and explicit title confirmation.
- Optional PPTX template upload.
- Presenter, advisor, language, target duration, and automatic or manual slide count.
- DocLayout-YOLO or CaptionCrop selection, inference device, threshold, and crop DPI.
- Declared image-generation and web-search capabilities.
- Final readability mode.
- Optional post-QA verbatim notes with target duration and drafting pace.
- Environment preflight, task status, logs, and artifact downloads.

## Reserved controls

Multiple automatic layouts, evidence footers, incremental rebuilds, generic template adaptation, and OpenCode/Claude Code execution adapters are visible but disabled. Reserved Paper2Seminar features are still recorded with `enabled=false` and `status=reserved`; provider adapters are a separate execution concern.

## Adapter boundary

`webapp/backend.py` owns validated job creation and the `CodexAdapter` command contract. `webapp/job_runner.py` is a detached process that owns the long-running agent call and durable status updates. Streamlit only reads files and starts the runner, so a browser refresh does not terminate an active task.

The adapter validates the confirmed request before starting the existing Agent Skill workflow; it does not duplicate paper comprehension in the web server. A successful process exit is insufficient: the runner reports completion only when `build/presentation.pptx` exists.

See [the job request contract](job-request.md) for interaction modes, extension rules, and the feature-registration checklist.
