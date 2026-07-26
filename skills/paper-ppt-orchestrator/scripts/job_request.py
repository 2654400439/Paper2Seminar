#!/usr/bin/env python3
"""Compile and validate provider-neutral Paper2Seminar job requests."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
import jsonschema


SKILL_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = SKILL_ROOT / "references"
SCHEMA_PATH = REFERENCE_DIR / "job-request.schema.json"
DEFAULTS_PATH = REFERENCE_DIR / "job-request.defaults.json"
FEATURE_REGISTRY_PATH = REFERENCE_DIR / "feature-registry.json"


class JobRequestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobRequestError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise JobRequestError(f"{path.name} must contain a JSON object")
    return value


def load_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    schema = load_json(SCHEMA_PATH)
    defaults = load_json(DEFAULTS_PATH)
    registry = load_json(FEATURE_REGISTRY_PATH)
    validate_contract(defaults, registry)
    return schema, defaults, registry


def validate_contract(defaults: dict[str, Any], registry: dict[str, Any]) -> None:
    if defaults.get("schema_version") != registry.get("schema_version"):
        raise JobRequestError("defaults and feature registry schema versions differ")
    default_profile = defaults.get("default_profile")
    profiles = defaults.get("profiles")
    if not isinstance(profiles, dict) or default_profile not in profiles:
        raise JobRequestError("default profile is missing")
    registered = registry.get("features")
    if not isinstance(registered, dict) or not registered:
        raise JobRequestError("feature registry is empty")
    registered_ids = set(registered)
    for profile_name, profile in profiles.items():
        features = profile.get("features") if isinstance(profile, dict) else None
        if not isinstance(features, dict) or set(features) != registered_ids:
            raise JobRequestError(
                f"profile '{profile_name}' features must exactly match the feature registry"
            )
        for feature_id, metadata in registered.items():
            value = features[feature_id]
            if value.get("status") != metadata.get("status"):
                raise JobRequestError(
                    f"feature '{feature_id}' status differs between profile and registry"
                )
            if value.get("enabled") != metadata.get("default_enabled"):
                raise JobRequestError(
                    f"feature '{feature_id}' default differs between profile and registry"
                )
            if metadata.get("status") == "reserved" and value.get("enabled"):
                raise JobRequestError(f"reserved feature '{feature_id}' cannot be enabled")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_paper_file(
    path: Path,
    title: str,
    title_cn: str = "",
    *,
    title_confirmed: bool = True,
) -> dict[str, Any]:
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise JobRequestError(f"cannot open paper PDF: {exc}") from exc
    try:
        if document.page_count < 1:
            raise JobRequestError("paper PDF has no pages")
        return {
            "path": str(path.resolve()),
            "original_filename": path.name,
            "sha256": sha256_file(path),
            "page_count": document.page_count,
            "text_extractable": bool(document[0].get_text("text").strip()),
            "detected_title": title.strip(),
            "confirmed_title": title.strip(),
            "title_cn": title_cn.strip(),
            "title_confirmed": title_confirmed,
        }
    finally:
        document.close()


def interaction_checkpoints(mode: str) -> list[str]:
    return {
        "non_interactive": ["final"],
        "confirm_once": ["intake", "final"],
        "guided": ["intake", "plan", "assets", "slides", "final"],
    }[mode]


def compile_request(
    *,
    job_id: str,
    paper: dict[str, Any],
    template: dict[str, Any],
    paths: dict[str, str],
    configuration: dict[str, Any],
    source: str,
    interaction_mode: str,
    confirmed: bool,
    profile_name: str | None = None,
    agent_adapter: str = "codex",
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema, defaults, registry = load_contract()
    selected_profile = profile_name or str(defaults["default_profile"])
    profiles = defaults["profiles"]
    if selected_profile not in profiles:
        raise JobRequestError(f"unknown job profile: {selected_profile}")
    profile = copy.deepcopy(profiles[selected_profile])

    presentation = profile["presentation"]
    for key in (
        "language",
        "target_minutes",
        "slide_count_mode",
        "target_slide_count",
        "presenter",
        "advisor",
    ):
        if key in configuration:
            presentation[key] = configuration[key]

    extraction = profile["extraction"]
    extraction.update(configuration.get("extraction", {}))
    visuals = profile["visuals"]
    visuals.update(configuration.get("visual_capabilities", {}))
    features = profile["features"]

    notes_override = configuration.get("speaker_notes", {})
    if notes_override:
        features["speaker_notes"]["enabled"] = bool(notes_override.get("enabled", True))
        features["speaker_notes"]["config"].update(
            {key: value for key, value in notes_override.items() if key != "enabled"}
        )
    readability_mode = configuration.get("readability_mode")
    if readability_mode is not None:
        features["readability"]["enabled"] = readability_mode != "off"
        features["readability"]["config"]["mode"] = readability_mode

    feature_overrides = configuration.get("features", {})
    if not isinstance(feature_overrides, dict):
        raise JobRequestError("configuration.features must be an object")
    for feature_id, override in feature_overrides.items():
        if feature_id not in registry["features"]:
            raise JobRequestError(
                f"feature '{feature_id}' is not registered; add it to feature-registry.json first"
            )
        if not isinstance(override, dict):
            raise JobRequestError(f"feature override '{feature_id}' must be an object")
        features[feature_id]["enabled"] = bool(
            override.get("enabled", features[feature_id]["enabled"])
        )
        if "config" in override:
            if not isinstance(override["config"], dict):
                raise JobRequestError(f"feature '{feature_id}' config must be an object")
            features[feature_id]["config"].update(override["config"])

    for feature_id, value in features.items():
        expected_status = registry["features"][feature_id]["status"]
        value["status"] = expected_status
        if expected_status == "reserved" and value["enabled"]:
            raise JobRequestError(f"reserved feature '{feature_id}' cannot be enabled")

    timestamp = utc_now()
    request = {
        "schema_version": "0.1",
        "job": {"id": job_id, "created_at": timestamp, "profile": selected_profile},
        "interaction": {
            "source": source,
            "mode": interaction_mode,
            "confirmed": confirmed,
            "confirmed_at": timestamp if confirmed else None,
            "review_checkpoints": interaction_checkpoints(interaction_mode),
        },
        "input": {"paper": paper, "template": template},
        "presentation": presentation,
        "extraction": extraction,
        "visuals": visuals,
        "features": features,
        "execution": {
            "agent_adapter": agent_adapter,
            "state": "pending",
            "paths": paths,
        },
        "extensions": extensions or {},
    }
    validate_request(request, schema=schema, registry=registry)
    return request


def validate_request(
    request: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
) -> None:
    if schema is None or registry is None:
        loaded_schema, _defaults, loaded_registry = load_contract()
        schema = schema or loaded_schema
        registry = registry or loaded_registry
    try:
        jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(request)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(value) for value in exc.absolute_path) or "$"
        raise JobRequestError(f"invalid job request at {location}: {exc.message}") from exc
    registered = registry["features"]
    for feature_id, value in request["features"].items():
        if feature_id not in registered:
            raise JobRequestError(f"unregistered feature in job request: {feature_id}")
        metadata = registered[feature_id]
        if value["status"] != metadata["status"]:
            raise JobRequestError(f"feature status mismatch: {feature_id}")
        if metadata["status"] == "reserved" and value["enabled"]:
            raise JobRequestError(f"reserved feature cannot be enabled: {feature_id}")

    interaction = request["interaction"]
    expected_checkpoints = interaction_checkpoints(interaction["mode"])
    if interaction["review_checkpoints"] != expected_checkpoints:
        raise JobRequestError(
            "interaction.review_checkpoints must match the selected interaction mode"
        )
    if interaction["confirmed"] != (interaction["confirmed_at"] is not None):
        raise JobRequestError(
            "interaction.confirmed and interaction.confirmed_at are inconsistent"
        )
    if interaction["mode"] == "non_interactive" and not interaction["confirmed"]:
        raise JobRequestError("non_interactive requests must already be confirmed")
    if interaction["source"] == "web_ui" and (
        interaction["mode"] != "non_interactive" or not interaction["confirmed"]
    ):
        raise JobRequestError(
            "web_ui requests must be confirmed and use non_interactive mode"
        )
    if interaction["confirmed"] and not request["input"]["paper"]["title_confirmed"]:
        raise JobRequestError("a confirmed request must include a confirmed paper title")


def write_request(path: Path, request: dict[str, Any]) -> None:
    validate_request(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def execution_brief(request: dict[str, Any]) -> str:
    validate_request(request)
    paper = request["input"]["paper"]
    presentation = request["presentation"]
    extraction = request["extraction"]
    features = [
        feature_id
        for feature_id, value in request["features"].items()
        if value["enabled"] and value["status"] == "available"
    ]
    slide_count = (
        "按论文复杂度自动确定"
        if presentation["slide_count_mode"] == "auto"
        else f"{presentation['target_slide_count']} 页"
    )
    return "\n".join(
        (
            f"论文：{paper['confirmed_title']}",
            f"汇报：{presentation['language']} / {presentation['target_minutes']} 分钟 / {slide_count}",
            f"模板：{request['input']['template']['source']}",
            f"图表抽取：{extraction['backend']} / {extraction['device']} / {extraction['crop_dpi']} DPI",
            f"启用功能：{', '.join(features) if features else '无'}",
            f"交互策略：{request['interaction']['mode']} / "
            f"{'已确认' if request['interaction']['confirmed'] else '等待确认'}",
        )
    )


def confirm_request(path: Path) -> dict[str, Any]:
    request = load_json(path)
    validate_request(request)
    request["interaction"]["confirmed"] = True
    request["interaction"]["confirmed_at"] = utc_now()
    request["input"]["paper"]["title_confirmed"] = True
    write_request(path, request)
    return request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a job-request.json")
    validate.add_argument("request", type=Path)

    brief = subparsers.add_parser("brief", help="print a compact execution brief")
    brief.add_argument("request", type=Path)

    confirm = subparsers.add_parser("confirm", help="record explicit intake confirmation")
    confirm.add_argument("request", type=Path)

    defaults = subparsers.add_parser("defaults", help="print a named default profile")
    defaults.add_argument("--profile")

    init = subparsers.add_parser("init", help="create a job request for Skill or CLI use")
    init.add_argument("--paper", type=Path, required=True)
    init.add_argument("--template", type=Path, default=SKILL_ROOT / "assets" / "seminar-template.pptx")
    init.add_argument("--run-dir", type=Path, required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--title-cn", default="")
    init.add_argument("--job-id", required=True)
    init.add_argument("--profile")
    init.add_argument("--source", choices=("skill_chat", "cli"), default="skill_chat")
    init.add_argument(
        "--interaction-mode",
        choices=("non_interactive", "confirm_once", "guided"),
        default="confirm_once",
    )
    init.add_argument("--confirmed", action="store_true")
    init.add_argument("--language", choices=("zh-CN", "en-US", "bilingual"))
    init.add_argument("--target-minutes", type=int)
    init.add_argument("--presenter")
    init.add_argument("--advisor")
    init.add_argument("--no-speaker-notes", action="store_true")
    init.add_argument("-o", "--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "validate":
            request = load_json(args.request)
            validate_request(request)
            print(f"PASS: job request is valid: {args.request.resolve()}")
        elif args.command == "brief":
            print(execution_brief(load_json(args.request)))
        elif args.command == "confirm":
            request = confirm_request(args.request)
            print(f"Confirmed job request: {args.request.resolve()}")
            print(execution_brief(request))
        elif args.command == "defaults":
            _schema, payload, _registry = load_contract()
            profile_name = args.profile or payload["default_profile"]
            if profile_name not in payload["profiles"]:
                raise JobRequestError(f"unknown profile: {profile_name}")
            print(json.dumps(payload["profiles"][profile_name], ensure_ascii=False, indent=2))
        else:
            paper_path = args.paper.resolve()
            template_path = args.template.resolve()
            run_dir = args.run_dir.resolve()
            if not paper_path.is_file() or not template_path.is_file():
                raise JobRequestError("paper and template must exist")
            configuration = {
                key: value
                for key, value in {
                    "language": args.language,
                    "target_minutes": args.target_minutes,
                    "presenter": args.presenter,
                    "advisor": args.advisor,
                }.items()
                if value is not None
            }
            configuration["speaker_notes"] = {"enabled": not args.no_speaker_notes}
            paths = {
                "job_dir": str(run_dir),
                "deck_plan": str(run_dir / "deck-plan.json"),
                "output_pptx": str(run_dir / "build" / "presentation.pptx"),
                "capabilities": str(run_dir / "capabilities.json"),
            }
            request = compile_request(
                job_id=args.job_id,
                paper=inspect_paper_file(
                    paper_path,
                    args.title,
                    args.title_cn,
                    title_confirmed=args.confirmed,
                ),
                template={
                    "path": str(template_path),
                    "source": "custom" if args.template != SKILL_ROOT / "assets" / "seminar-template.pptx" else "bundled",
                    "sha256": sha256_file(template_path),
                },
                paths=paths,
                configuration=configuration,
                source=args.source,
                interaction_mode=args.interaction_mode,
                confirmed=args.confirmed,
                profile_name=args.profile,
            )
            write_request(args.output, request)
            print(f"Created job request: {args.output.resolve()}")
        return 0
    except (JobRequestError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
