from __future__ import annotations

from slmagent.contracts.models import Brief, Storyboard, VideoPrompt


def build_video_prompt(
    brief: Brief,
    storyboard: Storyboard,
    *,
    first_frame_path: str | None,
    last_frame_path: str | None,
) -> VideoPrompt:
    shot = storyboard.shots[0]
    prompt = (
        f"{shot.action}. Camera move: {shot.camera_move}. "
        f"Scene: {shot.scene}. Subject: {shot.subject}. "
        f"Style: {shot.style_notes or brief.visual_style.value}. "
        f"Smooth continuous motion over {brief.duration_sec} seconds, "
        f"no jump cuts, maintain subject consistency."
    )
    return VideoPrompt(
        prompt=prompt,
        negative_prompt="jitter, morphing face, flicker, watermark",
        mode=brief.generation_mode,
        duration_sec=brief.duration_sec,
        resolution="768p",
        aspect_ratio=brief.aspect_ratio.value,
        first_frame_path=first_frame_path,
        last_frame_path=last_frame_path,
    )
