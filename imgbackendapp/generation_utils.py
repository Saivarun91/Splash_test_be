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

MULTI_PRODUCT_BACKGROUND_CHANGE_DEFAULT = (
    "CRITICAL: You are given MULTIPLE uploaded ornaments/products images. "
    "Create ONE cohesive themed image that MUST include EVERY uploaded ornaments "
    "from ALL reference images in a single composition. Count the uploaded ornaments "
    "images and place that same number of distinct ornaments in the output. "
    "Never output only the first ornament. Never drop, hide, or skip any uploaded ornaments. "
    "{final_prompt}"
)

MULTI_PRODUCT_BACKGROUND_CHANGE_RULES = """MULTI-PRODUCT THEMED IMAGE RULES (MANDATORY):

1. USE ALL UPLOADED ORNAMENTS (HIGHEST PRIORITY — NON-NEGOTIABLE):
   - Every uploaded ornaments/products image MUST appear in the final image
   - If N ornament images were uploaded, the output MUST contain all N ornaments
   - Do NOT use only the first ornament; do NOT prefer one ornament over others
   - Do NOT omit, crop out, hide behind another item, or leave any uploaded ornaments incomplete
   - Do NOT merge multiple ornaments into one redesigned piece
   - Do NOT invent extra ornaments that were not uploaded
   - Before finishing, mentally verify each uploaded ornament is clearly present

2. EXACT PRESERVATION (MANDATORY):
   - Preserve EACH ornaments EXACTLY identical to its own uploaded reference image
   - Keep design, shape, proportions, stones, metal finish, textures, and fine details unchanged
   - Do NOT redesign, restyle, recolor, or replace any ornament

3. PLACEMENT AND ORIENTATION (MANDATORY — REFERENCE IMAGE ONLY):
   - Ornament scene placement MUST come ONLY from the reference-image placement analysis
   - Match position in frame, orientation, facing direction, tilt, and how pieces sit/hang/rest from the reference
   - Uploaded product/ornament images define design identity ONLY — NEVER use them for scene placement, orientation, or facing direction
   - Do NOT invent a different placement than the reference analysis describes
   - Do NOT copy how the uploaded product photo was cropped, angled, or laid out

4. NO HUMANS / NO MODELS (MANDATORY — NON-NEGOTIABLE):
   - Do NOT include any human, person, model, face, body, hands, fingers, neck, or skin
   - Product-only themed photography — ornaments and scene/background only
   - If a human or model appears, remove them completely

5. COMPOSITION (MANDATORY):
   - Arrange ALL ornaments together as a coordinated set in one cohesive scene
   - Every ornament must be clearly visible, fully recognizable, and not overlapping into invisibility
   - Do NOT let a single ornament dominate 50-70% of the frame alone
   - Balance the layout so every uploaded ornament fits fully in frame

6. BACKGROUND ONLY:
   - Create/replace the background and atmosphere around the full ornament set
   - Background must complement all ornaments without competing with them
   - Professional product photography quality suitable for marketing"""

THEMED_NO_HUMAN_RULE = (
    "STRICT NO-HUMAN / NO-MODEL RULE (MANDATORY — NON-NEGOTIABLE): "
    "This is a PRODUCT-ONLY themed image. Do NOT include any human, person, fashion model, "
    "face, body, hands, fingers, neck, skin, arms, or wearable-on-body presentation. "
    "Never add a model. If any human or model is present in a base/reference/generated image, "
    "REMOVE them completely from the output. Show only the ornament(s) and the scene/background."
)

THEMED_ORNAMENT_PLACEMENT_RULE = (
    "ORNAMENT PLACEMENT RULE (MANDATORY — REFERENCE ONLY): "
    "Scene placement of ornament(s) must come ONLY from the reference-image placement analysis. "
    "Follow the reference for position in frame, how the piece sits/hangs/rests, orientation, "
    "facing direction, tilt, scale in the scene, and surface support. "
    "Uploaded product/ornament image(s) define ONLY exact design identity (look/details). "
    "NEVER take placement, orientation, angle, or facing direction from the uploaded product photos."
)

THEMED_REFERENCE_PLACEMENT_INSTRUCTION = (
    "REFERENCE PLACEMENT LOCK (MANDATORY): The reference analysis describes how ornament(s) "
    "are placed in the reference image. Place the user's uploaded ornament(s) using ONLY that "
    "reference placement: same position style, orientation, direction, and presentation. "
    "Copy placement ONLY — never copy the reference jewelry design. "
    "Never use uploaded product-photo orientation/placement."
)

THEMED_NO_REFERENCE_PLACEMENT_FALLBACK = (
    "No theme reference image/placement analysis was provided. Invent a suitable professional "
    "themed product-photography scene for these ornament(s): complementary background, surfaces, "
    "lighting, atmosphere, and tasteful non-jewelry props that highlight the jewelry. "
    "Do NOT use a plain white or solid studio-only background. "
    "Do NOT copy placement, orientation, crop, or facing direction from the uploaded "
    "product/ornament photos — those images are design identity only."
)

THEMED_AUTO_SCENE_DEFAULT = (
    "Create a cohesive themed product photograph with a suitable complementary background "
    "and tasteful props that match the ornament style, metal, and stones. "
    "Use professional lighting, depth, and atmosphere. "
    "Do NOT use a plain white or flat solid-color studio background."
)

USER_PROMPT_PRIORITY_PREFIX = (
    "USER PROMPT (HIGHEST PRIORITY — MANDATORY TO FOLLOW EXACTLY): "
)

USER_PROMPT_PRIORITY_SUFFIX = (
    " This user prompt is an EXTRA instruction on top of the system prompt. "
    "When it conflicts with creative/styling guidance, follow the user prompt. "
    "Hard locks still apply: preserve exact ornament design identity, "
    "and obey no-human rules for themed product-only images."
)


def format_priority_user_prompt(prompt: str) -> str:
    """Extra priority block for a user-entered prompt; system prompts stay unchanged."""
    text = (prompt or "").strip()
    if not text:
        return ""
    return f"{USER_PROMPT_PRIORITY_PREFIX}{text}{USER_PROMPT_PRIORITY_SUFFIX}"


REGENERATION_USER_PROMPT_PRIORITY = (
    "REGENERATION USER PROMPT (HIGHEST PRIORITY — MANDATORY TO FOLLOW EXACTLY): "
)


def format_priority_regeneration_prompt(prompt: str) -> str:
    """Extra priority block for regenerate; system regen locks stay unchanged."""
    text = (prompt or "").strip()
    if not text:
        return (
            "REGENERATION USER PROMPT: Make no creative changes; preserve the base image."
        )
    return (
        f"{REGENERATION_USER_PROMPT_PRIORITY}{text} "
        "This is an EXTRA instruction on top of the regeneration system locks. "
        "Apply this requested change. Keep everything else from the base generated image "
        "unchanged unless this prompt explicitly asks to change it."
    )


def append_priority_user_prompt(system_prompt: str, prompt: str) -> str:
    """Keep system prompt as-is; append user prompt as an extra priority block."""
    priority = format_priority_user_prompt(prompt)
    base = (system_prompt or "").strip()
    if not priority:
        return base
    if not base:
        return priority
    return f"{base} {priority}".strip()


REFERENCE_PRIORITY_SUFFIX = (
    " These reference instructions are EXTRA on top of the system prompt. "
    "When they conflict with generic creative or clothing examples, follow the reference."
)


def format_priority_reference(*, analysis: str = "", dress: str = "") -> str:
    """Extra priority block for reference analysis/dress; omitted when both empty."""
    parts = []
    analysis_text = (analysis or "").strip()
    dress_text = (dress or "").strip()
    if analysis_text:
        parts.append(
            "REFERENCE STYLE/POSE (HIGHEST PRIORITY — MANDATORY TO FOLLOW EXACTLY): "
            f"{analysis_text}"
        )
    if dress_text:
        parts.append(
            "REFERENCE DRESS/ATTIRE (HIGHEST PRIORITY — MANDATORY TO FOLLOW EXACTLY): "
            f"{dress_text} Follow this attire exactly; do not replace it with unrelated clothing."
        )
    if not parts:
        return ""
    return f"{' '.join(parts)}{REFERENCE_PRIORITY_SUFFIX}"


def append_priority_reference(
    system_prompt: str,
    *,
    analysis: str = "",
    dress: str = "",
) -> str:
    """Keep system prompt as-is; append reference extras only when present."""
    priority = format_priority_reference(analysis=analysis, dress=dress)
    base = (system_prompt or "").strip()
    if not priority:
        return base
    if not base:
        return priority
    return f"{base} {priority}".strip()


_SAREE_ATTIRE_MARKERS = ("saree", "sari", "blouse")
_OTHER_ATTIRE_MARKERS = (
    "gown",
    "suit",
    "blazer",
    "western",
    "cocktail",
    "shirt",
    "jeans",
    "lehenga",
    "anarkali",
    "kurta",
    "indo-western",
    "indo western",
)
_SAREE_RELEVANT_ORNAMENT_MARKERS = (
    "necklace",
    "pendant",
    "haar",
    "haram",
    "mangalsutra",
    "mangal sutra",
    "choker",
    "neckpiece",
    "neck piece",
    "temple",
    "long chain",
    "mala",
    "set",
)


def is_saree_blouse_relevant(
    *,
    ornament_type: str = "",
    ornament_types=None,
    dress: str = "",
    prompt: str = "",
) -> bool:
    """
    Blouse+saree attire hint is only for relevant ornament/attire context.
    If dress/prompt already specifies another outfit, do not force saree+blouse.
    """
    attire_text = f"{dress or ''} {prompt or ''}".lower()
    if any(marker in attire_text for marker in _SAREE_ATTIRE_MARKERS):
        return True
    if any(marker in attire_text for marker in _OTHER_ATTIRE_MARKERS):
        return False

    types = []
    if ornament_type:
        types.append(str(ornament_type))
    if ornament_types:
        types.extend(str(t) for t in ornament_types if t)
    ornament_text = " ".join(types).lower()
    return any(marker in ornament_text for marker in _SAREE_RELEVANT_ORNAMENT_MARKERS)


REGENERATION_THEMED_INSTRUCTION = (
    "THEMED IMAGE REGENERATION LOCK: Keep this as a PRODUCT-ONLY themed image. "
    "Preserve the ornaments EXACTLY and keep the background/theme unless the user "
    "explicitly requests a change. REMOVE any human, person, model, face, body, or hands "
    "if present. NEVER add a model or human. Apply ONLY the user's requested change."
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
    "CHANGE RULE (MANDATORY): The regeneration user prompt has HIGHEST PRIORITY. "
    "Apply that requested change. Do NOT change anything else. Especially do NOT change "
    "the dress/outfit, colors of clothing, pose, model appearance, background, lighting, "
    "or composition unless the user explicitly requests that exact change. If the request "
    "does not mention dress or attire, the dress/attire must remain identical to the base "
    "generated image."
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
    ornament_urls = getattr(root, "uploaded_ornament_urls", None) or []

    if image_type == "campaign_shot_advanced":
        if ornament_urls:
            return list(ornament_urls)
        if getattr(root, "uploaded_image_url", None):
            return [root.uploaded_image_url]
        return []

    # Multi-product themed images (background_change) store every original here
    if image_type == "background_change" and ornament_urls:
        return list(ornament_urls)

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


def build_regeneration_image_instructions(
    *,
    ornament_count=1,
    has_model_image=False,
    image_type="",
):
    """Prompt instructions: lock base image + ornament; apply only user change."""
    if image_type == "background_change":
        if ornament_count > 1:
            original_instruction = REGENERATION_ORIGINAL_ORNAMENTS_INSTRUCTION
        else:
            original_instruction = REGENERATION_ORIGINAL_ORNAMENT_INSTRUCTION
        return (
            f"{REGENERATION_THEMED_INSTRUCTION} "
            f"{original_instruction} "
            f"{THEMED_NO_HUMAN_RULE} "
            f"{THEMED_ORNAMENT_PLACEMENT_RULE} "
            f"{REGENERATION_APPLY_MODIFICATIONS_INSTRUCTION}"
        )

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
        "Only vary composition, camera angle, placement, or subtle styling details. "
        "Do NOT introduce any human, person, or model. "
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
