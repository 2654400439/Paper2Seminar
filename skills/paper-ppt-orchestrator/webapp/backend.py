"""Task storage, PDF inspection, and agent adapters for the Streamlit UI."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILL_ROOT / "scripts"
DEFAULT_TEMPLATE = SKILL_ROOT / "assets" / "seminar-template.pptx"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from job_request import (  # noqa: E402
    JobRequestError,
    compile_request,
    sha256_file,
    validate_request,
)


class UIError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n-|:")


def plausible_title(value: str) -> bool:
    lowered = value.lower()
    rejected = ("abstract", "arxiv:", "doi:", "preprint", "proceedings of")
    return 12 <= len(value) <= 320 and not any(token in lowered for token in rejected)


def inspect_pdf(payload: bytes) -> dict[str, Any]:
    try:
        document = fitz.open(stream=payload, filetype="pdf")
    except Exception as exc:
        raise UIError(f"无法读取 PDF：{exc}") from exc
    try:
        if document.page_count < 1:
            raise UIError("PDF 没有可读取页面")
        metadata_title = clean_title(str(document.metadata.get("title") or ""))
        page = document[0]
        page_height = float(page.rect.height)
        candidates: list[tuple[float, str]] = []
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            text = clean_title(
                " ".join(
                    str(span.get("text", ""))
                    for line in lines
                    for span in line.get("spans", [])
                )
            )
            if not plausible_title(text):
                continue
            spans = [span for line in lines for span in line.get("spans", [])]
            sizes = [float(span.get("size", 0)) for span in spans]
            if not sizes:
                continue
            y0 = float(block.get("bbox", [0, 0, 0, 0])[1])
            if y0 > page_height * 0.48:
                continue
            score = max(sizes) * 10 + sum(sizes) / len(sizes) - y0 / max(page_height, 1)
            candidates.append((score, text))
        candidates.sort(key=lambda item: item[0], reverse=True)
        detected = candidates[0][1] if candidates else metadata_title
        if plausible_title(metadata_title) and not candidates:
            detected = metadata_title
        if not detected:
            detected = "未识别到标题，请手动输入"
        return {
            "title": detected,
            "metadata_title": metadata_title,
            "page_count": document.page_count,
            "text_extractable": bool(clean_title(page.get_text("text"))),
            "candidates": [text for _, text in candidates[:5]],
            "sha256": sha256_bytes(payload),
        }
    finally:
        document.close()


def safe_slug(value: str) -> str:
    ascii_slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return (ascii_slug[:36] or "paper")


def repository_root() -> Path:
    candidate = SKILL_ROOT.parent.parent
    return candidate if (candidate / ".git").exists() else SKILL_ROOT


def build_agent_prompt(request: dict[str, Any]) -> str:
    interaction = request["interaction"]
    paper = request["input"]["paper"]
    template = request["input"]["template"]
    presentation = request["presentation"]
    extraction = request["extraction"]
    visuals = request["visuals"]
    features = request["features"]
    paths = request["execution"]["paths"]
    enabled_features = {
        feature_id: value
        for feature_id, value in features.items()
        if value["enabled"] and value["status"] == "available"
    }
    if interaction["confirmed"]:
        title_status = "用户已经确认以下英文/原文标题。"
        confirmation_guidance = (
            "该任务已经由" + interaction["source"] + " " + "入口确认，不要重复询问用户。"
        )
    else:
        title_status = "以下是当前检测到的英文/原文标题，尚待用户确认。"
        confirmation_guidance = (
            "该任务尚未确认。只完成便宜的输入检查并生成一次 execution brief；"
            "不要开始完整工作流程、全文阅读、模型抽取或资产生成，也不要假定用户已经同意。"
        )
    return f"""请使用 $paper-ppt-orchestrator 完成这个学术论文 PPT 任务。

任务配置文件：{paths['job_dir']}/job-request.json
任务目录必须固定为：{paths['job_dir']}
论文 PDF：{paper['path']}
模板 PPTX：{template['path']}
{title_status}
英文/原文标题：{paper['confirmed_title']}
用户填写的中文标题：{paper['title_cn'] or '请在阅读全文后准确翻译'}
汇报人：{presentation['presenter'] or '未填写'}
指导老师：{presentation['advisor'] or '未填写'}
语言：{presentation['language']}
目标时长：{presentation['target_minutes']} 分钟
目标页数策略：{presentation['slide_count_mode']}；手动页数：{presentation['target_slide_count'] or '不适用'}
图表抽取后端：{extraction['backend']}
CaptionCrop 命令路径：{extraction['captioncrop_command'] or '未指定，按 PATH 查找'}
DocLayout 设备：{extraction['device']}
检测阈值：{extraction['confidence']}
裁剪 DPI：{extraction['crop_dpi']}
图片生成能力：{visuals['imagegen']}
网络图片搜索能力：{visuals['web_search']}
已启用功能：{json.dumps(enabled_features, ensure_ascii=False)}

先运行 job-request 校验，并将该文件视为本次任务的不可变输入配置。
{confirmation_guidance}
确认后严格遵循 skill 的完整工作流程；将 run-manifest.json、capabilities.json、paper-notes.json、
deck-plan.json、资产、QA 记录和 build/presentation.pptx 全部放入指定任务目录。
不要在指定目录之外另建 runs 子目录。即使标题已确认，也仍需阅读全文并核对元数据。

interaction.source={interaction['source']}，mode={interaction['mode']}，confirmed={str(interaction['confirmed']).lower()}。
只执行 status=available 且 enabled=true 的功能；
status=reserved 的功能不得执行。任何新增功能都以 job-request.json 的 features 和当前 skill 版本为准。

不要声称成功，除非最终 PPTX 和要求的验证报告确实存在。遇到无法完成的依赖或权限问题时，
将具体原因写入任务目录的 qa/failure.md，并在最终回答中准确报告。
"""


def create_job(
    pdf_payload: bytes,
    original_name: str,
    configuration: dict[str, Any],
    *,
    jobs_root: Path | None = None,
    template_payload: bytes | None = None,
) -> dict[str, Any]:
    inspection = inspect_pdf(pdf_payload)
    title = clean_title(str(configuration.get("title_en") or ""))
    if not title:
        raise UIError("请确认论文标题")
    if not inspection["text_extractable"]:
        raise UIError("当前 PDF 第一页没有可提取文本，P0 工作流暂不适合直接处理")

    root = (jobs_root or (repository_root() / "runs")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_id = f"ui-{timestamp}-{safe_slug(title)}-{uuid.uuid4().hex[:6]}"
    job_dir = (root / job_id).resolve()
    if root not in job_dir.parents:
        raise UIError("任务目录越出允许范围")
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True)
    paper_path = input_dir / "paper.pdf"
    template_path = input_dir / "template.pptx"
    paper_path.write_bytes(pdf_payload)
    if template_payload is None:
        if not DEFAULT_TEMPLATE.is_file():
            raise UIError(f"默认模板不存在：{DEFAULT_TEMPLATE}")
        shutil.copy2(DEFAULT_TEMPLATE, template_path)
        template_source = "bundled"
    else:
        template_path.write_bytes(template_payload)
        template_source = "uploaded"

    configuration = dict(configuration)
    configuration["title_en"] = title
    paths = {
        "job_dir": str(job_dir),
        "deck_plan": str(job_dir / "deck-plan.json"),
        "output_pptx": str(job_dir / "build" / "presentation.pptx"),
        "capabilities": str(job_dir / "capabilities.json"),
    }
    paper = {
        "path": str(paper_path),
        "original_filename": Path(original_name).name,
        "sha256": inspection["sha256"],
        "page_count": inspection["page_count"],
        "text_extractable": inspection["text_extractable"],
        "detected_title": inspection["title"],
        "confirmed_title": title,
        "title_cn": str(configuration.get("title_cn") or "").strip(),
        "title_confirmed": True,
    }
    template = {
        "path": str(template_path),
        "source": template_source,
        "sha256": sha256_file(template_path),
    }
    try:
        request = compile_request(
            job_id=job_id,
            paper=paper,
            template=template,
            paths=paths,
            configuration=configuration,
            source="web_ui",
            interaction_mode="non_interactive",
            confirmed=True,
            agent_adapter="codex",
        )
    except JobRequestError as exc:
        raise UIError(str(exc)) from exc
    request_path = job_dir / "job-request.json"
    prompt_path = job_dir / "agent-prompt.txt"
    write_json_atomic(request_path, request)
    prompt_path.write_text(build_agent_prompt(request), encoding="utf-8")
    write_json_atomic(
        job_dir / "job-status.json",
        {"job_id": job_id, "state": "created", "updated_at": utc_now(), "message": "任务已创建"},
    )
    return request


class CodexAdapter:
    name = "codex"

    @staticmethod
    def executable() -> str | None:
        return shutil.which("codex") or shutil.which("codex.cmd")

    @classmethod
    def available(cls) -> bool:
        return cls.executable() is not None

    @classmethod
    def authentication(cls) -> dict[str, Any]:
        executable = cls.executable()
        if not executable:
            return {
                "installed": False,
                "authenticated": False,
                "detail": "Codex CLI is not installed",
            }
        try:
            completed = subprocess.run(
                [executable, "login", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "installed": True,
                "authenticated": False,
                "detail": f"cannot check Codex login status: {exc}",
            }
        detail = (completed.stdout.strip() or completed.stderr.strip()).strip()
        return {
            "installed": True,
            "authenticated": completed.returncode == 0,
            "detail": detail or f"Codex login status exited with {completed.returncode}",
        }

    @classmethod
    def command(cls, workdir: Path) -> list[str]:
        executable = cls.executable()
        if not executable:
            raise UIError("未找到 Codex CLI，请先安装并登录 Codex")
        command = [
            executable,
            "exec",
            "--json",
            "--color",
            "never",
            "--sandbox",
            "workspace-write",
            "-C",
            str(workdir),
        ]
        if not (workdir / ".git").exists():
            command.append("--skip-git-repo-check")
        command.append("-")
        return command


def run_preflight(output: Path, imagegen: str, web_search: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "paper_ppt.py"),
        "preflight",
        "-o",
        str(output.resolve()),
        "--imagegen",
        imagegen,
        "--web-search",
        web_search,
    ]
    completed = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if completed.returncode != 0:
        raise UIError(completed.stderr.strip() or completed.stdout.strip() or "环境预检失败")
    return json.loads(output.read_text(encoding="utf-8"))


def start_job(request: dict[str, Any]) -> int:
    try:
        validate_request(request)
    except JobRequestError as exc:
        raise UIError(str(exc)) from exc
    if not request["interaction"]["confirmed"]:
        raise UIError("后台任务只能启动已经确认的 job request")
    authentication = CodexAdapter.authentication()
    if not authentication["authenticated"]:
        raise UIError(
            "Codex CLI 尚未登录。请先在 PowerShell 中运行 "
            "& \"$env:APPDATA\\npm\\codex.CMD\" login"
        )
    job_dir = Path(request["execution"]["paths"]["job_dir"])
    runner = Path(__file__).with_name("job_runner.py")
    command = [sys.executable, str(runner), str(job_dir / "job-request.json")]
    kwargs: dict[str, Any] = {
        "cwd": str(repository_root()),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    return process.pid


def load_status(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "job-status.json"
    if not path.is_file():
        return {"state": "unknown", "message": "没有状态记录"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "unknown", "message": "状态文件暂时不可读"}


def list_artifacts(job_dir: Path) -> list[Path]:
    patterns = ("*.pptx", "*.json", "*.md", "*.png")
    paths = [path for pattern in patterns for path in job_dir.rglob(pattern)]
    return sorted(path for path in paths if "input" not in path.relative_to(job_dir).parts)
