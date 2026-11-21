"""Prompt builders for the image and video models."""

from __future__ import annotations

from typing import Optional

from .claude_vision import StudentProfile

STYLE_DESCRIPTION = (
    "Hand-painted digital caricature in a soft, realistic storybook style: an oversized head (about one third of "
    "the total height) on a small, energetic body. Highly detailed, lifelike face with big glossy eyes, soft "
    "airbrushed skin shading and fine individual hair strands with a few flyaways; the body and clothes are "
    "painted more simply with clean, thin outlines and gentle cel shading. Warm, even studio lighting from the "
    "front, soft contact shadows on the ground, a couple of small curved motion lines to suggest movement. "
    "Full body, centred, with generous margin on all sides, on a pure plain white background."
)

DEFAULT_ACTIVITY = (
    "mid-hop through a line of colourful hoops lying flat on the ground (purple, blue, green, yellow, red, "
    "receding diagonally into the distance), running pose with fists pumping, one foot landing inside a hoop"
)

DEFAULT_OUTFIT = "a sage-green and white raglan sports T-shirt, sage-green track pants with a white side stripe, light-green velcro sneakers and white socks"


def image_prompt(
    profile: StudentProfile,
    activity: Optional[str] = None,
    outfit: Optional[str] = None,
    fix_instructions: str = "",
) -> str:
    exaggerations = "; ".join(profile.caricature_exaggerations) or "slightly larger eyes and a bigger, warm smile"
    features = "; ".join(profile.distinctive_features + profile.accessories) or "none"
    parts = [
        "Image 1 is a photo of a school student. Image 2 is the art-style reference.",
        f"Create an original caricature of the student from Image 1, drawn in exactly the art style of Image 2. {STYLE_DESCRIPTION}",
        "LIKENESS (most important - classmates must instantly recognise this child): "
        f"{profile.likeness_summary} Age {profile.apparent_age_range}. Face shape: {profile.face_shape}. "
        f"Skin tone: {profile.skin_tone}. Hair: {profile.hair}. Eyes: {profile.eyes}. Eyebrows: {profile.eyebrows}. "
        f"Nose: {profile.nose}. Mouth and smile: {profile.mouth_and_smile}. Ears: {profile.ears}. "
        f"Keep these details: {features}.",
        f"Gentle caricature exaggerations: {exaggerations}. Keep the expression friendly, confident and joyful.",
        f"ACTION: the student is {activity or DEFAULT_ACTIVITY}.",
        f"OUTFIT: {outfit or DEFAULT_OUTFIT}.",
        "Anatomy: two arms, two legs, five fingers on each hand, both feet fully visible inside the frame.",
        "Take only the art style from Image 2: do not copy the face, hair or identity of the child in Image 2.",
    ]
    if fix_instructions:
        parts.append(f"CORRECTIONS FROM THE PREVIOUS ATTEMPT: {fix_instructions}")
    parts.append("Plain white background. No text, no lettering, no watermark, no logos, no frame or border.")
    return "\n\n".join(parts)


def video_prompt(activity: Optional[str] = None) -> str:
    return (
        "Animate this caricature illustration as a short, seamless, joyful loop. Keep the exact art style, "
        "character design, face, outfit, colours and plain white background from the first frame; the camera "
        "stays locked off with no cuts or zooms. "
        f"The child is {activity or DEFAULT_ACTIVITY}: they bounce lightly and playfully in place with springy "
        "squash-and-stretch, arms swinging, the big head bobbing a little, hair swishing, and a brief happy blink "
        "and smile. Props on the ground stay still. Smooth, gentle, cartoon-like motion. No text, no extra people."
    )
