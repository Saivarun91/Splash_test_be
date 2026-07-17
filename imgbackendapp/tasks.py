"""
Celery tasks for image generation in imgbackendapp.
These tasks handle asynchronous image generation using Gemini API.
"""
import os
import base64
import traceback
import time
import logging
from io import BytesIO
from django.conf import settings
from django.core.files.base import ContentFile
from celery import shared_task
from PIL import Image
import numpy as np
import cv2
import cloudinary.uploader
from .mongo_models import OrnamentMongo
from .models import Ornament
from bson import ObjectId
from common.error_reporter import report_handled_exception
from common.user_friendly_errors import get_user_friendly_message
from .generation_utils import (
    build_variation_instruction,
    build_regeneration_image_instructions,
    load_image_bytes_from_source,
    REFERENCE_DESCRIPTION_NO_ORNAMENT_RULE,
    REFERENCE_DESCRIPTION_USAGE_INSTRUCTION,
    resolve_original_ornament_sources,
    resolve_regeneration_dimension,
)
from .image_provider import generate_image_bytes, normalize_model_tier
from .file_utils import path_stem, resolve_media_path, to_media_db_path, write_bytes_to_unique_path
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# Check for Gemini SDK
try:
    from imgbackend.ai_utils import genai, types
    has_genai = True
except ImportError:
    has_genai = False


@shared_task(bind=True, max_retries=3)
def generate_white_background_task(
    self,
    uploaded_image_path,
    user_id,
    bg_color,
    extra_prompt,
    dimension,
):
    """
    Celery task to generate white background image using MongoDB workflow.
    """

    try:
        # Read uploaded image
        with open(uploaded_image_path, "rb") as f:
            img_bytes = f.read()

        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Build prompt
        from probackendapp.prompt_initializer import get_prompt_from_db

        extra_prompt_text = f" {extra_prompt}" if extra_prompt else ""
        dimension_text = (
            f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)."
            if dimension else ""
        )

        default_prompt = (
            f"Remove the background from this ornament image and replace it with a plain "
            f"{bg_color} background.{extra_prompt_text}{dimension_text}"
        )

        text_prompt = get_prompt_from_db(
            "images_white_background",
            default_prompt,
            bg_color=bg_color,
            extra_prompt=extra_prompt_text,
        )

        if dimension and dimension not in text_prompt:
            text_prompt += (
                f" Generate the image in {dimension} aspect ratio (width:height)."
            )

        generated_bytes = None

        # ---------------- Gemini ----------------
        if has_genai:
            if not (
                getattr(settings, "GEMINI_API_KEY", "")
                or getattr(settings, "GOOGLE_API_KEY", "")
            ):
                raise Exception("AI not configured")

            client = genai.Client()
            # White-background only: always use Gemini 3.1 Flash Image.
            # All other image flows keep the shared CreditSettings / IMAGE_MODEL_NAME model.
            model_name = "gemini-3.1-flash-image"

            contents = [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": img_b64,
                            }
                        },
                        {"text": text_prompt},
                    ]
                }
            ]

            supported_ratios = {
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
            }

            aspect = (dimension or "1:1").strip()

            if aspect not in supported_ratios:
                aspect = "1:1"

            config = types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    image_size="4K",
                    aspect_ratio=aspect,
                ),
            )

            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )

            for candidate in getattr(resp, "candidates", []):
                content = getattr(candidate, "content", None)

                if not content:
                    continue

                for part in getattr(content, "parts", []):
                    if getattr(part, "inline_data", None):
                        data = part.inline_data.data
                        generated_bytes = (
                            data
                            if isinstance(data, bytes)
                            else base64.b64decode(data)
                        )
                        break

                if generated_bytes:
                    break

        # ---------------- OpenCV fallback ----------------
        if not generated_bytes:

            original = Image.open(uploaded_image_path).convert("RGB")

            img_array = np.array(original)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)

            _, thresh = cv2.threshold(
                blur,
                240,
                255,
                cv2.THRESH_BINARY_INV,
            )

            kernel = np.ones((3, 3), np.uint8)

            thresh = cv2.morphologyEx(
                thresh,
                cv2.MORPH_CLOSE,
                kernel,
                iterations=2,
            )

            contours, _ = cv2.findContours(
                thresh,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )

            if not contours:
                raise Exception("Could not extract ornament.")

            largest = max(contours, key=cv2.contourArea)

            mask = np.zeros_like(gray)

            cv2.drawContours(mask, [largest], -1, 255, -1)

            mask = cv2.GaussianBlur(mask, (5, 5), 0)

            rgba = np.dstack((img_array, mask))

            transparent = Image.fromarray(rgba, "RGBA")

            bg = Image.new("RGB", original.size, bg_color)

            bg.paste(transparent, mask=transparent.split()[3])

            buf = BytesIO()

            bg.save(buf, format="JPEG", quality=95)

            generated_bytes = buf.getvalue()

        # ---------------- Upload original ----------------

        original_stem = path_stem(uploaded_image_path)

        upload_orig = cloudinary.uploader.upload(
            BytesIO(img_bytes),
            folder="ornaments",
            public_id=f"ornament_original_{original_stem}",
            overwrite=True,
        )

        uploaded_image_url = upload_orig["secure_url"]

        # ---------------- Save generated locally ----------------

        generated_dir = os.path.join(settings.MEDIA_ROOT, "generated")

        os.makedirs(generated_dir, exist_ok=True)

        filename = f"{int(time.time()*1000)}.jpg"

        local_generated_path = os.path.join(generated_dir, filename)

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        generated_db_path = to_media_db_path(local_generated_path)
        generated_image_url = generated_db_path

        # ---------------- MongoDB ----------------

        ornament_doc = OrnamentMongo(
            prompt=text_prompt,
            type="white_background",
            user_id=user_id,
            uploaded_image_url=uploaded_image_url,
            generated_image_url=generated_image_url,
            uploaded_image_path=to_media_db_path(uploaded_image_path),
            generated_image_path=to_media_db_path(local_generated_path),
            original_prompt=text_prompt,
            dimension=dimension or "1:1",
        )

        ornament_doc.save()

        return {
            "success": True,
            "uploaded_image_url": uploaded_image_url,
            "generated_image_url": generated_image_url,
            "mongo_id": str(ornament_doc.id),
            "prompt": text_prompt,
            "type": "white_background",
            "local": to_media_db_path(local_generated_path),
        }

    except Exception as e:
        traceback.print_exc()

        report_handled_exception(
            e,
            request=self.request,
            context={"user_id": user_id},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=e,
                countdown=60 * (self.request.retries + 1),
            )

        return {
            "success": False,
            "error": str(e),
        }

@shared_task(bind=True, max_retries=3)
def change_background_task(
    self,
    uploaded_image_paths,
    user_id,
    bg_color,
    prompt,
    dimension,
    reference_analysis="",
    variation_index=0,
    total_variations=1,
    model_tier="regular",
    ):
    """
    Celery task to change background of one or more product images.

    Args:
        uploaded_image_paths: List of local paths to uploaded product images
        user_id: User ID string
        bg_color: Background color (if no reference analysis)
        prompt: User prompt
        dimension: Aspect ratio dimension
        reference_analysis: Optimized text description from reference image analyzer
    """
    local_generated_path = None
    try:
        if isinstance(uploaded_image_paths, str):
            uploaded_image_paths = [uploaded_image_paths]

        uploaded_image_paths = [
            resolve_media_path(p)
            for p in (uploaded_image_paths or [])
            if p and os.path.exists(resolve_media_path(p))
        ]
        if not uploaded_image_paths:
            raise FileNotFoundError("No valid uploaded product image paths provided.")

        product_b64_list = []
        for idx, image_path in enumerate(uploaded_image_paths):
            with open(image_path, "rb") as f:
                ornament_bytes = f.read()
            ornament_img = Image.open(BytesIO(ornament_bytes)).convert("RGB")
            buf_ornament = BytesIO()
            ornament_img.save(buf_ornament, format="JPEG")
            product_b64_list.append(base64.b64encode(buf_ornament.getvalue()).decode("utf-8"))
            buf_ornament.close()

        from probackendapp.prompt_initializer import get_prompt_from_db
        user_prompt = prompt.strip() if prompt else ""
        has_reference_analysis = bool(reference_analysis and reference_analysis.strip())
        if has_reference_analysis:
            user_prompt = f"{user_prompt} {reference_analysis.strip()}".strip()

        if has_reference_analysis:
            bg_prompt = get_prompt_from_db(
                "images_background_change_with_image",
                (
                    "Replace the background using the following scene description derived "
                    "from a reference image. "
                    f"{REFERENCE_DESCRIPTION_NO_ORNAMENT_RULE}"
                ),
            )
            final_prompt = (
                f"{user_prompt} {bg_prompt} {REFERENCE_DESCRIPTION_USAGE_INSTRUCTION} "
                f"{REFERENCE_DESCRIPTION_NO_ORNAMENT_RULE}".strip()
            )
        elif bg_color:
            color_prompt = get_prompt_from_db(
                "images_background_change_with_color",
                f"Replace the background with a clean solid {bg_color} color.",
                bg_color=bg_color,
            )
            final_prompt = f"{user_prompt} {color_prompt}".strip()
        else:
            default_prompt = get_prompt_from_db(
                "images_background_change_default",
                "Change only the background without modifying the ornament.",
            )
            final_prompt = f"{user_prompt} {default_prompt}".strip()

        dimension_text = (
            f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)."
            if dimension
            else ""
        )
        final_prompt_with_dimension = (
            f"{final_prompt}{dimension_text}"
            f"{build_variation_instruction(variation_index, total_variations)}"
        )
        base_prompt = get_prompt_from_db(
            "images_background_change_base",
            "{final_prompt}",
            final_prompt=final_prompt_with_dimension,
        )
        if dimension and dimension not in base_prompt:
            base_prompt = (
                f"{base_prompt} Generate the image in {dimension} aspect ratio (width:height)."
            )

        contents = []
        multiple_products = len(product_b64_list) > 1
        for idx, product_b64 in enumerate(product_b64_list):
            contents.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": product_b64,
                    }
                }
            )
            if multiple_products:
                contents.append(
                    f"This is product reference image {idx + 1} of {len(product_b64_list)}. "
                    "Preserve this product accurately in the final image."
                )
            else:
                contents.append(
                    "This is the product whose background must be changed. "
                    "Preserve the product exactly; change only the background."
                )

        if multiple_products:
            contents.append(
                "Generate ONE cohesive themed image that includes ALL uploaded products together "
                "in a single composition with the new background. Do not omit any product."
            )

        if has_reference_analysis:
            contents.append(REFERENCE_DESCRIPTION_USAGE_INSTRUCTION)
            contents.append(REFERENCE_DESCRIPTION_NO_ORNAMENT_RULE)

        contents.append(base_prompt)

        reference_paths = list(uploaded_image_paths)

        logger.info(
            "change_background_task: tier=%s user=%s products=%s",
            normalize_model_tier(model_tier),
            user_id,
            len(uploaded_image_paths),
        )
        generated_bytes = generate_image_bytes(
            model_tier,
            prompt=base_prompt,
            gemini_contents=contents,
            reference_paths=reference_paths,
            dimension=dimension,
        )

        uploaded_urls = []
        for image_path in uploaded_image_paths:
            image_stem = path_stem(image_path)
            uploaded_result = cloudinary.uploader.upload(
                image_path,
                folder="ornaments_originals",
                public_id=f"ornament_original_{image_stem}",
                overwrite=True,
            )
            uploaded_urls.append(uploaded_result["secure_url"])

        primary_uploaded_path = uploaded_image_paths[0]
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        variation_suffix = f"v{variation_index + 1}" if total_variations > 1 else ""
        local_generated_path = write_bytes_to_unique_path(
            gen_dir,
            generated_bytes,
            "generated.jpg",
            suffix=variation_suffix,
        )
        generated_db_path = to_media_db_path(local_generated_path)
        generated_url = generated_db_path

        ornament_doc_kwargs = {
            "prompt": final_prompt,
            "generated_image_url": generated_url,
            "generated_image_path": to_media_db_path(local_generated_path),
            "type": "background_change",
            "user_id": user_id,
            "original_prompt": prompt,
            "model_tier": normalize_model_tier(model_tier),
            "dimension": dimension or "1:1",
        }
        if has_reference_analysis:
            ornament_doc_kwargs["reference_analysis"] = reference_analysis.strip()
        if len(uploaded_urls) > 1:
            ornament_doc_kwargs["uploaded_ornament_urls"] = uploaded_urls
            ornament_doc_kwargs["uploaded_image_path"] = "Multiple products"
            ornament_doc_kwargs["uploaded_image_url"] = uploaded_urls[0]
        else:
            ornament_doc_kwargs["uploaded_image_url"] = uploaded_urls[0]
            ornament_doc_kwargs["uploaded_image_path"] = to_media_db_path(primary_uploaded_path)

        ornament_doc = OrnamentMongo(**ornament_doc_kwargs)
        ornament_doc.save()

        logger.info(
            "change_background_task: success user=%s generated_url=%s products=%s",
            user_id,
            generated_url,
            len(uploaded_image_paths),
        )
        return {
            "success": True,
            "message": "Background changed successfully",
            "uploaded_image_url": uploaded_urls[0],
            "uploaded_ornament_urls": uploaded_urls if len(uploaded_urls) > 1 else None,
            "generated_image_url": generated_url,
            "prompt": prompt,
            "mongo_id": str(ornament_doc.id),
            "type": "background_change",
            "local": to_media_db_path(local_generated_path),
        }

    except Exception as e:
        logger.exception("change_background_task failed for user=%s", user_id)
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        if local_generated_path and os.path.exists(local_generated_path):
            try:
                os.remove(local_generated_path)
            except Exception:
                logger.warning("Failed cleaning temp file: %s", local_generated_path)
        return {"success": False, "error": str(e)}


@shared_task(bind=True, max_retries=3)
def generate_model_with_ornament_task(
    self,
    ornament_image_path,
    user_id,
    prompt,
    measurements,
    ornament_type,
    ornament_measurements,
    dimension,
    reference_analysis="",
    variation_index=0,
    total_variations=1,
    model_tier="regular",
):
    """
    Celery task to generate model with ornament.
    """
    try:
        # Read images
        ornament_absolute_path = resolve_media_path(ornament_image_path)
        with open(ornament_absolute_path, "rb") as f:
            ornament_bytes = f.read()
        ornament_b64 = base64.b64encode(ornament_bytes).decode("utf-8")

        has_reference_analysis = bool(reference_analysis and reference_analysis.strip())

        if normalize_model_tier(model_tier) == "regular" and not (
            getattr(settings, "GEMINI_API_KEY", "") or getattr(settings, "GOOGLE_API_KEY", "")
        ):
            raise Exception("GEMINI/GOOGLE API key not configured")

        contents = [
            {"inline_data": {"mime_type": "image/jpeg", "data": ornament_b64}},
        ]

        # Parse ornament measurements
        import json
        try:
            ornament_measurements_dict = json.loads(
                ornament_measurements) if ornament_measurements else {}
        except:
            ornament_measurements_dict = {}

        # Build ornament description
        ornament_description = ""
        if ornament_type:
            ornament_description += f"This is a {ornament_type}. "
        if ornament_measurements_dict:
            measurements_text = ", ".join(
                [f"{key}: {value}" for key, value in ornament_measurements_dict.items() if value])
            if measurements_text:
                ornament_description += f"Specific measurements: {measurements_text}. "

        # Get prompt from database
        from probackendapp.prompt_initializer import get_prompt_from_db
        measurements_text = f"measurements: {measurements}. " if measurements else ""
        prompt_text = f"\nmandatory consideration details: {prompt}" if prompt else ""
        pose_ref_text = ""
        if has_reference_analysis:
            pose_ref_text = (
                f"Follow this pose and styling direction: {reference_analysis.strip()}. "
            )
        default_prompt = (
            "Generate a close-up, high-fashion portrait of an elegant Indian woman "
            "wearing this 100% real accurate uploaded ornament. Focus tightly on the neckline and jewelry area according to the ornament. "
            "Ensure the jewelry fits naturally and realistically on the model. "
            "Lighting should be soft and natural, highlighting the sparkle of the jewelry and the model's features. "
            "Use a shallow depth of field with a softly blurred background that hints at an elegant setting. "
            "Do not include any watermark, text, or unnatural effects. "
            f"{ornament_description}"
            f"{measurements_text}Make sure to follow the measurements strictly."
            f"{prompt_text}"
        )
        user_prompt = get_prompt_from_db(
            'images_model_with_ornament',
            default_prompt,
            ornament_description=ornament_description,
            measurements_text=measurements_text,
            user_prompt=prompt,
            pose_ref_text=pose_ref_text,
        )
        if has_reference_analysis:
            user_prompt = f"{user_prompt} {reference_analysis.strip()}".strip()
        dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
        if dimension and dimension not in user_prompt:
            user_prompt = f"{user_prompt}{dimension_text}"
        user_prompt = (
            f"{user_prompt}{build_variation_instruction(variation_index, total_variations)}"
        )

        contents.append({"text": user_prompt})

        reference_paths = [ornament_absolute_path]

        generated_bytes = generate_image_bytes(
            model_tier,
            prompt=user_prompt,
            gemini_contents=contents,
            reference_paths=reference_paths,
            dimension=dimension,
        )

        # Upload ornament to Cloudinary
        ornament_stem = path_stem(ornament_absolute_path)
        uploaded_result = cloudinary.uploader.upload(
            ornament_absolute_path,
            folder="ornaments_originals",
            public_id=f"ornament_original_{ornament_stem}",
            overwrite=True
        )
        uploaded_url = uploaded_result["secure_url"]

        # Save generated image locally
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        variation_suffix = f"v{variation_index + 1}" if total_variations > 1 else ""
        local_generated_path = write_bytes_to_unique_path(
            gen_dir,
            generated_bytes,
            "generated.jpg",
            suffix=variation_suffix,
        )
        generated_db_path = to_media_db_path(local_generated_path)
        generated_url = generated_db_path

        # Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=user_prompt,
            uploaded_image_url=uploaded_url,
            generated_image_url=generated_url,
            uploaded_image_path=to_media_db_path(ornament_absolute_path),
            generated_image_path=generated_db_path,
            type="model_with_ornament",
            user_id=user_id,
            original_prompt=prompt,
            measurements=measurements,
            dimension=dimension or "1:1",
            model_tier=normalize_model_tier(model_tier),
            reference_analysis=reference_analysis.strip() if has_reference_analysis else "",
        )
        ornament_doc.save()
        # print("local_generated_path =", repr(local_generated_path))
        # print("length of local_generated_path =", len(local_generated_path))

        return {
            "status": "success",
            "message": "Generated AI close-up model wearing ornament successfully.",
            "prompt": prompt,
            "measurements": measurements,
            "uploaded_image_url": uploaded_url,
            "generated_image_url": generated_url,
            "mongo_id": str(ornament_doc.id),
            "type": "model_with_ornament",
            "local": to_media_db_path(local_generated_path),
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "status": "error",
            "message": str(e),
            "user_friendly_message": get_user_friendly_message(e),
        }


@shared_task(bind=True, max_retries=3)
def generate_real_model_with_ornament_task(
    self,
    model_image_path,
    ornament_image_path,
    user_id,
    prompt,
    measurements,
    ornament_type,
    ornament_measurements,
    dimension,
    reference_analysis="",
    variation_index=0,
    total_variations=1,
    model_tier="regular",
):
    """
    Celery task to generate real model with ornament.
    """
    try:
        # Read images
        model_absolute_path = resolve_media_path(model_image_path)
        ornament_absolute_path = resolve_media_path(ornament_image_path)
        with open(model_absolute_path, "rb") as f:
            model_bytes = f.read()
        model_b64 = base64.b64encode(model_bytes).decode("utf-8")
        
        with open(ornament_absolute_path, "rb") as f:
            ornament_bytes = f.read()
        ornament_b64 = base64.b64encode(ornament_bytes).decode("utf-8")

        has_reference_analysis = bool(reference_analysis and reference_analysis.strip())

        if normalize_model_tier(model_tier) == "regular" and not (
            getattr(settings, "GEMINI_API_KEY", "") or getattr(settings, "GOOGLE_API_KEY", "")
        ):
            raise Exception("AI not configured")

        contents = [
            {"inline_data": {"mime_type": "image/jpeg", "data": ornament_b64}},
            {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}},
        ]

        # Parse ornament measurements
        import json
        try:
            ornament_measurements_dict = json.loads(
                ornament_measurements) if ornament_measurements else {}
        except:
            ornament_measurements_dict = {}

        # Build ornament description
        ornament_description = ""
        if ornament_type:
            ornament_description += f"This is a {ornament_type}. "
        if ornament_measurements_dict:
            measurements_text = ", ".join(
                [f"{key}: {value}" for key, value in ornament_measurements_dict.items() if value])
            if measurements_text:
                ornament_description += f"Specific measurements: {measurements_text}. "

        # Get prompt from database
        from probackendapp.prompt_initializer import get_prompt_from_db
        measurements_text = f"Additional measurements: {measurements}. " if measurements else ""
        prompt_text = f" Additional user instructions: {prompt}" if prompt else ""
        pose_ref_text = ""
        if has_reference_analysis:
            pose_ref_text = (
                f"Follow this pose and styling direction: {reference_analysis.strip()}. "
            )
        default_prompt = (
            "Generate a realistic, high-quality close-up image of the uploaded model wearing "
            "the exact uploaded ornament. Keep the model's face fully intact and recognizable. "
            "Ensure the ornament fits naturally and realistically on the model. "
            "Generate a background suitable for both the model and the ornament. "
            "Lighting should be soft, natural, and elegant. "
            "Focus tightly on the jewelry area. "
            f"{pose_ref_text}"
            f"{ornament_description}"
            f"{measurements_text}"
            f"{prompt_text}"
        )
        user_prompt = get_prompt_from_db(
            'images_real_model_with_ornament',
            default_prompt,
            ornament_description=ornament_description,
            measurements_text=measurements_text,
            user_prompt=prompt,
            pose_ref_text=pose_ref_text,
        )
        if prompt:
            user_prompt = f"{user_prompt} {prompt}"
        if has_reference_analysis:
            user_prompt = f"{user_prompt} {reference_analysis.strip()}".strip()

        dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
        if dimension and dimension not in user_prompt:
            user_prompt = f"{user_prompt}{dimension_text}"
        user_prompt = (
            f"{user_prompt}{build_variation_instruction(variation_index, total_variations)}"
        )

        contents.append({"text": user_prompt})

        reference_paths = [model_absolute_path, ornament_absolute_path]

        generated_bytes = generate_image_bytes(
            model_tier,
            prompt=user_prompt,
            gemini_contents=contents,
            reference_paths=reference_paths,
            dimension=dimension,
        )

        # Upload images to Cloudinary
        model_stem = path_stem(model_absolute_path)
        ornament_stem = path_stem(ornament_absolute_path)
        model_upload = cloudinary.uploader.upload(
            model_absolute_path,
            folder="models_originals",
            public_id=f"model_original_{model_stem}",
            overwrite=True
        )
        ornament_upload = cloudinary.uploader.upload(
            ornament_absolute_path,
            folder="ornaments_originals",
            public_id=f"ornament_original_{ornament_stem}",
            overwrite=True
        )

        model_url = model_upload["secure_url"]
        ornament_url = ornament_upload["secure_url"]

        # Save generated image locally
        generated_dir = os.path.join(
            settings.MEDIA_ROOT, "generated_models")
        variation_suffix = f"v{variation_index + 1}" if total_variations > 1 else ""
        local_generated_path = write_bytes_to_unique_path(
            generated_dir,
            generated_bytes,
            "generated.jpg",
            suffix=variation_suffix,
        )
        generated_db_path = to_media_db_path(local_generated_path)
        generated_url = generated_db_path

        # Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=user_prompt,
            model_image_url=model_url,
            uploaded_image_url=ornament_url,
            generated_image_url=generated_url,
            uploaded_image_path=to_media_db_path(model_absolute_path),
            generated_image_path=generated_db_path,
            type="real_model_with_ornament",
            user_id=user_id,
            original_prompt=prompt,
            measurements=measurements,
            dimension=dimension or "1:1",
            model_tier=normalize_model_tier(model_tier),
            reference_analysis=reference_analysis.strip() if has_reference_analysis else "",
        )
        ornament_doc.save()

        return {
            "status": "success",
            "message": "Generated AI image of the model wearing ornament successfully.",
            "prompt": prompt,
            "measurements": measurements,
            "model_image_url": model_url,
            "ornament_image_url": ornament_url,
            "generated_image_url": generated_url,
            "mongo_id": str(ornament_doc.id),
            "type": "real_model_with_ornament",
            "local": to_media_db_path(local_generated_path),
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "status": "error",
            "message": str(e),
            "user_friendly_message": get_user_friendly_message(e),
        }


@shared_task(bind=True, max_retries=3)
def generate_campaign_shot_advanced_task(
    self,
    user_id,
    model_type,
    model_image_path,
    ornament_image_paths,
    ornament_names,
    ornament_types,
    prompt,
    dimension,
    reference_analysis="",
    ornament_measurements='[]',
    variation_index=0,
    total_variations=1,
    model_tier="regular",
):
    """
    Celery task to generate campaign shot.
    """
    try:
        # Upload ornaments to Cloudinary & encode
        ornament_urls = []
        ornament_b64_list = []

        # Parse optional per-ornament measurements (JSON array of dicts)
        import json
        try:
            ornament_measurements_list = json.loads(
                ornament_measurements) if ornament_measurements else []
        except Exception:
            ornament_measurements_list = []

        for idx, ornament_path in enumerate(ornament_image_paths):
            ornament_absolute_path = resolve_media_path(ornament_path)
            with open(ornament_absolute_path, "rb") as f:
                ornament_bytes = f.read()
            
            # Upload
            ornament_stem = path_stem(ornament_absolute_path)
            result = cloudinary.uploader.upload(
                ornament_absolute_path,
                folder="ornaments",
                public_id=f"ornament_{ornament_stem}",
                overwrite=True,
            )
            ornament_urls.append(result['secure_url'])

            # Encode
            ornament_name = ornament_names[idx] if idx < len(
                ornament_names) else f"Ornament {idx+1}"
            ornament_type = None
            if ornament_types and idx < len(ornament_types):
                ornament_type = ornament_types[idx] or None

            # Attach measurements for this ornament (if any)
            per_ornament_measurements = {}
            if (
                ornament_measurements_list
                and idx < len(ornament_measurements_list)
                and isinstance(ornament_measurements_list[idx], dict)
            ):
                per_ornament_measurements = ornament_measurements_list[idx]

            ornament_b64_list.append({
                "name": ornament_name,
                "type": ornament_type,
                "measurements": per_ornament_measurements,
                "data": base64.b64encode(ornament_bytes).decode('utf-8')
            })

        # Model upload & encoding
        model_url = None
        model_b64 = None
        model_absolute_path = resolve_media_path(model_image_path) if model_image_path else None
        if model_absolute_path and os.path.exists(model_absolute_path):
            with open(model_absolute_path, "rb") as f:
                model_bytes = f.read()
            model_stem = path_stem(model_absolute_path)
            model_upload = cloudinary.uploader.upload(
                model_absolute_path,
                folder="models",
                public_id=f"model_{model_stem}",
                overwrite=True,
            )
            model_url = model_upload['secure_url']
            model_b64 = base64.b64encode(model_bytes).decode('utf-8')

        has_reference_analysis = bool(reference_analysis and reference_analysis.strip())
        parts = []

        # Model (optional)
        if model_b64:
            parts.append(
                {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}})
            parts.append({"text": "Reference for the real model."})

        # Ornaments
        for ornament in ornament_b64_list:
            parts.append(
                {"inline_data": {"mime_type": "image/jpeg", "data": ornament["data"]}}
            )
            type_text = f" (type: {ornament['type']})" if ornament.get("type") else ""

            measurements_text = ""
            if ornament.get("measurements"):
                entries = [
                    f"{k}: {v}"
                    for k, v in ornament["measurements"].items()
                    if v
                ]
                if entries:
                    measurements_text = f" with measurements: {', '.join(entries)}"

            parts.append(
                {
                    "text": f"Reference for ornament: {ornament['name']}{type_text}{measurements_text}"
                }
            )

        # Get prompt from database
        from probackendapp.prompt_initializer import get_prompt_from_db

        if model_type == 'real_model':
            default_prompt = (
                "Generate a realistic image of the uploaded real model wearing all the uploaded ornaments. "
                "Preserve the model's facial features and natural pose while making a small smile. "
                f"Campaign instructions: {prompt}"
            )
            user_prompt = get_prompt_from_db(
                'images_campaign_shot_real',
                default_prompt,
                user_prompt=prompt
            )
        else:
            default_prompt = (
                "Generate a high-quality campaign image of a model wearing all the uploaded ornaments. "
                "Use realistic lighting, texture, and cohesive fashion aesthetics. "
                f"Campaign instructions: {prompt}"
            )
            user_prompt = get_prompt_from_db(
                'images_campaign_shot_ai',
                default_prompt,
                user_prompt=prompt
            )
            if prompt:
                user_prompt = f"{user_prompt} {prompt}"

        if has_reference_analysis:
            user_prompt = (
                f"{user_prompt} {REFERENCE_DESCRIPTION_USAGE_INSTRUCTION} "
                f"{reference_analysis.strip()} {REFERENCE_DESCRIPTION_NO_ORNAMENT_RULE}"
            ).strip()

        dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
        if dimension and dimension not in user_prompt:
            user_prompt = f"{user_prompt}{dimension_text}"
        user_prompt = (
            f"{user_prompt}{build_variation_instruction(variation_index, total_variations)}"
        )

        parts.append({"text": user_prompt})
        contents = [{"parts": parts}]

        reference_paths = []
        if model_absolute_path and os.path.exists(model_absolute_path):
            reference_paths.append(model_absolute_path)
        reference_paths.extend(
            [
                resolve_media_path(path)
                for path in ornament_image_paths
                if path and os.path.exists(resolve_media_path(path))
            ]
        )

        generated_bytes = generate_image_bytes(
            model_tier,
            prompt=user_prompt,
            gemini_contents=contents,
            reference_paths=reference_paths,
            dimension=dimension,
        )

        # Save and upload generated image
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated", "campaign")
        variation_suffix = f"v{variation_index + 1}" if total_variations > 1 else ""
        local_generated_path = write_bytes_to_unique_path(
            gen_dir,
            generated_bytes,
            "campaign.jpg",
            suffix=variation_suffix,
        )
        generated_db_path = to_media_db_path(local_generated_path)
        generated_url = generated_db_path

        # Save record to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=prompt,
            type="campaign_shot_advanced",
            model_image_url=model_url,
            uploaded_ornament_urls=ornament_urls,
            generated_image_url=generated_url,
            uploaded_image_path="Multiple ornaments",
            generated_image_path=generated_db_path,
            user_id=user_id,
            original_prompt=prompt,
            dimension=dimension or "1:1",
            model_tier=normalize_model_tier(model_tier),
            reference_analysis=reference_analysis.strip() if has_reference_analysis else "",
        )
        ornament_doc.save()

        return {
            "status": "success",
            "message": "Campaign shot generated successfully.",
            "prompt": prompt,
            "model_type": model_type,
            "ornament_names": ornament_names,
            "uploaded_ornament_urls": ornament_urls,
            "model_image_url": model_url,
            "generated_image_url": generated_url,
            "mongo_id": str(ornament_doc.id),
            "type": "campaign_shot_advanced",
            "local": to_media_db_path(local_generated_path),
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "status": "error",
            "message": str(e)
        }


@shared_task(bind=True, max_retries=3)
def regenerate_image_task(self, image_id, user_id, new_prompt, model_tier="regular"):
    """
    Celery task to regenerate an image.
    """
    try:
        from urllib.request import urlopen
        import re

        # Validate MongoDB ObjectId format
        object_id_pattern = re.compile(r'^[0-9a-fA-F]{24}$')
        if not object_id_pattern.match(image_id):
            return {
                "success": False,
                "error": f"Invalid image_id: '{image_id}' is not a valid MongoDB ObjectId.",
                "user_friendly_message": get_user_friendly_message("Invalid image_id"),
            }

        # Fetch the previous image record from MongoDB
        try:
            prev_doc = OrnamentMongo.objects.get(id=ObjectId(image_id))
        except OrnamentMongo.DoesNotExist:
            return {
                "success": False,
                "error": "Image record not found",
                "user_friendly_message": get_user_friendly_message("Image record not found"),
            }

        # Verify that the image belongs to the user
        if prev_doc.user_id != user_id:
            return {
                "success": False,
                "error": "You don't have permission to regenerate this image",
                "user_friendly_message": get_user_friendly_message("permission to regenerate"),
            }

        # Load the previous generated image from disk (fallback to URL for legacy records)
        prev_generated_url = prev_doc.generated_image_url
        img_bytes = None
        if prev_doc.generated_image_path:
            ref_path = resolve_media_path(prev_doc.generated_image_path)
            if os.path.exists(ref_path):
                with open(ref_path, "rb") as f:
                    img_bytes = f.read()

        if img_bytes is None and prev_generated_url:
            with urlopen(prev_generated_url) as resp:
                img_bytes = resp.read()

        if not img_bytes:
            return {
                "success": False,
                "error": "Previous generated image not found",
                "user_friendly_message": get_user_friendly_message("Previous generated image not found"),
            }

        prev_img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Load the original uploaded ornament image(s) from the root generation record
        ornament_sources = resolve_original_ornament_sources(prev_doc)
        if not ornament_sources:
            return {
                "success": False,
                "error": "Original uploaded ornament image not found",
                "user_friendly_message": get_user_friendly_message("Original uploaded ornament image not found"),
            }

        ornament_images = []
        for source in ornament_sources:
            try:
                ornament_bytes = load_image_bytes_from_source(source)
            except FileNotFoundError:
                continue
            ornament_images.append({"source": source, "bytes": ornament_bytes})

        if not ornament_images:
            return {
                "success": False,
                "error": "Original uploaded ornament image not found",
                "user_friendly_message": get_user_friendly_message("Original uploaded ornament image not found"),
            }

        dimension = resolve_regeneration_dimension(prev_doc, img_bytes)
        dimension_text = (
            f"Generate the ultra high quality image in {dimension} aspect ratio (width:height)."
        )

        # Combine the original prompt with the new prompt
        original_prompt = prev_doc.original_prompt or prev_doc.prompt
        combined_prompt = f"{original_prompt}. {new_prompt}"
        measurements = getattr(prev_doc, 'measurements', None) or ''
        measurements_text = f"measurements: {measurements}." if measurements else ""
        regeneration_instructions = build_regeneration_image_instructions(
            ornament_count=len(ornament_images),
        )
        full_prompt = " ".join(
            part for part in (
                regeneration_instructions,
                combined_prompt,
                measurements_text,
                dimension_text,
            ) if part
        )

        regen_dir = os.path.join(settings.MEDIA_ROOT, "generated")
        reference_paths = []
        contents = []

        for idx, ornament_image in enumerate(ornament_images):
            ornament_b64 = base64.b64encode(ornament_image["bytes"]).decode("utf-8")
            temp_ornament_path = write_bytes_to_unique_path(
                regen_dir,
                ornament_image["bytes"],
                "regen_ornament.jpg",
                suffix=f"ornament_{image_id}_{idx}",
            )
            reference_paths.append(temp_ornament_path)
            contents.append(
                {"inline_data": {"mime_type": "image/jpeg", "data": ornament_b64}}
            )
            if len(ornament_images) > 1:
                contents.append(
                    {
                        "text": (
                            f"Original uploaded ornament reference {idx + 1} of "
                            f"{len(ornament_images)}."
                        )
                    }
                )

        temp_ref_path = write_bytes_to_unique_path(
            regen_dir, img_bytes, "regen_ref.jpg", suffix=f"ref_{image_id}"
        )
        reference_paths.append(temp_ref_path)
        contents.extend([
            {"inline_data": {"mime_type": "image/jpeg", "data": prev_img_b64}},
            {"text": full_prompt},
        ])

        generated_bytes = generate_image_bytes(
            model_tier,
            prompt=full_prompt,
            gemini_contents=contents,
            reference_paths=reference_paths,
            dimension=dimension,
        )
        local_regen_path = write_bytes_to_unique_path(
            regen_dir, generated_bytes, "regen.jpg", suffix=image_id
        )
        regen_db_path = to_media_db_path(local_regen_path)
        regenerated_url = regen_db_path

        # Create new MongoDB document for the regenerated image
        new_doc = OrnamentMongo(
            prompt=combined_prompt,
            type=prev_doc.type,
            user_id=user_id,
            parent_image_id=ObjectId(image_id),
            original_prompt=original_prompt,
            measurements=measurements,
            dimension=dimension,
            uploaded_image_url=prev_doc.uploaded_image_url,
            generated_image_url=regenerated_url,
            uploaded_image_path=prev_doc.uploaded_image_path,
            generated_image_path=regen_db_path,
            model_image_url=prev_doc.model_image_url if hasattr(
                prev_doc, 'model_image_url') else None,
            uploaded_ornament_urls=prev_doc.uploaded_ornament_urls if hasattr(
                prev_doc, 'uploaded_ornament_urls') else None,
            model_tier=normalize_model_tier(model_tier),
        )
        new_doc.save()

        # Track regeneration in history
        try:
            from probackendapp.history_utils import track_image_regeneration
            track_image_regeneration(
                user_id=user_id,
                original_image_id=image_id,
                new_image_url=regenerated_url,
                new_prompt=new_prompt,
                original_prompt=original_prompt,
                image_type=prev_doc.type,
                local_path=to_media_db_path(local_regen_path),
                metadata={
                    "uploaded_image_url": prev_doc.uploaded_image_url,
                    "model_image_url": getattr(prev_doc, 'model_image_url', None)
                }
            )
        except Exception as history_error:
            print(f"Error tracking regeneration history: {history_error}")

        return {
            "success": True,
            "message": "Image regenerated successfully",
            "mongo_id": str(new_doc.id),
            "parent_image_id": image_id,
            "generated_image_url": regenerated_url,
            "generated_image_path": regen_db_path,
            "uploaded_image_url": prev_doc.uploaded_image_url,
            "combined_prompt": combined_prompt,
            "original_prompt": original_prompt,
            "new_prompt": new_prompt,
            "type": prev_doc.type,
            "dimension": dimension,
            "local": to_media_db_path(local_regen_path),
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e),
            "user_friendly_message": get_user_friendly_message(e),
        }
