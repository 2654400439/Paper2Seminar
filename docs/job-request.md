# Job request contract

`job-request.json` is the provider-neutral input contract shared by the Web UI, conversational Skill intake, and CLI automation. It records what the user requested; it does not contain the agent's paper interpretation or slide decisions. Those belong in `paper-notes.json` and `deck-plan.json`.

## Contract files

- `references/job-request.schema.json`: structural and type validation.
- `references/job-request.defaults.json`: named profiles and the only executable default values.
- `references/feature-registry.json`: optional feature IDs, availability, workflow stage, default state, and UI metadata.

A confirmed request is immutable. Runtime capability discoveries go to `capabilities.json`, progress goes to status/event artifacts, and semantic decisions go to the deck plan.

## Interaction modes

| Mode | Intended caller | Behavior |
|---|---|---|
| `non_interactive` | Confirmed Web UI jobs, CI, explicit default execution | Never block for routine questions; fail structurally when the request cannot be honored |
| `confirm_once` | Normal conversational Skill invocation | Perform cheap inspection, show one execution brief, and wait once before expensive work |
| `guided` | User-requested collaborative runs | Pause at intake, plan, assets, slides, and final checkpoints |

The Web UI always writes `source=web_ui`, `mode=non_interactive`, and `confirmed=true`. It has already collected the user's choices, so the agent must not ask for them again.

## Feature envelope

Every optional feature uses the same outer shape:

```json
{
  "enabled": false,
  "status": "reserved",
  "config": {}
}
```

The controller and agent execute a feature only when `enabled=true` and `status=available`. Reserved features remain in the request snapshot so UI, logs, and future migrations can explain what was visible but unavailable.

To add a new feature:

1. Add its ID and UI metadata to `feature-registry.json`.
2. Add its default envelope to every profile in `job-request.defaults.json`.
3. Add a typed schema definition when its `config` has a stable contract; otherwise the generic object envelope is sufficient during early development.
4. Add or update the Skill reference that defines execution behavior and stage ownership.
5. Mark `ui_control=custom` for a dedicated UI editor, or use `toggle` for a generic feature switch.
6. Add tests covering registry/default synchronization, valid compilation, and reserved-feature rejection.

Provider-specific or experimental data that is not a Paper2Seminar feature belongs under a namespaced `extensions` key such as `org.example_option`; do not add arbitrary top-level properties.

## Commands

```text
python scripts/paper_ppt.py job-request defaults
python scripts/paper_ppt.py job-request init ...
python scripts/paper_ppt.py job-request brief RUN/job-request.json
python scripts/paper_ppt.py job-request confirm RUN/job-request.json
python scripts/paper_ppt.py job-request validate RUN/job-request.json
```
