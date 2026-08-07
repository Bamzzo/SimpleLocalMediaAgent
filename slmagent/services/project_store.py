"""Filesystem-backed project run store."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slmagent.configs.settings import get_settings


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


class ProjectStore:
    def __init__(self, runs_dir: Path | None = None) -> None:
        settings = get_settings()
        self.runs_dir = Path(runs_dir or settings.runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create_project(self, project_name: str) -> tuple[str, Path]:
        # Keep filesystem IDs ASCII-safe for cross-platform runs.
        ascii_slug = "".join(ch if ("a" <= ch.lower() <= "z") or ch.isdigit() or ch in "-_" else "_" for ch in project_name)
        ascii_slug = "_".join(part for part in ascii_slug.split("_") if part)[:32] or "project"
        project_id = f"{_now_stamp()}_{ascii_slug}_{uuid.uuid4().hex[:6]}"
        root = self.runs_dir / project_id
        for sub in ("prompts", "uploads", "images", "videos", "final"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return project_id, root

    def path(self, project_id: str, *parts: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ValueError("invalid project_id")
        return self.runs_dir / project_id / Path(*parts)

    def write_json(self, project_id: str, relative: str, data: Any) -> Path:
        path = self.path(project_id, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(data, "model_dump"):
            payload = data.model_dump(mode="json")
        else:
            payload = data
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def read_json(self, project_id: str, relative: str) -> Any:
        path = self.path(project_id, relative)
        return json.loads(path.read_text(encoding="utf-8"))

    def save_upload(self, project_id: str, src: Path, name: str | None = None) -> Path:
        dest = self.path(project_id, "uploads", name or src.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def append_error(self, project_id: str, record: dict[str, Any]) -> None:
        path = self.path(project_id, "errors.json")
        items: list[Any] = []
        if path.exists():
            items = json.loads(path.read_text(encoding="utf-8"))
        items.append(record)
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
