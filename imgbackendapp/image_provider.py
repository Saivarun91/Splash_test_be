"""Route image generation to Gemini (regular) or OpenAI gpt-image-1 (premium)."""

import base64
import logging
import os
import re
from typing import Iterable, List, Optional, Sequence, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

OPENAI_IMAGE_MODEL = "gpt-image-1"

DIMENSION_TO_OPENAI_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "4:5": "1024x1536",
    "9:16": "1024x1536",
    "3:4": "1024x1536",
    "4:3": "1536x1024",
}


def normalize_model_tier(value, default="regular") -> str:
    tier = (value or default).strip().lower()
    if tier in {"premium", "openai", "gpt", "gpt-image-1"}:
        return "premium"
    return "regular"


def parse_model_tier(request, default="regular") -> str:
    return normalize_model_tier(request.POST.get("model_tier"), default=default)


OPENAI_SIZE_ASPECTS = {
    "1024x1024": 1.0,
    "1536x1024": 1536 / 1024,
    "1024x1536": 1024 / 1536,
}


def parse_aspect_ratio(dimension: str) -> Optional[Tuple[float, float]]:
    normalized = (dimension or "").strip().replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", normalized)
    if not match:
        return None

    width_ratio = float(match.group(1))
    height_ratio = float(match.group(2))
    if width_ratio <= 0 or height_ratio <= 0:
        return None

    return width_ratio, height_ratio


def map_dimension_to_openai_size(dimension: str) -> str:
    if not dimension:
        return "1024x1024"

    normalized = dimension.strip().replace(" ", "")
    if normalized in DIMENSION_TO_OPENAI_SIZE:
        return DIMENSION_TO_OPENAI_SIZE[normalized]

    parsed = parse_aspect_ratio(normalized)
    if not parsed:
        return "1024x1024"

    width_ratio, height_ratio = parsed
    target_aspect = width_ratio / height_ratio

    return min(
        OPENAI_SIZE_ASPECTS,
        key=lambda size: abs(OPENAI_SIZE_ASPECTS[size] - target_aspect),
    )


def collect_existing_paths(paths: Optional[Iterable[str]]) -> List[str]:
    collected = []
    for path in paths or []:
        if path and os.path.exists(path):
            collected.append(path)
    return collected


def _get_openai_api_key() -> str:
    api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI API key not configured")
    return api_key


def generate_with_openai(
    prompt: str,
    reference_paths: Optional[Sequence[str]] = None,
    dimension: str = "1:1",
) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=_get_openai_api_key())
    size = map_dimension_to_openai_size(dimension)
    valid_paths = collect_existing_paths(reference_paths)
    opened_files = []

    try:
        if valid_paths:
            opened_files = [open(path, "rb") for path in valid_paths]
            image_input = opened_files[0] if len(opened_files) == 1 else opened_files
            response = client.images.edit(
                model=OPENAI_IMAGE_MODEL,
                image=image_input,
                prompt=prompt,
                size=size,
                quality="high",
                input_fidelity="high",
            )
        else:
            response = client.images.generate(
                model=OPENAI_IMAGE_MODEL,
                prompt=prompt,
                size=size,
                quality="high",
            )

        if not response.data:
            raise RuntimeError("OpenAI returned no image data")

        item = response.data[0]
        if getattr(item, "b64_json", None):
            return base64.b64decode(item.b64_json)

        if getattr(item, "url", None):
            from urllib.request import urlopen

            with urlopen(item.url) as resp:
                return resp.read()

        raise RuntimeError("OpenAI response missing image bytes")
    finally:
        for handle in opened_files:
            try:
                handle.close()
            except Exception:
                logger.warning("Failed closing OpenAI reference file handle")


def generate_with_gemini(contents, dimension: str = "1:1") -> bytes:
    from CREDITS.utils import get_image_model_name

    try:
        from imgbackend.ai_utils import genai, types
    except ImportError as exc:
        raise RuntimeError("Gemini SDK not installed.") from exc

    api_key = getattr(settings, "GEMINI_API_KEY", None) or getattr(
        settings, "GOOGLE_API_KEY", None
    )
    if not api_key:
        raise RuntimeError("GEMINI/GOOGLE API key not configured")

    configured_model = get_image_model_name(default_model="gemini-3-pro-image-preview")
    model_name = (
        "gemini-3-pro-image-preview"
        if str(configured_model).strip().lower().startswith("imagen-")
        else configured_model
    )

    client = genai.Client(api_key=api_key)
    
    # Normalize aspect ratio to one supported by types.ImageConfig
    supported_ratios = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
    aspect = (dimension or "1:1").strip().replace(" ", "")
    if aspect not in supported_ratios:
        aspect = "1:1"

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                image_size="4K",
                aspect_ratio=aspect
            )
        ),
    )

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    parts = getattr(getattr(candidates[0], "content", None), "parts", None) or []
    for part in parts:
        inline_data = getattr(part, "inline_data", None)
        if not inline_data:
            continue
        data = getattr(inline_data, "data", None)
        if not data:
            continue
        generated_bytes = data if isinstance(data, bytes) else base64.b64decode(data)
        if generated_bytes:
            return generated_bytes

    raise RuntimeError("Gemini returned no inline image data.")


def generate_image_bytes(
    model_tier,
    *,
    prompt: str,
    gemini_contents=None,
    reference_paths: Optional[Sequence[str]] = None,
    dimension: str = "1:1",
) -> bytes:
    tier = normalize_model_tier(model_tier)
    if tier == "premium":
        logger.info("Using OpenAI model %s for image generation", OPENAI_IMAGE_MODEL)
        return generate_with_openai(prompt, reference_paths, dimension)

    if gemini_contents is None:
        raise RuntimeError("Gemini generation requires gemini_contents")
    logger.info("Using Gemini for image generation")
    return generate_with_gemini(gemini_contents, dimension)
