"""Route image generation to Gemini (regular) or OpenAI gpt-image-1 (premium)."""

import base64
import io
import logging
import os
import re
from typing import Iterable, List, Optional, Sequence, Tuple

from django.conf import settings
from google import genai
from google.genai import types
from PIL import Image

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
    _ = (value, default)
    # Premium/OpenAI view is disabled for now.
    # if tier in {"premium", "openai", "gpt", "gpt-image-1"}:
    #     return "premium"
    return "regular"


def parse_model_tier(request, default="regular") -> str:
    return normalize_model_tier(request.POST.get("model_tier"), default=default)


OPENAI_SIZE_ASPECTS = {
    "1024x1024": 1.0,
    "1536x1024": 1536 / 1024,
    "1024x1536": 1024 / 1536,
}

GEMINI_SUPPORTED_ASPECT_RATIOS = (
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
)

CLOTHING_RULES_SUFFIX = (
    " CRITICAL CLOTHING RULES: The model must be wearing modest, elegant, highly professional, "
    "and decent apparel suitable for a luxury brand campaign (such as a high-neck blouse with "
    "related saree, premium formal dress, or elegant corporate apparel, this all should depend "
    "on the ornament). Absolutely no revealing, plunging, low-cut, or inappropriate clothing is "
    "allowed under any circumstances. Ensure the attire is sophisticated and completely decent."
)

GEMINI_SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
]


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


def map_dimension_to_gemini_aspect_ratio(dimension: str) -> str:
    normalized = (dimension or "1:1").strip().replace(" ", "")
    if normalized in GEMINI_SUPPORTED_ASPECT_RATIOS:
        return normalized

    parsed = parse_aspect_ratio(normalized)
    if not parsed:
        logger.warning(
            "Unmapped dimension %r; defaulting Gemini aspect ratio to 1:1",
            dimension,
        )
        return "1:1"

    width_ratio, height_ratio = parsed
    target_aspect = width_ratio / height_ratio
    return min(
        GEMINI_SUPPORTED_ASPECT_RATIOS,
        key=lambda ratio: abs(
            (parse_aspect_ratio(ratio)[0] / parse_aspect_ratio(ratio)[1]) - target_aspect
        ),
    )


def _append_clothing_rules_to_contents(contents) -> list:
    updated = []
    clothing_marker = "CRITICAL CLOTHING RULES:"
    for item in contents or []:
        if isinstance(item, dict) and "text" in item:
            text = item["text"]
            if clothing_marker not in text:
                updated.append({**item, "text": f"{text}{CLOTHING_RULES_SUFFIX}"})
            else:
                updated.append(item)
            continue

        parts = item.get("parts") if isinstance(item, dict) else None
        if parts:
            new_parts = []
            for part in parts:
                if isinstance(part, dict) and "text" in part:
                    text = part["text"]
                    if clothing_marker not in text:
                        new_parts.append(
                            {**part, "text": f"{text}{CLOTHING_RULES_SUFFIX}"}
                        )
                    else:
                        new_parts.append(part)
                else:
                    new_parts.append(part)
            updated.append({**item, "parts": new_parts})
            continue

        updated.append(item)
    return updated


def _crop_image_to_dimension(image_bytes: bytes, dimension: str) -> bytes:
    parsed = parse_aspect_ratio((dimension or "").strip().replace(" ", ""))
    if not parsed:
        return image_bytes

    width_ratio, height_ratio = parsed
    target_aspect = width_ratio / height_ratio

    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        width, height = img.size
        current_aspect = width / height

        if abs(current_aspect - target_aspect) < 0.001:
            cropped = img
        elif current_aspect > target_aspect:
            new_width = int(height * target_aspect)
            left = (width - new_width) // 2
            cropped = img.crop((left, 0, left + new_width, height))
        else:
            new_height = int(width / target_aspect)
            top = (height - new_height) // 2
            cropped = img.crop((0, top, width, top + new_height))

        output = io.BytesIO()
        cropped.save(output, format="JPEG", quality=95)
        return output.getvalue()


def _log_gemini_response_diagnostics(response, *, model_name: str, dimension: str, aspect: str) -> None:
    prompt_feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(prompt_feedback, "block_reason", None)
    safety_ratings = getattr(prompt_feedback, "safety_ratings", None)
    logger.error(
        "Gemini returned no candidates model=%s requested_dimension=%s gemini_aspect=%s "
        "block_reason=%s safety_ratings=%s",
        model_name,
        dimension,
        aspect,
        block_reason,
        safety_ratings,
    )


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

    api_key = getattr(settings, "GEMINI_API_KEY", None) or getattr(
        settings, "GOOGLE_API_KEY", None
    )
    if not api_key:
        raise RuntimeError("GEMINI/GOOGLE API key not configured")

    configured_model = get_image_model_name(default_model="gemini-3-pro-image")
    model_name = (
        "gemini-3-pro-image"
        if str(configured_model).strip().lower().startswith("imagen-")
        else configured_model
    )

    prepared_contents = _append_clothing_rules_to_contents(contents)
    aspect = map_dimension_to_gemini_aspect_ratio(dimension)
    normalized_dimension = (dimension or "1:1").strip().replace(" ", "")
    if normalized_dimension and normalized_dimension != aspect:
        logger.info(
            "Mapped requested dimension %s to nearest Gemini aspect ratio %s",
            normalized_dimension,
            aspect,
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prepared_contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            safety_settings=GEMINI_SAFETY_SETTINGS,
            image_config=types.ImageConfig(
                image_size="4K",
                aspect_ratio=aspect,
            ),
        ),
    )

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        _log_gemini_response_diagnostics(
            response,
            model_name=model_name,
            dimension=normalized_dimension,
            aspect=aspect,
        )
        raise RuntimeError("Gemini returned no candidates")

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    safety_ratings = getattr(candidate, "safety_ratings", None)
    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    for part in parts:
        inline_data = getattr(part, "inline_data", None)
        if not inline_data:
            continue
        data = getattr(inline_data, "data", None)
        if not data:
            continue
        generated_bytes = data if isinstance(data, bytes) else base64.b64decode(data)
        if generated_bytes:
            logger.info(
                "Gemini image generated model=%s dimension=%s gemini_aspect=%s finish_reason=%s",
                model_name,
                normalized_dimension,
                aspect,
                finish_reason,
            )
            return _crop_image_to_dimension(generated_bytes, normalized_dimension)

    logger.error(
        "Gemini candidate contained no inline image data model=%s dimension=%s "
        "gemini_aspect=%s finish_reason=%s safety_ratings=%s part_count=%s",
        model_name,
        normalized_dimension,
        aspect,
        finish_reason,
        safety_ratings,
        len(parts),
    )
    raise RuntimeError("Gemini returned no inline image data")


def generate_image_bytes(
    model_tier,
    *,
    prompt: str,
    gemini_contents=None,
    reference_paths: Optional[Sequence[str]] = None,
    dimension: str = "1:1",
) -> bytes:
    tier = normalize_model_tier(model_tier)
    # Premium/OpenAI path remains in place but is unreachable while tier normalization
    # is forced to "regular" above.
    if tier == "premium":
        logger.info("Using OpenAI model %s for image generation", OPENAI_IMAGE_MODEL)
        return generate_with_openai(prompt, reference_paths, dimension)

    if gemini_contents is None:
        raise RuntimeError("Gemini generation requires gemini_contents")

    clothing_marker = "CRITICAL CLOTHING RULES:"
    enriched_prompt = prompt
    if clothing_marker not in prompt:
        enriched_prompt = f"{prompt}{CLOTHING_RULES_SUFFIX}"

    prepared_contents = _append_clothing_rules_to_contents(gemini_contents)
    logger.info(
        "Using Gemini for image generation dimension=%s prompt_chars=%s",
        dimension,
        len(enriched_prompt),
    )
    return generate_with_gemini(prepared_contents, dimension)
