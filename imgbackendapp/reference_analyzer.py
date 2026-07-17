"""Reusable service for analyzing reference images with Gemini Vision."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re
from typing import Iterable, Optional

from django.conf import settings

from imgbackend.ai_utils import genai

from .reference_analysis_prompts import (
    DEFAULT_REFERENCE_TYPE,
    REFERENCE_ANALYSIS_PROMPTS,
    REFERENCE_TYPE_ALIASES,
)

logger = logging.getLogger(__name__)

GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-pro")


def normalize_reference_type(reference_type: str) -> str:
    """Map aliases and unknown types to a supported analysis prompt key."""
    normalized = (reference_type or DEFAULT_REFERENCE_TYPE).strip().lower()
    normalized = REFERENCE_TYPE_ALIASES.get(normalized, normalized)
    if normalized not in REFERENCE_ANALYSIS_PROMPTS:
        return DEFAULT_REFERENCE_TYPE
    return normalized


def _detect_mime_type(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type and mime_type.startswith("image/"):
        return mime_type
    return "image/jpeg"


def _clean_analysis_output(text: str) -> str:
    """Normalize model output into a single paragraph suitable for prompt append."""
    if not text:
        return ""

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|markdown|text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""

    bullet_lines = []
    prose_lines = []
    for line in lines:
        if re.match(r"^[-*•]\s+", line):
            bullet_lines.append(re.sub(r"^[-*•]\s+", "", line).strip())
        else:
            prose_lines.append(line)

    if bullet_lines and not prose_lines:
        cleaned = " ".join(bullet_lines)
    elif prose_lines:
        cleaned = " ".join(prose_lines)
    else:
        cleaned = " ".join(lines)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


_EMPTY_DRESS_PATTERNS = re.compile(
    r"^(none|n/?a|null|nil|no dress|no outfit|no clothing|not applicable|"
    r"no attire|empty|nothing|no garment)[.!]?\s*$",
    re.IGNORECASE,
)


def _normalize_dress_output(text: str) -> str:
    """Return dress analysis text, or empty when none / not worn."""
    cleaned = _clean_analysis_output(text)
    if not cleaned:
        return ""
    if _EMPTY_DRESS_PATTERNS.match(cleaned):
        return ""
    return cleaned


def _call_gemini_vision(prompt: str, image_path: str) -> Optional[str]:
    """Call AI Vision with a local image file."""
    api_key = getattr(settings, "GEMINI_API_KEY", None) or getattr(
        settings, "GOOGLE_API_KEY", None
    ) or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("Reference image analysis skipped: AI not configured")
        return None

    try:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = _detect_mime_type(image_path)
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_TEXT_MODEL,
            contents=[
                prompt,
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ],
        )
        return (response.text or "").strip() or None
    except Exception as exc:
        logger.exception("AI Vision reference analysis failed: %s", exc)
        return None


def analyze_reference_image(reference_image_path: str, reference_type: str = "custom") -> str:
    """
    Analyze a reference image and return an optimized text description.

    Args:
        reference_image_path: Absolute or resolvable path to the temporary reference image.
        reference_type: Analysis category (background, campaign, pose, dress, etc.).

    Returns:
        A single paragraph description, or an empty string if analysis fails / no dress.
    """
    if not reference_image_path or not os.path.exists(reference_image_path):
        logger.warning(
            "Reference image analysis skipped: file not found (%s)",
            reference_image_path,
        )
        return ""

    prompt_key = normalize_reference_type(reference_type)
    analysis_prompt = REFERENCE_ANALYSIS_PROMPTS[prompt_key]
    raw_result = _call_gemini_vision(analysis_prompt, reference_image_path)
    if not raw_result:
        return ""

    if prompt_key == "dress":
        cleaned = _normalize_dress_output(raw_result)
    else:
        cleaned = _clean_analysis_output(raw_result)

    if not cleaned and prompt_key != "dress":
        logger.warning(
            "Reference image analysis returned empty output for type=%s path=%s",
            prompt_key,
            reference_image_path,
        )
    return cleaned


def analyze_pose_and_dress(reference_image_path: str) -> dict:
    """
    Run pose + dress analysis for model/campaign reference images.

    Returns:
        {"analysis_text": str, "dress": str}
        dress is empty when no attire is worn by a model/human.
    """
    return {
        "analysis_text": analyze_reference_image(reference_image_path, "pose"),
        "dress": analyze_reference_image(reference_image_path, "dress"),
    }


def analyze_campaign_and_dress(reference_image_path: str) -> dict:
    """
    Run campaign style + dress analysis for theme/campaign reference images.

    Returns:
        {"analysis_text": str, "dress": str}
    """
    return {
        "analysis_text": analyze_reference_image(reference_image_path, "campaign"),
        "dress": analyze_reference_image(reference_image_path, "dress"),
    }



def safe_delete_reference_file(file_path: Optional[str]) -> None:
    """Delete a temporary reference image file if it exists."""
    if not file_path or not os.path.isfile(file_path):
        return
    try:
        os.remove(file_path)
        logger.debug("Deleted temporary reference image: %s", file_path)
    except OSError as exc:
        logger.warning("Failed to delete temporary reference image %s: %s", file_path, exc)


def combine_reference_analyses(analyses: Iterable[str]) -> str:
    """Merge multiple reference analyses into one prompt-ready paragraph."""
    parts = [analysis.strip() for analysis in analyses if analysis and analysis.strip()]
    return " ".join(parts).strip()
