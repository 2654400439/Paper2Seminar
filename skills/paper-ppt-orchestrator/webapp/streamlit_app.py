"""Paper2Seminar local task console."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import streamlit as st


WEBAPP_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = WEBAPP_DIR.parent / "scripts"
if str(WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(WEBAPP_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from backend import (  # noqa: E402
    CodexAdapter,
    UIError,
    create_job,
    inspect_pdf,
    list_artifacts,
    load_status,
    repository_root,
    run_preflight,
    start_job,
)
from job_request import load_contract  # noqa: E402


REPO_ROOT = repository_root()
JOBS_ROOT = REPO_ROOT / "runs"
_JOB_SCHEMA, JOB_DEFAULTS, FEATURE_REGISTRY = load_contract()
DEFAULT_PROFILE_NAME = JOB_DEFAULTS["default_profile"]
DEFAULT_PROFILE = JOB_DEFAULTS["profiles"][DEFAULT_PROFILE_NAME]


def option_index(options: list[str], selected: str) -> int:
    return options.index(selected) if selected in options else 0


st.set_page_config(page_title="Paper2Seminar", page_icon="📑", layout="wide")
st.markdown(
    """
    <style>
    :root { --ink: #17212b; --muted: #66717c; --line: #d8dee5; --blue: #194a96; --teal: #147d78; --amber: #a86508; }
    .stApp { background: #f7f9fb; color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(247,249,251,.96); }
    .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 4rem; }
    h1, h2, h3 { letter-spacing: 0 !important; color: var(--ink); }
    h1 { font-size: 2rem !important; }
    h2 { font-size: 1.25rem !important; margin-top: 1.5rem !important; }
    div[data-testid="stMetric"] { background: #fff; border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
    div[data-testid="stForm"], div[data-testid="stExpander"] { border-color: var(--line); border-radius: 6px; background: #fff; }
    .status-line { padding: 12px 14px; border-left: 4px solid var(--blue); background: #fff; border-radius: 4px; }
    .muted { color: var(--muted); font-size: .9rem; }
    .reserved { color: var(--amber); font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)


def recent_jobs() -> list[Path]:
    if not JOBS_ROOT.is_dir():
        return []
    return sorted(
        (path for path in JOBS_ROOT.glob("ui-*") if (path / "job-request.json").is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def render_status(job_dir: Path) -> None:
    status = load_status(job_dir)
    request = json.loads((job_dir / "job-request.json").read_text(encoding="utf-8"))
    notes_enabled = request["features"]["speaker_notes"]["enabled"]
    state = status.get("state", "unknown")
    labels = {
        "created": ("已创建", 5),
        "running": ("制作中", 55),
        "completed": ("已完成", 100),
        "failed": ("失败", 100),
        "unknown": ("未知", 0),
    }
    label, progress = labels.get(state, (state, 0))
    st.progress(progress, text=f"{label} · {status.get('message', '')}")
    cols = st.columns(4)
    expected = [
        ("论文理解", job_dir / "paper-notes.json"),
        ("页面规划", job_dir / "deck-plan.json"),
        ("PPT 组装", job_dir / "build" / "presentation.pptx"),
        ("后置讲稿", job_dir / "build" / "presentation.notes.json"),
    ]
    for column, (name, path) in zip(cols, expected):
        value = "完成" if path.exists() else "等待"
        if name == "后置讲稿" and not notes_enabled:
            value = "未启用"
        column.metric(name, value)

    log_path = job_dir / "agent.log"
    if log_path.is_file():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        with st.expander("执行日志", expanded=state == "failed"):
            st.code("\n".join(lines[-120:]) or "暂无日志", language="text")

    artifacts = list_artifacts(job_dir)
    deliverables = [path for path in artifacts if path.suffix.lower() in {".pptx", ".json", ".md"}]
    if deliverables:
        st.subheader("任务产物")
        for path in deliverables:
            relative = path.relative_to(job_dir)
            col_name, col_size, col_action = st.columns([5, 1, 1])
            col_name.write(str(relative))
            col_size.caption(f"{path.stat().st_size / 1024:.0f} KB")
            col_action.download_button(
                "下载",
                data=path.read_bytes(),
                file_name=path.name,
                key=f"download-{hashlib.sha1(str(path).encode()).hexdigest()}",
            )


st.title("Paper2Seminar（测试版）")
st.caption("本地论文汇报任务控制台")

with st.sidebar:
    st.subheader("运行状态")
    codex_authentication = CodexAdapter.authentication()
    if codex_authentication["authenticated"]:
        codex_label = "已安装并登录"
    elif codex_authentication["installed"]:
        codex_label = "已安装，未登录"
    else:
        codex_label = "未检测到"
    st.write("Codex CLI", codex_label)
    jobs = recent_jobs()
    selected_job = st.selectbox(
        "最近任务",
        options=[""] + [path.name for path in jobs],
        format_func=lambda value: "未选择" if not value else value,
    )
    st.caption(f"任务目录：{JOBS_ROOT}")

create_tab, status_tab, environment_tab = st.tabs(["新建任务", "任务状态", "环境检查"])

with create_tab:
    st.subheader("1. 论文与模板")
    pdf_file = st.file_uploader("论文 PDF", type=["pdf"])
    template_file = st.file_uploader("演示模板（可选）", type=["pptx"])

    inspection = None
    if pdf_file is not None:
        pdf_payload = pdf_file.getvalue()
        if len(pdf_payload) > 100 * 1024 * 1024:
            st.error("PDF 超过 100 MB，请先压缩后再上传。")
            st.stop()
        digest = hashlib.sha256(pdf_payload).hexdigest()
        if st.session_state.get("inspected_pdf_sha") != digest:
            try:
                st.session_state["pdf_inspection"] = inspect_pdf(pdf_payload)
                st.session_state["inspected_pdf_sha"] = digest
                st.session_state["confirmed_title_en"] = st.session_state["pdf_inspection"]["title"]
                st.session_state["confirmed_title_cn"] = ""
            except UIError as exc:
                st.error(str(exc))
        inspection = st.session_state.get("pdf_inspection")

    if inspection:
        metrics = st.columns(3)
        metrics[0].metric("页数", inspection["page_count"])
        metrics[1].metric("文本解析", "通过" if inspection["text_extractable"] else "失败")
        metrics[2].metric("文件指纹", inspection["sha256"][:10])
        st.text_input("确认论文原文标题", key="confirmed_title_en")
        st.text_input("中文标题（可留空，由 agent 翻译）", key="confirmed_title_cn")
        with st.expander("标题识别候选"):
            for candidate in inspection["candidates"]:
                st.write(candidate)

    st.subheader("2. 汇报配置")
    identity_left, identity_right = st.columns(2)
    presenter = identity_left.text_input("汇报人")
    advisor = identity_right.text_input("指导老师")

    config_left, config_middle, config_right = st.columns(3)
    language_options = ["zh-CN", "bilingual", "en-US"]
    language = config_left.selectbox(
        "输出语言",
        language_options,
        index=option_index(language_options, DEFAULT_PROFILE["presentation"]["language"]),
        format_func={"zh-CN": "中文", "bilingual": "中英双语", "en-US": "英文"}.get,
    )
    target_minutes = config_middle.number_input(
        "目标时长（分钟）",
        min_value=5,
        max_value=120,
        value=DEFAULT_PROFILE["presentation"]["target_minutes"],
        step=5,
    )
    slide_mode_options = ["auto", "manual"]
    slide_count_mode = config_right.selectbox(
        "页数策略",
        slide_mode_options,
        index=option_index(slide_mode_options, DEFAULT_PROFILE["presentation"]["slide_count_mode"]),
        format_func={"auto": "按论文复杂度自动", "manual": "手动指定"}.get,
    )
    target_slide_count = None
    if slide_count_mode == "manual":
        target_slide_count = st.number_input("目标总页数", min_value=8, max_value=80, value=30)

    st.subheader("3. 图表、视觉与质量")
    extraction_col, visual_col, qa_col = st.columns(3)
    with extraction_col:
        extraction_options = ["doclayout", "captioncrop"]
        extraction_backend = st.selectbox(
            "论文图表裁剪",
            extraction_options,
            index=option_index(extraction_options, DEFAULT_PROFILE["extraction"]["backend"]),
            format_func={"doclayout": "DocLayout-YOLO（默认）", "captioncrop": "CaptionCrop（轻量）"}.get,
        )
        device_options = ["cpu", "cuda", "mps"]
        device = st.selectbox(
            "推理设备",
            device_options,
            index=option_index(device_options, DEFAULT_PROFILE["extraction"]["device"]),
        )
        confidence = st.slider(
            "检测阈值", 0.05, 0.80, float(DEFAULT_PROFILE["extraction"]["confidence"]), 0.01
        )
        crop_dpi = st.number_input(
            "裁剪 DPI",
            min_value=150,
            max_value=600,
            value=DEFAULT_PROFILE["extraction"]["crop_dpi"],
            step=25,
        )
        captioncrop_command = ""
        if extraction_backend == "captioncrop":
            captioncrop_command = st.text_input("CaptionCrop 命令路径")
    with visual_col:
        capability_labels = {
            "unknown": "由 agent 首次确认",
            "available": "当前会话可用",
            "unavailable": "当前会话不可用",
        }
        capability_options = ["unknown", "available", "unavailable"]
        imagegen_state = st.selectbox(
            "概念图片生成能力",
            capability_options,
            index=option_index(capability_options, DEFAULT_PROFILE["visuals"]["imagegen"]),
            format_func=capability_labels.get,
        )
        web_search_state = st.selectbox(
            "授权图片搜索能力",
            capability_options,
            index=option_index(capability_options, DEFAULT_PROFILE["visuals"]["web_search"]),
            format_func=capability_labels.get,
        )
    with qa_col:
        readability_default = DEFAULT_PROFILE["features"]["readability"]["config"]["mode"]
        readability_options = ["overview", "full", "off"]
        readability_mode = st.selectbox(
            "最终可读性检查",
            readability_options,
            index=option_index(readability_options, readability_default),
            format_func={"overview": "总览检查（推荐）", "full": "逐组精查", "off": "关闭"}.get,
        )
        st.caption("其余可选功能统一显示在下方功能配置中。")

    st.subheader("4. 逐页讲稿")
    speaker_default = DEFAULT_PROFILE["features"]["speaker_notes"]
    notes_enabled = st.toggle("核心 PPT 完成后生成逐字稿", value=speaker_default["enabled"])
    notes_left, notes_middle, notes_right = st.columns(3)
    notes_left.text_input("生成阶段", value="页面审批后（post-QA）", disabled=True)
    delivery_style = notes_middle.selectbox("讲稿形式", ["verbatim"], format_func=lambda _: "可直接口述的逐字稿", disabled=not notes_enabled)
    pace = notes_right.number_input(
        "参考语速（中英混合单位/分钟）",
        min_value=80,
        max_value=400,
        value=speaker_default["config"]["pace_units_per_minute"],
        step=10,
        disabled=not notes_enabled,
    )
    st.caption("讲稿只读取页面文字、可视化设计元数据、论文笔记和论文文本；不会通过幻灯片截图生成。")

    st.subheader("5. 可选功能")
    generic_feature_values: dict[str, dict[str, object]] = {}
    feature_columns = st.columns(2)
    generic_features = [
        (feature_id, metadata)
        for feature_id, metadata in FEATURE_REGISTRY["features"].items()
        if feature_id not in {"speaker_notes", "readability"}
    ]
    for index, (feature_id, metadata) in enumerate(generic_features):
        default_value = DEFAULT_PROFILE["features"][feature_id]
        reserved = metadata["status"] == "reserved"
        label = metadata["label_zh"] + (" · 未完成" if reserved else "")
        enabled = feature_columns[index % 2].checkbox(
            label,
            value=default_value["enabled"],
            disabled=reserved,
            key=f"feature-{feature_id}",
        )
        generic_feature_values[feature_id] = {"enabled": enabled, "config": {}}

    with st.expander("高级配置"):
        st.selectbox("Agent 适配器", ["codex"], format_func=lambda _: "Codex CLI")
        st.text_input("OpenCode 适配器 · 未完成", value="", disabled=True)
        st.text_input("Claude Code 适配器 · 未完成", value="", disabled=True)

    ready = pdf_file is not None and inspection is not None and inspection.get("text_extractable")
    if st.button("创建并开始制作", type="primary", disabled=not ready, use_container_width=True):
        if not codex_authentication["installed"]:
            st.error("未检测到 Codex CLI，当前版本无法启动 agent 任务。")
        elif not codex_authentication["authenticated"]:
            st.error("Codex CLI 尚未登录。请先在 PowerShell 中运行以下命令，然后刷新页面：")
            st.code('& "$env:APPDATA\\npm\\codex.CMD" login', language="powershell")
        else:
            configuration = {
                "title_en": st.session_state.get("confirmed_title_en", ""),
                "title_cn": st.session_state.get("confirmed_title_cn", ""),
                "presenter": presenter.strip(),
                "advisor": advisor.strip(),
                "language": language,
                "target_minutes": int(target_minutes),
                "slide_count_mode": slide_count_mode,
                "target_slide_count": int(target_slide_count) if target_slide_count else None,
                "extraction": {
                    "backend": extraction_backend,
                    "device": device,
                    "confidence": confidence,
                    "crop_dpi": int(crop_dpi),
                    "captioncrop_command": captioncrop_command.strip(),
                },
                "visual_capabilities": {
                    "imagegen": imagegen_state,
                    "web_search": web_search_state,
                },
                "readability_mode": readability_mode,
                "speaker_notes": {
                    "enabled": notes_enabled,
                    "generation_stage": "post_qa",
                    "delivery_style": delivery_style,
                    "target_minutes": int(target_minutes),
                    "pace_units_per_minute": int(pace),
                },
                "features": generic_feature_values,
            }
            try:
                request = create_job(
                    pdf_file.getvalue(),
                    pdf_file.name,
                    configuration,
                    template_payload=template_file.getvalue() if template_file else None,
                )
                pid = start_job(request)
                st.session_state["active_job"] = request["job"]["id"]
                st.success(f"任务已启动，进程号 {pid}")
                st.code(request["execution"]["paths"]["job_dir"], language="text")
            except UIError as exc:
                st.error(str(exc))

with status_tab:
    active_name = st.session_state.get("active_job") or selected_job
    active_dir = JOBS_ROOT / active_name if active_name else None
    if active_dir and active_dir.is_dir():
        st.subheader(active_name)
        render_status(active_dir)
        st.button("刷新状态", use_container_width=True)
    else:
        st.info("选择或创建任务后，这里会显示进度、日志和下载项。")

with environment_tab:
    st.subheader("本机能力")
    if codex_authentication["authenticated"]:
        st.success("Codex CLI 已安装并登录，可以接收后台任务。")
    elif codex_authentication["installed"]:
        st.warning("Codex CLI 已安装但尚未登录，完整任务当前无法启动。")
        st.code('& "$env:APPDATA\\npm\\codex.CMD" login', language="powershell")
    else:
        st.error("未检测到 Codex CLI。")
    env_left, env_right = st.columns(2)
    declared_imagegen = env_left.selectbox("当前 agent 的图片生成能力", ["available", "unavailable", "unknown"])
    declared_web = env_right.selectbox("当前 agent 的网络搜索能力", ["available", "unavailable", "unknown"])
    if st.button("运行环境检查", use_container_width=True):
        try:
            report = run_preflight(JOBS_ROOT / "ui-preflight" / "capabilities.json", declared_imagegen, declared_web)
            tool_rows = []
            for name, record in report["tools"].items():
                if name == "browsers":
                    tool_rows.append({"工具": "browser", "状态": "available" if record else "unavailable", "版本/路径": record[0]["path"] if record else ""})
                else:
                    tool_rows.append({"工具": name, "状态": record.get("status", "unknown"), "版本/路径": record.get("version") or record.get("path") or ""})
            st.dataframe(tool_rows, use_container_width=True, hide_index=True)
            for warning in report["warnings"]:
                st.warning(warning)
        except UIError as exc:
            st.error(str(exc))
