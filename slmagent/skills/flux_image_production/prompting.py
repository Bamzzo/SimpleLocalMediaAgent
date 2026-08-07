from __future__ import annotations

from slmagent.contracts.models import Brief, ImagePrompt, Storyboard


def build_image_prompt(brief: Brief, storyboard: Storyboard) -> ImagePrompt:
    shot = storyboard.shots[0]
    base = (
        f"{shot.subject}, {shot.scene}, {shot.composition}, {shot.shot_size}, "
        f"{shot.lighting}, style: {shot.style_notes or brief.visual_style.value}, "
        f"cinematic still, high detail, aspect ratio {brief.aspect_ratio.value}"
    )
    first = (
        f"First keyframe: {base}. Action setup: {shot.action}. "
        f"Camera ready for {shot.camera_move}. Clean product-focused framing."
    )
    last = (
        f"Last keyframe: {base}. End pose of action: {shot.action}. "
        f"Strong brand lockup, settled composition after {shot.camera_move}."
    )
    return ImagePrompt(
        first_frame_prompt=first,
        last_frame_prompt=last,
        negative_prompt="blurry, deformed hands, watermark, low resolution, text artifacts",
        aspect_ratio=brief.aspect_ratio.value,
        reference_image_paths=list(brief.reference_image_paths),
        seed=42,
    )
