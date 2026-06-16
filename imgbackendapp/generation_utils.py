"""Shared helpers for multi-image generation batches."""


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
