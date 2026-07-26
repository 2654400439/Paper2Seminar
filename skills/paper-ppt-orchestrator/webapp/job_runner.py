"""Detached runner used by the Streamlit task console."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from backend import CodexAdapter, repository_root, utc_now, write_json_atomic
from job_request import JobRequestError, validate_request


def agent_environment(job_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    cache_dir = job_dir / ".cache"
    yolo_dir = cache_dir / "yolo"
    matplotlib_dir = cache_dir / "matplotlib"
    yolo_dir.mkdir(parents=True, exist_ok=True)
    matplotlib_dir.mkdir(parents=True, exist_ok=True)
    environment["YOLO_CONFIG_DIR"] = str(yolo_dir.resolve())
    environment["MPLCONFIGDIR"] = str(matplotlib_dir.resolve())
    return environment


def update(path: Path, request: dict, state: str, message: str, **extra: object) -> None:
    write_json_atomic(
        path,
        {
            "job_id": request["job"]["id"],
            "state": state,
            "message": message,
            "updated_at": utc_now(),
            **extra,
        },
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: job_runner.py JOB_REQUEST", file=sys.stderr)
        return 2
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        validate_request(request)
    except JobRequestError as exc:
        print(f"invalid job request: {exc}", file=sys.stderr)
        return 2
    if request["interaction"]["confirmed"] is not True:
        print("job request is not confirmed", file=sys.stderr)
        return 2
    paths = request["execution"]["paths"]
    job_dir = Path(paths["job_dir"])
    status_path = job_dir / "job-status.json"
    log_path = job_dir / "agent.log"
    prompt = (job_dir / "agent-prompt.txt").read_text(encoding="utf-8")
    try:
        command = CodexAdapter.command(repository_root())
        environment = agent_environment(job_dir)
        update(status_path, request, "running", "Agent 正在执行完整工作流")
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=repository_root(),
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
            )
            process.communicate(prompt)
        output = Path(paths["output_pptx"])
        if process.returncode != 0:
            update(status_path, request, "failed", f"Agent 退出码为 {process.returncode}", log=str(log_path))
            return process.returncode or 1
        if not output.is_file():
            update(status_path, request, "failed", "Agent 已结束，但没有找到最终 PPTX", log=str(log_path))
            return 1
        update(
            status_path,
            request,
            "completed",
            "PPT 已生成并完成验证",
            output_pptx=str(output),
            log=str(log_path),
        )
        return 0
    except Exception as exc:
        update(status_path, request, "failed", str(exc), log=str(log_path))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
