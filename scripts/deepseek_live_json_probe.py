"""Phase A.2: probe DeepSeek live JSON for CreativePlan + Storyboard (3 cases).

Keeps GENERATION_BACKEND=mock. Does not call FLUX/H3.
Never writes API keys into evidence files.
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slmagent.configs.settings import get_settings
from slmagent.contracts.models import Brief, CreativePlan, Storyboard
from slmagent.services.llm.client import LLMClient


def _mask_secrets(text: str, api_key: str) -> str:
    if not text:
        return text
    out = text
    if api_key:
        out = out.replace(api_key, "***REDACTED***")
        if len(api_key) > 8:
            out = out.replace(api_key[:8], "***")
    return out


def _chat_raw(settings, system: str, user: str) -> dict[str, Any]:
    url = settings.llm_base_url.rstrip("/") + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.llm_model,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(url, headers=headers, json=body)
        status = resp.status_code
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            payload = {"raw_text": resp.text}
        resp.raise_for_status()
        content = payload["choices"][0]["message"]["content"]
    return {
        "http_status": status,
        "model": payload.get("model"),
        "usage": payload.get("usage"),
        "content": content,
        "content_preview": content[:1200],
    }


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _validate_case(name: str, brief: Brief) -> dict[str, Any]:
    settings = get_settings()
    client = LLMClient(settings)
    record: dict[str, Any] = {
        "case": name,
        "brief_mode": brief.mode,
        "has_reference": bool(brief.reference_image_paths),
        "llm_mode_resolved": client.mode,
        "creative": {},
        "storyboard": {},
        "ok": False,
        "fix_strategy": "",
    }
    if client.mode != "live":
        record["error"] = "LLM did not resolve to live (check LLM_MODE and LLM_API_KEY)"
        record["fix_strategy"] = "Ensure LLM_MODE=live and non-empty LLM_API_KEY, then clear settings cache."
        return record

    # Creative
    try:
        raw_c = _chat_raw(settings, client._creative_system(), client._creative_user(brief))
        record["creative"]["raw_preview"] = _mask_secrets(raw_c["content_preview"], settings.llm_api_key)
        record["creative"]["usage"] = raw_c.get("usage")
        record["creative"]["model"] = raw_c.get("model")
        parsed_c = _parse_json(raw_c["content"])
        creative = CreativePlan.model_validate(parsed_c)
        record["creative"]["pydantic"] = "pass"
        record["creative"]["parsed"] = creative.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        record["creative"]["pydantic"] = "fail"
        record["creative"]["error"] = _mask_secrets(f"{type(exc).__name__}: {exc}", settings.llm_api_key)
        record["creative"]["traceback"] = _mask_secrets(traceback.format_exc(limit=4), settings.llm_api_key)
        record["fix_strategy"] = (
            "Tighten system prompt fields; retry with temperature=0; "
            "if enum/type mismatch, coerce arrays/strings before validate."
        )
        return record

    # Storyboard
    try:
        raw_s = _chat_raw(
            settings,
            client._storyboard_system(),
            client._storyboard_user(brief, creative),
        )
        record["storyboard"]["raw_preview"] = _mask_secrets(raw_s["content_preview"], settings.llm_api_key)
        record["storyboard"]["usage"] = raw_s.get("usage")
        record["storyboard"]["model"] = raw_s.get("model")
        parsed_s = _parse_json(raw_s["content"])
        storyboard = Storyboard.model_validate(parsed_s)
        record["storyboard"]["pydantic"] = "pass"
        record["storyboard"]["parsed"] = storyboard.model_dump(mode="json")
        shot_count = len(storyboard.shots)
        record["storyboard"]["shot_count"] = shot_count
        if shot_count != 1:
            record["storyboard"]["pydantic"] = "fail"
            record["storyboard"]["error"] = f"expected 1 shot, got {shot_count}"
            record["fix_strategy"] = "Add hard constraint in prompt: shots length must be exactly 1."
            return record
        if storyboard.shots[0].duration_sec != 5:
            record["warnings"] = [
                f"shot duration_sec={storyboard.shots[0].duration_sec}, expected 5 (soft warning)"
            ]
    except Exception as exc:  # noqa: BLE001
        record["storyboard"]["pydantic"] = "fail"
        record["storyboard"]["error"] = _mask_secrets(f"{type(exc).__name__}: {exc}", settings.llm_api_key)
        record["storyboard"]["traceback"] = _mask_secrets(traceback.format_exc(limit=4), settings.llm_api_key)
        record["fix_strategy"] = (
            "Align generation_mode enum to Chinese labels; ensure shots is a one-element array; "
            "retry once with stricter JSON schema reminder."
        )
        return record

    record["ok"] = True
    return record


def _build_cases() -> list[tuple[str, Brief]]:
    defaults = yaml.safe_load((ROOT / "slmagent" / "configs" / "defaults.yaml").read_text(encoding="utf-8"))
    demo = defaults["demo_case"]
    ref = ROOT / "runs" / "_manual_accept" / "ref_product.png"
    cases = [
        (
            "default_brief",
            Brief(
                project_name=demo["project_name"],
                mode="free",
                description=demo["description"],
                selling_points=demo["selling_points"],
                audience=demo["audience"],
                constraints=demo["constraints"],
            ),
        ),
        (
            "script_mode",
            Brief(
                project_name="智影剧本驱动样例",
                mode="script",
                description="",
                selling_points="结构化分镜, 自动化成片",
                audience="高校创新团队",
                constraints="单镜头5秒, 16:9, 768p",
                script_text=(
                    "画面从深色科技空间拉开，中央浮现智影平台界面。"
                    "镜头缓慢推进，数据流汇聚到品牌标识，最后定格产品名。"
                    "旁白强调：从 Brief 到关键帧再到视频的全自动链路。"
                ),
            ),
        ),
        (
            "brief_with_reference",
            Brief(
                project_name=demo["project_name"] + "_ref",
                mode="free",
                description=demo["description"],
                selling_points=demo["selling_points"],
                audience=demo["audience"],
                constraints=demo["constraints"] + ", 保持参考图主体色调",
                reference_image_paths=[str(ref)] if ref.exists() else [],
            ),
        ),
    ]
    return cases


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.llm_api_key.strip():
        print("FAIL: LLM_API_KEY empty")
        raise SystemExit(1)
    if settings.resolved_llm_mode() != "live":
        print("FAIL: set LLM_MODE=live before running this probe")
        raise SystemExit(1)
    if settings.generation_backend != "mock":
        print("FAIL: GENERATION_BACKEND must remain mock for A.2")
        raise SystemExit(1)

    out_dir = ROOT / "runs" / "_deepseek_live_probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "generation_backend": settings.generation_backend,
        "api_key_present": True,
        "api_key_prefix": settings.llm_api_key[:6] + "***",
        "cases": [],
    }

    all_ok = True
    for name, brief in _build_cases():
        print(f"== case {name} ==")
        record = _validate_case(name, brief)
        results["cases"].append(record)
        print("  ok=", record["ok"], "creative=", record["creative"].get("pydantic"), "storyboard=", record["storyboard"].get("pydantic"))
        if record.get("error"):
            print("  error=", record["error"])
        if not record["ok"]:
            all_ok = False
            print("  fix=", record.get("fix_strategy"))

    results["finished_at"] = datetime.now(timezone.utc).isoformat()
    results["all_ok"] = all_ok
    json_path = out_dir / f"probe_{stamp}.json"
    md_path = ROOT / "docs" / "DEEPSEEK_LIVE_JSON_PROBE.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# DeepSeek Live JSON Probe (Phase A.2)",
        "",
        f"- Time (UTC): `{results['started_at']}`",
        f"- Model: `{results['llm_model']}` @ `{results['llm_base_url']}`",
        f"- Generation backend: `{results['generation_backend']}` (must stay mock)",
        f"- Overall: **{'PASS' if all_ok else 'FAIL'}**",
        f"- Raw evidence JSON: `{json_path.relative_to(ROOT).as_posix()}`",
        "",
        "| Case | CreativePlan | Storyboard | OK | Notes |",
        "|---|---|---|---|---|",
    ]
    for c in results["cases"]:
        note = c.get("fix_strategy") or "; ".join(c.get("warnings") or []) or "-"
        err = c.get("creative", {}).get("error") or c.get("storyboard", {}).get("error") or c.get("error") or ""
        if err:
            note = err
        lines.append(
            f"| {c['case']} | {c.get('creative', {}).get('pydantic', '-')} | "
            f"{c.get('storyboard', {}).get('pydantic', '-')} | {'yes' if c.get('ok') else 'no'} | {note} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "- API key is redacted; only prefix stored in evidence JSON.",
            "- This probe validates structured JSON only; it does not claim FLUX/H3 quality.",
            "- After probe, restore `LLM_MODE=mock` in `.env`.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", json_path)
    print("WROTE", md_path)
    print("OVERALL", "PASS" if all_ok else "FAIL")
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
