"""Shared helpers for multi-image generation batches."""

from .file_utils import _NON_FILE_PATH_VALUES, resolve_media_path

REFERENCE_IMAGE_USAGE_INSTRUCTION = (
    "This is the reference/style image ONLY. Use it for background, environment, "
    "lighting, surfaces, props, and atmosphere — NEVER for any ornament or jewelry."
)

REFERENCE_IMAGE_NO_ORNAMENT_RULE = (
    "STRICT REFERENCE IMAGE RULE (MANDATORY): The reference image is ONLY for scene "
    "style — backdrop, colors, lighting, surfaces, props, and atmosphere. Do NOT copy, "
    "reproduce, blend, or include ANY ornament, jewelry, necklace, earrings, bangles, "
    "rings, bracelet, pendant, chain, or accessory from the reference image. The ONLY "
    "ornament(s) allowed in the output are from the uploaded product image(s). If the "
    "reference shows jewelry on a model or anywhere in the scene, completely ignore and "
    "exclude that jewelry from the final image."
)

REFERENCE_DESCRIPTION_USAGE_INSTRUCTION = (
    "The following scene/style description was derived from a reference image. "
    "Use it ONLY for background, environment, lighting, surfaces, props, pose, and "
    "atmosphere — NEVER for any ornament or jewelry."
)

REFERENCE_DESCRIPTION_NO_ORNAMENT_RULE = (
    "STRICT REFERENCE DESCRIPTION RULE (MANDATORY): The reference description is ONLY "
    "for scene style — backdrop, colors, lighting, surfaces, props, pose, and atmosphere. "
    "Do NOT copy, reproduce, blend, or include ANY ornament, jewelry, necklace, earrings, "
    "bangles, rings, bracelet, pendant, chain, or accessory mentioned or implied in the "
    "reference description. The ONLY ornament(s) allowed in the output are from the "
    "uploaded product image(s)."
)

REGENERATION_ORIGINAL_ORNAMENT_INSTRUCTION = (
    "ORNAMENT LOCK: The ornament/product reference image(s) are the authoritative "
    "source for jewelry only. Preserve the ornament EXACTLY — identical design, "
    "shape, proportions, gemstones, metal finish, textures, and fine details. "
    "Do NOT redesign, restyle, or replace the ornament."
)

REGENERATION_ORIGINAL_ORNAMENTS_INSTRUCTION = (
    "ORNAMENT LOCK: The ornament/product reference image(s) are the authoritative "
    "sources for jewelry only. Preserve EVERY ornament EXACTLY — identical design, "
    "shape, proportions, gemstones, metal finish, textures, and fine details. "
    "Do NOT redesign, restyle, or replace any ornament."
)

REGENERATION_PREVIOUS_GENERATED_INSTRUCTION = (
    "BASE IMAGE LOCK: The previously generated image is the primary visual base. "
    "Keep the model identity, face, body, pose, camera angle, framing, background, "
    "lighting, atmosphere, styling, and DRESS/ATTIRE EXACTLY the same unless the "
    "user explicitly asks to change that specific element. Do not invent a new scene."
)

REGENERATION_APPLY_MODIFICATIONS_INSTRUCTION = (
    "CHANGE RULE (MANDATORY): Apply ONLY the user's requested regeneration change. "
    "Do NOT change anything else. Especially do NOT change the dress/outfit, colors of "
    "clothing, pose, model appearance, background, lighting, or composition unless the "
    "user explicitly requests that exact change. If the request does not mention dress "
    "or attire, the dress/attire must remain identical to the base generated image."
)

REGENERATION_MODEL_IMAGE_INSTRUCTION = (
    "When a model reference image is provided, use it only for the model's face, body "
    "and pose. Do not copy ornament details from the model image — ornament fidelity "
    "must always follow the original uploaded ornament image(s)."
)

_STANDARD_DIMENSIONS = (
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


def get_root_ornament_doc(doc):
    """Return the first image record in a regeneration chain."""
    current = doc
    seen = set()
    while getattr(current, "parent_image_id", None) and current.parent_image_id:
        parent_id = current.parent_image_id
        if parent_id in seen:
            break
        seen.add(parent_id)
        try:
            from .mongo_models import OrnamentMongo

            current = OrnamentMongo.objects.get(id=parent_id)
        except Exception:
            break
    return current


def resolve_original_ornament_sources(doc):
    """
    Return path/URL strings for the original uploaded ornament image(s) on ``doc``.
    """
    root = get_root_ornament_doc(doc)
    image_type = getattr(root, "type", "") or ""

    if image_type == "campaign_shot_advanced":
        ornament_urls = getattr(root, "uploaded_ornament_urls", None) or []
        if ornament_urls:
            return list(ornament_urls)
        if getattr(root, "uploaded_image_url", None):
            return [root.uploaded_image_url]
        return []

    if image_type == "real_model_with_ornament":
        if getattr(root, "uploaded_image_url", None):
            return [root.uploaded_image_url]
        return []

    uploaded_path = getattr(root, "uploaded_image_path", None)
    if uploaded_path and uploaded_path not in _NON_FILE_PATH_VALUES:
        return [uploaded_path]

    if getattr(root, "uploaded_image_url", None):
        return [root.uploaded_image_url]

    return []


def load_image_bytes_from_source(source):
    """Load image bytes from a local media path, filesystem path, or URL."""
    import os
    from urllib.request import urlopen

    if not source:
        raise FileNotFoundError("Empty image source")

    if source.startswith(("http://", "https://")):
        with urlopen(source) as resp:
            return resp.read()

    resolved_path = resolve_media_path(source)
    if resolved_path and os.path.exists(resolved_path):
        with open(resolved_path, "rb") as image_file:
            return image_file.read()

    if os.path.exists(source):
        with open(source, "rb") as image_file:
            return image_file.read()

    raise FileNotFoundError(f"Image not found for source: {source}")


def resolve_model_image_source(doc):
    """Return path/URL for the original model image when applicable."""
    root = get_root_ornament_doc(doc)
    image_type = getattr(root, "type", "") or ""

    if image_type not in ("real_model_with_ornament", "campaign_shot_advanced"):
        return None

    model_url = getattr(root, "model_image_url", None)
    if model_url:
        return model_url

    if image_type == "real_model_with_ornament":
        uploaded_path = getattr(root, "uploaded_image_path", None)
        if uploaded_path and uploaded_path not in _NON_FILE_PATH_VALUES:
            return uploaded_path

    return None


def infer_dimension_from_image_bytes(image_bytes):
    """Map image pixel dimensions to the nearest supported aspect ratio string."""
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(image_bytes)) as image:
        width, height = image.size

    if width <= 0 or height <= 0:
        return "1:1"

    aspect = width / height
    best_dimension = "1:1"
    best_diff = float("inf")

    for dimension in _STANDARD_DIMENSIONS:
        width_ratio, height_ratio = dimension.split(":")
        target_aspect = float(width_ratio) / float(height_ratio)
        diff = abs(aspect - target_aspect)
        if diff < best_diff:
            best_diff = diff
            best_dimension = dimension

    return best_dimension


def resolve_regeneration_dimension(doc, generated_image_bytes=None):
    """Return the aspect ratio to use when regenerating an image."""
    root = get_root_ornament_doc(doc)

    for candidate in (
        getattr(doc, "dimension", None),
        getattr(root, "dimension", None),
    ):
        if candidate and str(candidate).strip():
            return str(candidate).strip()

    if generated_image_bytes:
        return infer_dimension_from_image_bytes(generated_image_bytes)

    return "1:1"


def build_regeneration_image_instructions(*, ornament_count=1, has_model_image=False):
    """Prompt instructions: lock base image + ornament; apply only user change."""
    if ornament_count > 1:
        original_instruction = REGENERATION_ORIGINAL_ORNAMENTS_INSTRUCTION
    else:
        original_instruction = REGENERATION_ORIGINAL_ORNAMENT_INSTRUCTION

    instructions = (
        f"{REGENERATION_PREVIOUS_GENERATED_INSTRUCTION} "
        f"{original_instruction} "
        f"{REGENERATION_APPLY_MODIFICATIONS_INSTRUCTION}"
    )
    if has_model_image:
        instructions = f"{instructions} {REGENERATION_MODEL_IMAGE_INSTRUCTION}"
    return instructions


def parse_num_images(request, default=1, max_images=3):
    try:
        num = int(request.POST.get("num_images", str(default)) or default)
    except (TypeError, ValueError):
        num = default
    return max(1, min(max_images, num))


def build_variation_instruction(variation_index=0, total_variations=1):
    """
    Prompt suffix so each image in a batch keeps the same ornament and theme
    but produces a distinct composition.
    """
    if total_variations <= 1:
        return ""

    composition_hints = [
        (
            "Use a straight-on hero composition with the ornament centered and "
            "even, balanced lighting."
        ),
        (
            "Use a three-quarter angle with subtle depth-of-field and elegant "
            "off-center placement within the same themed setting."
        ),
        (
            "Use a creative editorial composition with a distinct camera angle, "
            "crop, or styling accent while preserving the same mood and theme."
        ),
    ]
    hint = composition_hints[variation_index % len(composition_hints)]

    return (
        f"\n\nVARIATION REQUIREMENT (image {variation_index + 1} of {total_variations}): "
        "Create a visually DISTINCT result from the other images in this batch. "
        "Preserve the EXACT same ornament/product — identical design, metal, stones, "
        "size, and proportions — and preserve the EXACT same theme, background style, "
        "and color palette. "
        "Only vary composition, camera angle, placement, pose, or subtle styling details. "
        "Do NOT duplicate the same framing as another variation. "
        f"{hint}"
    )


def dispatch_variation_tasks(task_fn, num_images, base_kwargs):
    """Enqueue one Celery task per variation; return task id(s) for polling."""
    if num_images <= 1:
        task = task_fn.delay(
            **base_kwargs,
            variation_index=0,
            total_variations=1,
        )
        return {"task_id": task.id, "task_ids": None}

    task_ids = []
    for index in range(num_images):
        task = task_fn.delay(
            **base_kwargs,
            variation_index=index,
            total_variations=num_images,
        )
        task_ids.append(task.id)

    return {"task_id": task_ids[0], "task_ids": task_ids}
