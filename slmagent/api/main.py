"""FastAPI entry: pipeline + async generation tools."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from slmagent import __version__
from slmagent.configs.settings import get_settings
from slmagent.contracts.models import Brief, GenerationMode
from slmagent.orchestrator.graph import run_pipeline
from slmagent.services.generation import get_generation_service
from slmagent.services.project_store import ProjectStore

app = FastAPI(
    title="SLMAgent API",
    description="Simple Local Media Agent — Gradio/API/LangGraph orchestration",
    version=__version__,
)


class GenerateImageRequest(BaseModel):
    prompt: str
    output_path: str
    output_name: str = "image.png"
    aspect_ratio: str = "16:9"
    seed: Optional[int] = None
    reference_image_path: Optional[str] = None


class GenerateVideoRequest(BaseModel):
    prompt: str
    output_path: str
    output_name: str = "video.mp4"
    mode: GenerationMode = GenerationMode.FL2VA
    duration_sec: int = 5
    resolution: str = "768p"
    first_frame_path: Optional[str] = None
    last_frame_path: Optional[str] = None


class PipelineRequest(BaseModel):
    brief: Brief


class PipelineResponse(BaseModel):
    project_id: str
    status: str
    final_video_path: Optional[str] = None
    first_frame_path: Optional[str] = None
    last_frame_path: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    manifest_path: Optional[str] = None
    # Actual modes used by this pipeline run (from orchestrator state / manifest).
    backend: str = "mock"
    llm_mode: str = "mock"


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    backend = settings.generation_backend
    llm_mode = settings.resolved_llm_mode()
    if backend == "live":
        note = (
            "generation_backend=live; media adapters are live. "
            f"llm_mode={llm_mode}. "
            "OpenCLIP thresholds and full LLM-live planning are separate claims."
        )
    else:
        note = (
            "generation_backend=mock; media outputs are placeholders, "
            "not a claim of real FLUX/H3 deployment."
        )
    return {
        "ok": True,
        "version": __version__,
        "generation_backend": backend,
        "llm_mode": llm_mode,
        "note": note,
    }


@app.post("/tools/generate_image")
def generate_image(req: GenerateImageRequest) -> dict[str, Any]:
    job = get_generation_service().generate_image(req.model_dump())
    return job.model_dump(mode="json")


@app.post("/tools/generate_video")
def generate_video(req: GenerateVideoRequest) -> dict[str, Any]:
    job = get_generation_service().generate_video(req.model_dump())
    return job.model_dump(mode="json")


@app.get("/tools/get_generation_job/{job_id}")
def get_generation_job(job_id: str) -> dict[str, Any]:
    job = get_generation_service().get_job(job_id)
    return job.model_dump(mode="json")


@app.post("/pipeline/run", response_model=PipelineResponse)
def pipeline_run(req: PipelineRequest) -> PipelineResponse:
    try:
        result = run_pipeline(req.brief)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    project_id = result["project_id"]
    store = ProjectStore()
    manifest = store.path(project_id, "final_manifest.json")
    return PipelineResponse(
        project_id=project_id,
        status=result.get("status", "unknown"),
        final_video_path=result.get("final_video_path"),
        first_frame_path=result.get("first_frame_path"),
        last_frame_path=result.get("last_frame_path"),
        warnings=list(result.get("warnings") or []),
        manifest_path=str(manifest) if manifest.exists() else None,
        backend=str(result.get("backend") or "mock"),
        llm_mode=str(result.get("llm_mode") or "mock"),
    )


@app.get("/projects/{project_id}/manifest")
def get_manifest(project_id: str) -> dict[str, Any]:
    store = ProjectStore()
    path = store.path(project_id, "final_manifest.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")
    return store.read_json(project_id, "final_manifest.json")


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "slmagent.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
