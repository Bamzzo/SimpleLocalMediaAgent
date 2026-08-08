"""Gradio UI for SLMAgent."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

import gradio as gr
import httpx
import yaml

from slmagent.configs.settings import ROOT, get_settings
from slmagent.contracts.models import (
    AspectRatio,
    Brief,
    CameraMove,
    ContentType,
    GenerationMode,
    VisualStyle,
)


def _load_defaults() -> dict[str, Any]:
    path = ROOT / "slmagent" / "configs" / "defaults.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


DEF = _load_defaults()
OPTS = DEF["options"]
DEMO = DEF["demo_case"]


def backend_mode_label(generation_backend: str | None = None) -> str:
    """Return mock|live for media labels from GENERATION_BACKEND."""
    backend = generation_backend or get_settings().generation_backend
    return "live" if backend == "live" else "mock"


def ui_status_banner(
    generation_backend: str | None = None,
    llm_mode: str | None = None,
) -> str:
    """Banner for Gradio page config at launch time (not a specific API run)."""
    settings = get_settings()
    backend = generation_backend or settings.generation_backend
    llm = llm_mode or settings.resolved_llm_mode()
    if backend == "live":
        media_line = (
            "当前页面配置：**Generation Backend = live**。"
            "控件标签按此配置显示；单次运行完成后的结果摘要以 API 返回的实际值为准。"
        )
    else:
        media_line = (
            "当前页面配置：**Generation Backend = mock**。"
            "控件标签按此配置显示；单次运行完成后的结果摘要以 API 返回的实际值为准。"
        )
    llm_line = (
        f"当前页面 LLM 配置：`{llm}`。"
        + (
            " DeepSeek 结构化规划配置为 live。"
            if llm == "live"
            else " DeepSeek 规划配置为 mock，不能写成全真实 LLM 链路。"
        )
    )
    return (
        "# SLMAgent — Simple Local Media Agent\n"
        "简易本地化智能视听创作智能体（P0 验证）\n\n"
        f"{media_line}\n\n"
        f"{llm_line}"
    )


def run_result_footnote(generation_backend: str, llm_mode: str) -> str:
    """Footnote for a completed run; callers must pass API-reported modes."""
    backend = "live" if generation_backend == "live" else "mock"
    llm = "live" if llm_mode == "live" else "mock"
    if backend == "live":
        return (
            f"说明：本次 API 运行 Generation Backend={backend}；LLM={llm}。"
            "媒体结果来自真实适配器，不等于 OpenCLIP 阈值已校准，"
            "也不等于 LLM 一定为 live。"
        )
    return (
        f"说明：本次 API 运行 Generation Backend={backend}；LLM={llm}。"
        "图像/视频为 Mock 占位，未宣称真实 FLUX/H3 画质。"
    )


def format_run_summary(result: dict[str, Any]) -> str:
    """Build Gradio status text from /pipeline/run JSON (API is source of truth)."""
    status = result.get("status", "unknown")
    pid = result.get("project_id", "")
    warnings = result.get("warnings") or []
    backend = str(result.get("backend") or "mock")
    llm_mode = str(result.get("llm_mode") or "mock")
    return (
        f"status={status}\n"
        f"project_id={pid}\n"
        f"backend={backend}\n"
        f"llm_mode={llm_mode}\n"
        f"warnings={warnings}\n"
        f"manifest=runs/{pid}/final_manifest.json\n"
        f"\n{run_result_footnote(backend, llm_mode)}"
    )


def _save_refs(files: Optional[list[Any]]) -> list[str]:
    if not files:
        return []
    # Use RUNS_DIR so API and Gradio can share uploads in Docker Compose.
    staging = get_settings().runs_dir / "_uploads" / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for f in files:
        src = Path(f if isinstance(f, str) else getattr(f, "name", f))
        dest = staging / src.name
        shutil.copy2(src, dest)
        paths.append(str(dest))
    return paths


def run_job(
    mode_label: str,
    project_name: str,
    content_type: str,
    description: str,
    selling_points: str,
    audience: str,
    visual_style: str,
    aspect_ratio: str,
    duration_sec: int,
    camera_move: str,
    generation_mode: str,
    constraints: str,
    script_text: str,
    ref_images: Optional[list[Any]],
) -> tuple[str, Optional[str], Optional[str], Optional[str], str]:
    mode = "script" if mode_label.startswith("剧本") else "free"
    refs = _save_refs(ref_images)
    brief = Brief(
        project_name=project_name or DEMO["project_name"],
        mode=mode,
        content_type=ContentType(content_type),
        description=description,
        selling_points=selling_points,
        audience=audience,
        visual_style=VisualStyle(visual_style),
        aspect_ratio=AspectRatio(aspect_ratio),
        duration_sec=int(duration_sec),
        camera_move=CameraMove(camera_move),
        generation_mode=GenerationMode(generation_mode),
        constraints=constraints,
        script_text=script_text,
        reference_image_paths=refs,
    )
    settings = get_settings()
    try:
        response = httpx.post(
            f"{settings.api_base_url.rstrip('/')}/pipeline/run",
            json={"brief": brief.model_dump(mode="json")},
            timeout=settings.api_pipeline_timeout_sec,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.HTTPError as exc:
        message = (
            "无法连接或调用 API。请先启动 FastAPI 服务，并检查 API_BASE_URL。\n"
            f"技术信息：{exc}"
        )
        return message, None, None, None, message
    summary = format_run_summary(result)
    return (
        summary,
        result.get("first_frame_path"),
        result.get("last_frame_path"),
        result.get("final_video_path"),
        summary,
    )


def build_ui() -> gr.Blocks:
    settings = get_settings()
    media_tag = backend_mode_label(settings.generation_backend)
    with gr.Blocks(title="SLMAgent — Simple Local Media Agent") as demo:
        gr.Markdown(ui_status_banner())
        with gr.Row():
            mode = gr.Radio(
                choices=["自由创作模式", "剧本驱动模式"],
                value="自由创作模式",
                label="创作模式",
            )
        with gr.Row():
            with gr.Column():
                project_name = gr.Textbox(label="项目名称", value=DEMO["project_name"])
                content_type = gr.Dropdown(OPTS["content_types"], value="项目宣传片", label="内容类型")
                description = gr.Textbox(label="产品/项目/故事介绍", value=DEMO["description"], lines=4)
                selling_points = gr.Textbox(label="核心卖点", value=DEMO["selling_points"])
                audience = gr.Textbox(label="目标受众", value=DEMO["audience"])
                visual_style = gr.Dropdown(OPTS["visual_styles"], value="科技未来", label="视觉风格")
                aspect_ratio = gr.Dropdown(OPTS["aspect_ratios"], value="16:9", label="画面比例")
                duration_sec = gr.Number(label="视频时长（秒）", value=5, precision=0)
                camera_move = gr.Dropdown(OPTS["camera_moves"], value="缓慢推进", label="运镜偏好")
                generation_mode = gr.Dropdown(
                    OPTS["generation_modes"],
                    value="首尾帧生视频",
                    label="生成模式（未验证项请视为实验性）",
                )
                constraints = gr.Textbox(label="约束条件", value=DEMO["constraints"])
                script_text = gr.Textbox(label="完整剧本文本（剧本驱动模式）", lines=8)
                ref_images = gr.File(
                    label="参考图片（点击或拖拽）",
                    file_count="multiple",
                    file_types=["image"],
                )
                run_btn = gr.Button("开始全自动生成", variant="primary")
            with gr.Column():
                status_box = gr.Textbox(label="运行状态", lines=12)
                first_img = gr.Image(
                    label=f"首帧（页面配置:{media_tag}）",
                    type="filepath",
                )
                last_img = gr.Image(
                    label=f"尾帧（页面配置:{media_tag}）",
                    type="filepath",
                )
                video_out = gr.Video(label=f"导出视频（页面配置:{media_tag}）")
                log_box = gr.Textbox(label="结果清单（以 API 返回为准）", lines=8)

        run_btn.click(
            fn=run_job,
            inputs=[
                mode,
                project_name,
                content_type,
                description,
                selling_points,
                audience,
                visual_style,
                aspect_ratio,
                duration_sec,
                camera_move,
                generation_mode,
                constraints,
                script_text,
                ref_images,
            ],
            outputs=[status_box, first_img, last_img, video_out, log_box],
        )
        gr.Markdown(
            f"API：`{settings.api_base_url}` ｜ "
            f"当前页面配置 LLM：`{settings.resolved_llm_mode()}` ｜ "
            f"Backend：`{settings.generation_backend}`"
            "（单次运行结果以 `/pipeline/run` 返回的 backend/llm_mode 为准）"
        )
    return demo


def main() -> None:
    settings = get_settings()
    demo = build_ui()
    demo.launch(server_name=settings.gradio_host, server_port=settings.gradio_port)


if __name__ == "__main__":
    main()
