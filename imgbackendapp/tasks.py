"""
Celery tasks for image generation in imgbackendapp.
These tasks handle asynchronous image generation using Gemini API.
"""
import os
import base64
import traceback
import time
from io import BytesIO
from datetime import datetime
from django.conf import settings
from django.core.files.base import ContentFile
from celery import shared_task
from CREDITS.utils import get_image_model_name
from PIL import Image
import numpy as np
import cv2
import cloudinary.uploader
from .mongo_models import OrnamentMongo
from .models import Ornament
from bson import ObjectId
from common.error_reporter import report_handled_exception
from common.user_friendly_errors import get_user_friendly_message


def _path_to_media_url(full_path):
    """Convert absolute file path under MEDIA_ROOT to relative URL (e.g. /media/generated_ornaments/x.jpg)."""
    if not full_path or not getattr(settings, "MEDIA_ROOT", None):
        return full_path
    try:
        rel = os.path.relpath(
            os.path.abspath(full_path), os.path.abspath(settings.MEDIA_ROOT)
        )
        return (settings.MEDIA_URL + rel).replace("\\", "/")
    except (ValueError, TypeError):
        return full_path


def _url_or_path_to_bytes(url_or_path):
    """Get image bytes from either a local /media/ URL/path or a remote http URL."""
    if not url_or_path:
        return None
    try:
        if url_or_path.startswith("/") and getattr(settings, "MEDIA_URL", "").rstrip("/") in url_or_path:
            # Local media URL: /media/generated_ornaments/foo.jpg -> MEDIA_ROOT/generated_ornaments/foo.jpg
            prefix = (settings.MEDIA_URL or "/media/").rstrip("/")
            rel = url_or_path[len(prefix):].lstrip("/")
            local_path = os.path.join(settings.MEDIA_ROOT, rel.replace("/", os.sep))
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    return f.read()
        if not url_or_path.startswith("http"):
            # Treat as filesystem path
            if os.path.exists(url_or_path):
                with open(url_or_path, "rb") as f:
                    return f.read()
            abs_path = os.path.join(settings.MEDIA_ROOT, url_or_path.lstrip("/").replace("/", os.sep))
            if os.path.exists(abs_path):
                with open(abs_path, "rb") as f:
                    return f.read()
        # Remote URL
        from urllib.request import urlopen
        with urlopen(url_or_path) as resp:
            return resp.read()
    except Exception:
        return None


def _upload_bytes_to_cloudinary(image_bytes, folder, public_id_prefix):
    """Upload raw image bytes to Cloudinary and return secure URL, or None on failure."""
    if not image_bytes:
        return None
    try:
        buf = BytesIO(image_bytes)
        buf.seek(0)
        unique_suffix = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        upload_result = cloudinary.uploader.upload(
            buf,
            folder=folder,
            public_id=f"{public_id_prefix}_{unique_suffix}",
            overwrite=False,
            resource_type="image",
        )
        return upload_result.get("secure_url")
    except Exception as e:
        # Don't break the task if Cloudinary is temporarily unavailable; fall back to local URLs.
        report_handled_exception(e, request=None, context={"cloudinary_upload_folder": folder})
        return None


def _finish_credit_reservation(credit_reservation_id, success, task_self=None):
    """On success: complete (deduct). On failure: release only when not retrying."""
    if not credit_reservation_id:
        return
    from CREDITS.utils import complete_reservation, release_reservation
    if success:
        complete_reservation(credit_reservation_id)
    else:
        max_retries = getattr(task_self, "max_retries", 3)
        retries = getattr(getattr(task_self, "request", None), "retries", 0)
        if retries >= max_retries:
            release_reservation(credit_reservation_id)


# Check for Gemini SDK
try:
    from google import genai
    from google.genai import types
    has_genai = True
except ImportError:
    has_genai = False


def analyze_reference_image_with_genai(image_path, context):
    """
    Analyze a reference image with Gemini (text-only) and return description text.
    context: 'themed' | 'model' | 'campaign'
    - themed: backgrounds, backdrops, mood, props
    - model: poses, style, attire
    - campaign: theme, style, mood, attire, background, props
    Returns a short paragraph suitable for inclusion in generation prompts.
    """
    if not has_genai or not getattr(settings, 'GOOGLE_API_KEY', None) or settings.GOOGLE_API_KEY == 'your_api_key_here':
        return ""
    if not image_path or not os.path.exists(image_path):
        return ""
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model = getattr(settings, 'GEMINI_ANALYZE_MODEL', 'gemini-2.0-flash')
        if context == "themed":
            instruction = (
                "Analyze this image and describe in 1-3 short sentences: "
                "the background and backdrop (setting, surfaces, colors), the mood (e.g. calm, luxury, minimal), "
                "and any visible props. Output only the description, no labels or bullet points."
            )
        elif context == "model":
            instruction = (
                "Analyze this image and describe in 1-3 short sentences: "
                "the pose and body position, the style (e.g. fashion, casual), and the attire/clothing. "
                "Output only the description, no labels or bullet points."
            )
        elif context == "campaign":
            instruction = (
                "Analyze this image and describe in 1-3 short sentences: "
                "the overall theme, visual style, mood, and attire. "
                "Output only the description, no labels or bullet points."
            )
        else:
            instruction = "Describe this image in 1-2 sentences for use as a style reference. Output only the description."
        contents = [
            {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
            {"text": instruction},
        ]
        resp = client.models.generate_content(model=model, contents=contents)
        text = (resp.candidates[0].content.parts[0].text or "").strip() if resp.candidates and resp.candidates[0].content.parts else ""
        return text
    except Exception as e:
        report_handled_exception(e, request=None, context={"analyze_reference": context})
        return ""
    


@shared_task(bind=True, max_retries=3)
def generate_white_background_task(self, ornament_id, user_id, bg_color, extra_prompt, dimension, credit_reservation_id=None):
    """
    Celery task to generate white background image.
    
    Args:
        ornament_id: Django model ID of the uploaded ornament
        user_id: User ID string
        bg_color: Background color
        extra_prompt: Additional prompt text
        dimension: Aspect ratio dimension
    """
    try:
        # Get ornament from database
        ornament = Ornament.objects.get(id=ornament_id)
        
        # Read image file
        with open(ornament.image.path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Get prompt from database
        from probackendapp.prompt_initializer import get_prompt_from_db
        extra_prompt_text = f" {extra_prompt}" if extra_prompt else ""
        dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
        default_prompt = f"Remove the background from this ornament image and replace it with a plain {bg_color} background.{extra_prompt_text}{dimension_text}"
        text_prompt = get_prompt_from_db(
            'images_white_background',
            default_prompt,
            bg_color=bg_color,
            extra_prompt=extra_prompt_text
        )
        # Add dimension to prompt if not already included
        if dimension and dimension not in text_prompt:
            text_prompt = f"{text_prompt} Generate the image in {dimension} aspect ratio (width:height)."

        generated_bytes = None

        if has_genai:
            if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == "your_api_key_here":
                raise Exception("GOOGLE_API_KEY not configured")

            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)

            contents = [
                {
                    "parts": [
                        {"inline_data": {
                            "mime_type": "image/jpeg", "data": img_b64}},
                        {"text": text_prompt}
                    ]
                }
            ]

            config = types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE]
            )

            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )

            candidates = getattr(resp, "candidates", [])
            for cand in candidates:
                content = getattr(cand, "content", [])
                for part in content.parts if hasattr(content, "parts") else []:
                    if getattr(part, "inline_data", None):
                        data = part.inline_data.data
                        generated_bytes = data if isinstance(
                            data, bytes) else base64.b64decode(data)
                        break
                if generated_bytes:
                    break

            if not generated_bytes:
                raise Exception("Gemini did not return an image. Using local fallback.")

        # Fallback
        if not generated_bytes:
            original = Image.open(ornament.image.path).convert("RGB")
            img_array = np.array(original)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(
                blur, 240, 255, cv2.THRESH_BINARY_INV)
            kernel = np.ones((3, 3), np.uint8)
            thresh = cv2.morphologyEx(
                thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
            thresh = cv2.morphologyEx(
                thresh, cv2.MORPH_OPEN, kernel, iterations=1)
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                mask = np.zeros_like(gray)
                cv2.drawContours(mask, [largest_contour], -1, 255, -1)
                mask = cv2.GaussianBlur(mask, (5, 5), 0)
                rgba_array = np.dstack((img_array, mask))
                transparent_img = Image.fromarray(rgba_array, 'RGBA')
                bg = Image.new("RGB", original.size, bg_color)
                bg.paste(transparent_img,
                         mask=transparent_img.split()[3])
                buf = BytesIO()
                bg.save(buf, format="JPEG", quality=95)
                generated_bytes = buf.getvalue()
            else:
                raise Exception(
                    "Could not extract ornament using fallback method.")

        # Save generated image locally
        filename = f"{ornament.id}_generated.jpg"
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)
        local_generated_path = os.path.join(gen_dir, filename)
        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # Upload original and generated images to Cloudinary for viewing
        uploaded_cloud_url = _upload_bytes_to_cloudinary(
            img_bytes,
            folder="imgbackend/uploaded_ornaments",
            public_id_prefix=f"ornament_{ornament.id}",
        )
        generated_cloud_url = _upload_bytes_to_cloudinary(
            generated_bytes,
            folder="imgbackend/generated_ornaments",
            public_id_prefix=f"white_background_{ornament.id}",
        )

        uploaded_image_url = uploaded_cloud_url or _path_to_media_url(ornament.image.path)
        generated_image_url = generated_cloud_url or _path_to_media_url(local_generated_path)

        # Save in MongoDB
        ornament_doc = OrnamentMongo(
            prompt=text_prompt,
            uploaded_image_url=uploaded_image_url,
            generated_image_url=generated_image_url,
            uploaded_image_path=ornament.image.path,
            generated_image_path=local_generated_path,
            type="white_background",
            user_id=user_id,
            original_prompt=text_prompt
        )
        ornament_doc.save()

        # Track image generation in history
        try:
            from probackendapp.history_utils import track_image_generation
            track_image_generation(
                user_id=user_id,
                image_type="white_background",
                image_url=generated_image_url,
                prompt=text_prompt,
                local_path=filename,
                metadata={
                    "uploaded_image_url": uploaded_image_url,
                    "background_color": bg_color,
                    "extra_prompt": extra_prompt
                }
            )
        except Exception as history_error:
            print(f"Error tracking image generation history: {history_error}")

        # Save locally in Django model
        ornament.generated_image.save(
            filename, ContentFile(generated_bytes), save=True)

        _finish_credit_reservation(credit_reservation_id, True, self)
        return {
            "success": True,
            "message": "Image generated successfully",
            "uploaded_image_url": uploaded_image_url,
            "generated_image_url": generated_image_url,
            "prompt": text_prompt,
            "ornament_id": ornament.id,
            "mongo_id": str(ornament_doc.id),
            "type": "white_background"
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        _finish_credit_reservation(credit_reservation_id, False, self)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e)
        }


@shared_task(bind=True, max_retries=3)
def generate_white_background_batch_task(
    self, ornament_id, user_id, bg_color, extra_prompt, dimension, num_images
):
    """
    Generate multiple white-background images from one ornament (same prompt, N variations).
    Returns { success, images: [ { generated_image_url, mongo_id, prompt }, ... ] }.
    """
    try:
        ornament = Ornament.objects.get(id=ornament_id)
        with open(ornament.image.path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        from probackendapp.prompt_initializer import get_prompt_from_db
        extra_prompt_text = f" {extra_prompt}" if extra_prompt else ""
        dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
        default_prompt = f"Remove the background from this ornament image and replace it with a plain {bg_color} background.{extra_prompt_text}{dimension_text}"
        text_prompt = get_prompt_from_db(
            "images_white_background",
            default_prompt,
            bg_color=bg_color,
            extra_prompt=extra_prompt_text,
        )
        if dimension and dimension not in text_prompt:
            text_prompt = f"{text_prompt} Generate the image in {dimension} aspect ratio (width:height)."

        results = []
        # Cloudinary URL (or local fallback) for the uploaded ornament image
        uploaded_cloud_url = _upload_bytes_to_cloudinary(
            img_bytes,
            folder="imgbackend/uploaded_ornaments",
            public_id_prefix=f"ornament_{ornament.id}_batch",
        )
        uploaded_image_url = uploaded_cloud_url or _path_to_media_url(ornament.image.path)

        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)

        for index in range(num_images):
            generated_bytes = None
            if has_genai and settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY != "your_api_key_here":
                client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)
                contents = [
                    {
                        "parts": [
                            {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                            {"text": text_prompt},
                        ]
                    }
                ]
                config = types.GenerateContentConfig(response_modalities=[types.Modality.IMAGE])
                resp = client.models.generate_content(
                    model=model_name, contents=contents, config=config
                )
                candidates = getattr(resp, "candidates", [])
                for cand in candidates:
                    content = getattr(cand, "content", [])
                    for part in content.parts if hasattr(content, "parts") else []:
                        if getattr(part, "inline_data", None):
                            data = part.inline_data.data
                            generated_bytes = data if isinstance(data, bytes) else base64.b64decode(data)
                            break
                    if generated_bytes:
                        break

            if not generated_bytes:
                original = Image.open(ornament.image.path).convert("RGB")
                img_array = np.array(original)
                img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                _, thresh = cv2.threshold(blur, 240, 255, cv2.THRESH_BINARY_INV)
                kernel = np.ones((3, 3), np.uint8)
                thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
                thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest_contour = max(contours, key=cv2.contourArea)
                    mask = np.zeros_like(gray)
                    cv2.drawContours(mask, [largest_contour], -1, 255, -1)
                    mask = cv2.GaussianBlur(mask, (5, 5), 0)
                    rgba_array = np.dstack((img_array, mask))
                    transparent_img = Image.fromarray(rgba_array, "RGBA")
                    bg = Image.new("RGB", original.size, bg_color)
                    bg.paste(transparent_img, mask=transparent_img.split()[3])
                    buf = BytesIO()
                    bg.save(buf, format="JPEG", quality=95)
                    generated_bytes = buf.getvalue()
                else:
                    generated_bytes = None

            if not generated_bytes:
                results.append({
                    "success": False,
                    "error": "Generation failed for this image",
                    "index": index,
                })
                continue

            filename = f"{ornament.id}_generated_batch_{index}.jpg"
            local_generated_path = os.path.join(gen_dir, filename)
            with open(local_generated_path, "wb") as f:
                f.write(generated_bytes)
            generated_cloud_url = _upload_bytes_to_cloudinary(
                generated_bytes,
                folder="imgbackend/generated_ornaments",
                public_id_prefix=f"white_background_batch_{ornament.id}_{index}",
            )
            generated_image_url = generated_cloud_url or _path_to_media_url(local_generated_path)

            ornament_doc = OrnamentMongo(
                prompt=text_prompt,
                uploaded_image_url=uploaded_image_url,
                generated_image_url=generated_image_url,
                uploaded_image_path=ornament.image.path,
                generated_image_path=local_generated_path,
                type="white_background",
                user_id=user_id,
                original_prompt=text_prompt,
            )
            ornament_doc.save()

            try:
                from probackendapp.history_utils import track_image_generation
                track_image_generation(
                    user_id=user_id,
                    image_type="white_background",
                    image_url=generated_image_url,
                    prompt=text_prompt,
                    local_path=filename,
                    metadata={
                        "uploaded_image_url": uploaded_image_url,
                        "background_color": bg_color,
                        "extra_prompt": extra_prompt,
                        "batch_index": index,
                    },
                )
            except Exception as history_error:
                print(f"Error tracking image generation history: {history_error}")

            if index == 0:
                ornament.generated_image.save(filename, ContentFile(generated_bytes), save=True)

            results.append({
                "success": True,
                "generated_image_url": generated_image_url,
                "mongo_id": str(ornament_doc.id),
                "prompt": text_prompt,
                "uploaded_image_url": uploaded_image_url,
                "index": index,
            })

        return {
            "success": True,
            "message": f"Generated {len([r for r in results if r.get('success')])} image(s)",
            "images": results,
            "type": "white_background",
        }
    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {"success": False, "error": str(e), "images": []}


@shared_task(bind=True, max_retries=3)
def change_background_task(self, uploaded_image_path, user_id, bg_color, background_image_path, prompt, dimension, batch_index=None, reference_analysis=None, credit_reservation_id=None):
    """
    Celery task to change background of an image.
    When batch_index is set, uses unique paths/ids for multi-image generation.
    """
    try:
        # Read ornament image
        with open(uploaded_image_path, "rb") as f:
            ornament_bytes = f.read()
        
        ornament_img = Image.open(uploaded_image_path).convert("RGB")
        buf_ornament = BytesIO()
        ornament_img.save(buf_ornament, format="JPEG")
        img_b64 = base64.b64encode(buf_ornament.getvalue()).decode("utf-8")

        # Handle background image
        bg_b64 = None
        if background_image_path and os.path.exists(background_image_path):
            bg_img = Image.open(background_image_path).convert("RGB")
            buf_bg = BytesIO()
            bg_img.save(buf_bg, format="JPEG")
            bg_b64 = base64.b64encode(buf_bg.getvalue()).decode("utf-8")

        # Build prompt
        from probackendapp.prompt_initializer import get_prompt_from_db
        user_prompt = prompt.strip() if prompt else ""

        if bg_b64:
            bg_prompt = get_prompt_from_db(
                'images_background_change_with_image',
                "Replace the background using the uploaded background image."
            )
            ref_analysis_text = f" Reference image analysis: {reference_analysis}." if reference_analysis else ""
            final_prompt = f"{user_prompt}{ref_analysis_text} {bg_prompt}"
        elif bg_color:
            color_prompt = get_prompt_from_db(
                'images_background_change_with_color',
                f"Replace the background with a clean solid {bg_color} color.",
                bg_color=bg_color
            )
            final_prompt = f"{user_prompt} {color_prompt}"
        else:
            default_prompt = get_prompt_from_db(
                'images_background_change_default',
                "Change only the background without modifying the ornament."
            )
            final_prompt = f"{user_prompt} {default_prompt}"

        dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
        final_prompt_with_dimension = f"{final_prompt}{dimension_text}"
        
        base_prompt = get_prompt_from_db(
            'images_background_change_base',
            "{final_prompt}",
            final_prompt=final_prompt_with_dimension
        )
        if dimension and dimension not in base_prompt:
            base_prompt = f"{base_prompt} Generate the image in {dimension} aspect ratio (width:height)."

        generated_bytes = None

        if has_genai:
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)

            parts = []
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": img_b64
                }
            })
            parts.append(
                {"text": "This is the ornament whose background must be changed."})

            if bg_b64:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": bg_b64
                    }
                })
                parts.append(
                    {"text": "Use this image strictly as the new background."})
                if reference_analysis:
                    parts.append({"text": f"Reference description to match: {reference_analysis}"})

            parts.append({"text": base_prompt})

            contents = [{"parts": parts}]

            config = types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE]
            )

            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )

            candidate = resp.candidates[0]
            for part in candidate.content.parts:
                if getattr(part, "inline_data", None):
                    data = part.inline_data.data
                    generated_bytes = (
                        data if isinstance(data, bytes)
                        else base64.b64decode(data)
                    )
                    break

            if not generated_bytes:
                raise Exception("Gemini 3 Pro returned no image data")
        else:
            # Fallback
            if bg_b64:
                bg_img = Image.open(
                    BytesIO(base64.b64decode(bg_b64))).convert("RGB")
                bg_img = bg_img.resize(ornament_img.size)
            else:
                bg_img = Image.new(
                    "RGB", ornament_img.size, bg_color or (255, 255, 255))

            bg_img.paste(ornament_img, (0, 0),
                         ornament_img.convert("RGBA"))
            buf = BytesIO()
            bg_img.save(buf, format="JPEG", quality=95)
            generated_bytes = buf.getvalue()

        base_name = os.path.splitext(os.path.basename(uploaded_image_path))[0]
        suffix = f"_batch_{batch_index}" if batch_index is not None else ""

        # Save generated image locally
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)
        local_generated_path = os.path.join(
            gen_dir, f"generated_{os.path.basename(uploaded_image_path)}{suffix}.jpg")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # Upload original and generated images to Cloudinary for viewing
        uploaded_cloud_url = _upload_bytes_to_cloudinary(
            ornament_bytes,
            folder="imgbackend/uploaded_ornaments",
            public_id_prefix=f"background_change_{base_name}",
        )
        generated_cloud_url = _upload_bytes_to_cloudinary(
            generated_bytes,
            folder="imgbackend/generated_backgrounds",
            public_id_prefix=f"background_change_{base_name}{suffix}",
        )

        uploaded_url = uploaded_cloud_url or _path_to_media_url(uploaded_image_path)
        generated_url = generated_cloud_url or _path_to_media_url(local_generated_path)

        # Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=final_prompt,
            uploaded_image_url=uploaded_url,
            generated_image_url=generated_url,
            uploaded_image_path=uploaded_image_path,
            generated_image_path=local_generated_path,
            type="background_change",
            user_id=user_id,
            original_prompt=prompt,
            reference_analysis=reference_analysis or "",
        )
        ornament_doc.save()

        _finish_credit_reservation(credit_reservation_id, True, self)
        return {
            "success": True,
            "message": "Background changed successfully",
            "uploaded_image_url": uploaded_url,
            "generated_image_url": generated_url,
            "prompt": prompt,
            "mongo_id": str(ornament_doc.id),
            "type": "background_change"
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        _finish_credit_reservation(credit_reservation_id, False, self)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e)
        }


@shared_task(bind=True, max_retries=3)
def change_background_combined_task(
    self,
    uploaded_image_paths,
    user_id,
    bg_color,
    background_image_path,
    prompt,
    dimension,
    reference_analysis=None,
    credit_reservation_id=None,
    ):
    """
    Change background and combine multiple product images into one.
    All uploaded images are sent to Gemini; output is a single combined image
    with the new background applied to all products in one cohesive scene.
    """
    try:
        from probackendapp.prompt_initializer import get_prompt_from_db

        # Encode all product images
        product_b64_list = []
        for path in uploaded_image_paths:
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                b = f.read()
            img = Image.open(path).convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG")
            product_b64_list.append(base64.b64encode(buf.getvalue()).decode("utf-8"))

        if not product_b64_list:
            raise Exception("No valid product images provided")

        # Background image (optional)
        bg_b64 = None
        if background_image_path and os.path.exists(background_image_path):
            bg_img = Image.open(background_image_path).convert("RGB")
            buf_bg = BytesIO()
            bg_img.save(buf_bg, format="JPEG")
            bg_b64 = base64.b64encode(buf_bg.getvalue()).decode("utf-8")

        user_prompt = (prompt or "").strip()
        ref_analysis_text = f" Reference image analysis: {reference_analysis}." if reference_analysis else ""

        if bg_b64:
            bg_prompt = get_prompt_from_db(
                "images_background_change_with_image",
                "Replace the background using the uploaded background image.",
            )
            combine_instruction = (
                " Combine all the uploaded product/ornament images into ONE single cohesive image, "
                "each product clearly visible, with this new background applied consistently. "
            )
            final_prompt = f"{user_prompt}{ref_analysis_text} {bg_prompt}{combine_instruction}"
        elif bg_color:
            color_prompt = get_prompt_from_db(
                "images_background_change_with_color",
                f"Replace the background with a clean solid {bg_color} color.",
                bg_color=bg_color,
            )
            combine_instruction = (
                " Combine all the uploaded product/ornament images into ONE single cohesive image, "
                "each product clearly visible, on this solid background color. "
            )
            final_prompt = f"{user_prompt} {color_prompt}{combine_instruction}"
        else:
            default_prompt = get_prompt_from_db(
                "images_background_change_default",
                "Change only the background without modifying the ornament.",
            )
            combine_instruction = (
                " Combine all the uploaded product/ornament images into ONE single cohesive image, "
                "each product clearly visible, with a clean new background. "
            )
            final_prompt = f"{user_prompt} {default_prompt}{combine_instruction}"

        dimension_text = (
            f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)."
            if dimension
            else ""
        )
        final_prompt_with_dimension = f"{final_prompt}{dimension_text}"

        base_prompt = get_prompt_from_db(
            "images_background_change_base",
            "{final_prompt}",
            final_prompt=final_prompt_with_dimension,
        )
        if dimension and dimension not in base_prompt:
            base_prompt = f"{base_prompt} Generate the image in {dimension} aspect ratio (width:height)."

        if not has_genai:
            raise Exception("Gemini SDK not available")

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)

        parts = []
        for i, img_b64 in enumerate(product_b64_list):
            parts.append({
                "inline_data": {"mime_type": "image/jpeg", "data": img_b64},
            })
            parts.append({
                "text": f"This is product/ornament image {i + 1} of {len(product_b64_list)}. Its background must be changed and it should appear in the final combined image.",
            })

        if bg_b64:
            parts.append({
                "inline_data": {"mime_type": "image/jpeg", "data": bg_b64},
            })
            parts.append({"text": "Use this image strictly as the new background for the combined scene."})
            if reference_analysis:
                parts.append({"text": f"Reference description to match: {reference_analysis}"})

        parts.append({"text": base_prompt})

        contents = [{"parts": parts}]
        config = types.GenerateContentConfig(
            response_modalities=[types.Modality.IMAGE],
        )

        resp = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        candidate = resp.candidates[0]
        generated_bytes = None
        for part in candidate.content.parts:
            if getattr(part, "inline_data", None):
                data = part.inline_data.data
                generated_bytes = (
                    data if isinstance(data, bytes) else base64.b64decode(data)
                )
                break

        if not generated_bytes:
            raise Exception("Gemini returned no image data")

        # Save and upload
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)
        base_name = f"background_change_combined_{len(uploaded_image_paths)}"
        local_generated_path = os.path.join(gen_dir, f"{base_name}.jpg")
        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        generated_cloud_url = _upload_bytes_to_cloudinary(
            generated_bytes,
            folder="imgbackend/generated_backgrounds",
            public_id_prefix=base_name,
        )
        generated_url = generated_cloud_url or _path_to_media_url(local_generated_path)

        # Upload first product for "uploaded" reference in MongoDB
        with open(uploaded_image_paths[0], "rb") as f:
            first_bytes = f.read()
        uploaded_cloud_url = _upload_bytes_to_cloudinary(
            first_bytes,
            folder="imgbackend/uploaded_ornaments",
            public_id_prefix=f"background_change_combined_{len(uploaded_image_paths)}",
        )
        uploaded_url = uploaded_cloud_url or _path_to_media_url(uploaded_image_paths[0])

        ornament_doc = OrnamentMongo(
            prompt=base_prompt,
            uploaded_image_url=uploaded_url,
            generated_image_url=generated_url,
            uploaded_image_path="Multiple (combined)",
            generated_image_path=local_generated_path,
            type="background_change_combined",
            user_id=user_id,
            original_prompt=prompt or "",
            reference_analysis=reference_analysis or "",
        )
        ornament_doc.save()

        _finish_credit_reservation(credit_reservation_id, True, self)
        return {
            "success": True,
            "message": "Background changed and combined successfully",
            "uploaded_image_url": uploaded_url,
            "generated_image_url": generated_url,
            "prompt": prompt,
            "mongo_id": str(ornament_doc.id),
            "type": "background_change_combined",
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        _finish_credit_reservation(credit_reservation_id, False, self)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e),
        }


@shared_task(bind=True, max_retries=3)
def generate_model_with_ornament_task(self, ornament_image_path, user_id, pose_image_path, prompt, measurements, ornament_type, ornament_measurements, dimension, batch_index=None, reference_analysis=None, credit_reservation_id=None):
    """
    Celery task to generate model with ornament. Use batch_index for multi-image generation.
    reference_analysis: optional text from analyzing the pose/reference image (model).
    """
    try:
        # Read images
        with open(ornament_image_path, "rb") as f:
            ornament_bytes = f.read()
        ornament_b64 = base64.b64encode(ornament_bytes).decode("utf-8")
        
        pose_b64 = None
        if pose_image_path and os.path.exists(pose_image_path):
            with open(pose_image_path, "rb") as f:
                pose_bytes = f.read()
            pose_b64 = base64.b64encode(pose_bytes).decode('utf-8')

        if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == 'your_api_key_here':
            raise Exception("GOOGLE_API_KEY not configured")

        generated_bytes = None

        if has_genai:
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)

            contents = [
                {"inline_data": {"mime_type": "image/jpeg", "data": ornament_b64}},
            ]
            if pose_b64:
                contents.append(
                    {"inline_data": {"mime_type": "image/jpeg", "data": pose_b64}}
                )

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
            pose_ref_text = f" Pose and style reference from image: {reference_analysis}." if reference_analysis else ""
            default_prompt = (
                "Generate a close-up, high-fashion portrait of an elegant Indian woman "
                "wearing this 100% real accurate uploaded ornament. Focus tightly on the neckline and jewelry area according to the ornament. "
                "Ensure the jewelry fits naturally and realistically on the model. "
                "Lighting should be soft and natural, highlighting the sparkle of the jewelry and the model's features. "
                "Use a shallow depth of field with a softly blurred background that hints at an elegant setting. "
                "Do not include any watermark, text, or unnatural effects. "
                f"{ornament_description}"
                f"{measurements_text}Make sure to follow the measurements strictly."
                f"{pose_ref_text}"
                f"{prompt_text}"
            )
            user_prompt = get_prompt_from_db(
                'images_model_with_ornament',
                default_prompt,
                ornament_description=ornament_description,
                measurements_text=measurements_text,
                user_prompt=prompt
            )
            dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
            if dimension and dimension not in user_prompt:
                user_prompt = f"{user_prompt}{dimension_text}"

            contents.append({"text": user_prompt})

            config = types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE]
            )

            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )

            candidate = resp.candidates[0]
            for part in candidate.content.parts:
                if part.inline_data:
                    data = part.inline_data.data
                    generated_bytes = (
                        data if isinstance(data, bytes)
                        else base64.b64decode(data)
                    )
                    break

            if not generated_bytes:
                raise Exception("No image returned from Gemini")
        else:
            raise Exception("Gemini SDK not available or misconfigured.")

        base_name = os.path.splitext(os.path.basename(ornament_image_path))[0]
        suffix = f"_batch_{batch_index}" if batch_index is not None else ""

        # Save generated image locally
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)
        local_generated_path = os.path.join(
            gen_dir, f"generated_{os.path.basename(ornament_image_path)}{suffix}.jpg")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # Upload original and generated images to Cloudinary for viewing
        uploaded_cloud_url = _upload_bytes_to_cloudinary(
            ornament_bytes,
            folder="imgbackend/uploaded_ornaments",
            public_id_prefix=f"model_with_ornament_{base_name}",
        )
        generated_cloud_url = _upload_bytes_to_cloudinary(
            generated_bytes,
            folder="imgbackend/generated_models",
            public_id_prefix=f"model_with_ornament_{base_name}{suffix}",
        )

        uploaded_url = uploaded_cloud_url or _path_to_media_url(ornament_image_path)
        generated_url = generated_cloud_url or _path_to_media_url(local_generated_path)

        # Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=user_prompt,
            uploaded_image_url=uploaded_url,
            generated_image_url=generated_url,
            uploaded_image_path=ornament_image_path,
            generated_image_path=local_generated_path,
            type="model_with_ornament",
            user_id=user_id,
            original_prompt=prompt,
            reference_analysis=reference_analysis or "",
        )
        ornament_doc.save()

        _finish_credit_reservation(credit_reservation_id, True, self)
        return {
            "status": "success",
            "message": "Generated AI close-up model wearing ornament successfully.",
            "prompt": prompt,
            "measurements": measurements,
            "uploaded_image_url": uploaded_url,
            "generated_image_url": generated_url,
            "mongo_id": str(ornament_doc.id),
            "type": "model_with_ornament"
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        _finish_credit_reservation(credit_reservation_id, False, self)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "status": "error",
            "message": str(e),
            "user_friendly_message": get_user_friendly_message(e),
        }


@shared_task(bind=True, max_retries=3)
def generate_real_model_with_ornament_task(self, model_image_path, ornament_image_path, user_id, pose_image_path, prompt, measurements, ornament_type, ornament_measurements, dimension, batch_index=None, reference_analysis=None, credit_reservation_id=None):
    """
    Celery task to generate real model with ornament. Use batch_index for multi-image generation.
    reference_analysis: optional text from analyzing the pose/reference image (model).
    """
    try:
        # Read images
        with open(model_image_path, "rb") as f:
            model_bytes = f.read()
        model_b64 = base64.b64encode(model_bytes).decode("utf-8")
        
        with open(ornament_image_path, "rb") as f:
            ornament_bytes = f.read()
        ornament_b64 = base64.b64encode(ornament_bytes).decode("utf-8")
        
        pose_b64 = None
        if pose_image_path and os.path.exists(pose_image_path):
            with open(pose_image_path, "rb") as f:
                pose_bytes = f.read()
            pose_b64 = base64.b64encode(pose_bytes).decode("utf-8")

        if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == 'your_api_key_here':
            raise Exception("GOOGLE_API_KEY not configured")

        generated_bytes = None

        if has_genai:
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)

            contents = [
                {"inline_data": {"mime_type": "image/jpeg", "data": ornament_b64}},
                {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}},
            ]
            if pose_b64:
                contents.append(
                    {"inline_data": {"mime_type": "image/jpeg", "data": pose_b64}})

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
            pose_ref_text = f" Pose and style reference from image: {reference_analysis}." if reference_analysis else ""
            default_prompt = (
                "Generate a realistic, high-quality close-up image of the uploaded model wearing "
                "the exact uploaded ornament. Keep the model's face fully intact and recognizable. "
                "Ensure the ornament fits naturally and realistically on the model. "
                "Generate a background suitable for both the model and the ornament. "
                "Lighting should be soft, natural, and elegant. "
                "Focus tightly on the jewelry area. "
                "Follow the pose from the uploaded pose image if provided. "
                f"{ornament_description}"
                f"{measurements_text}"
                f"{pose_ref_text}"
                f"{prompt_text}"
            )
            user_prompt = get_prompt_from_db(
                'images_real_model_with_ornament',
                default_prompt,
                ornament_description=ornament_description,
                measurements_text=measurements_text,
                user_prompt=prompt
            )
            if prompt:
                user_prompt = f"{user_prompt} {prompt}"
            
            dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
            if dimension and dimension not in user_prompt:
                user_prompt = f"{user_prompt}{dimension_text}"

            contents.append({"text": user_prompt})
            config = types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE])

            resp = client.models.generate_content(
                model=model_name, contents=contents, config=config)
            candidate = resp.candidates[0]

            for part in candidate.content.parts:
                if part.inline_data:
                    data = part.inline_data.data
                    generated_bytes = data if isinstance(
                        data, bytes) else base64.b64decode(data)
                    break

            if not generated_bytes:
                raise Exception("No image returned from Gemini")
        else:
            raise Exception(
                "Gemini SDK not available. Please install or configure it.")

        model_base = os.path.splitext(os.path.basename(model_image_path))[0]
        ornament_base = os.path.splitext(os.path.basename(ornament_image_path))[0]
        suffix = f"_batch_{batch_index}" if batch_index is not None else ""

        # Save generated image locally
        generated_dir = os.path.join(
            settings.MEDIA_ROOT, "generated_models")
        os.makedirs(generated_dir, exist_ok=True)
        local_generated_path = os.path.join(
            generated_dir, f"generated_{os.path.basename(model_image_path)}{suffix}.jpg")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # Upload original and generated images to Cloudinary for viewing
        model_cloud_url = _upload_bytes_to_cloudinary(
            model_bytes,
            folder="imgbackend/uploaded_models",
            public_id_prefix=f"real_model_{model_base}",
        )
        ornament_cloud_url = _upload_bytes_to_cloudinary(
            ornament_bytes,
            folder="imgbackend/uploaded_ornaments",
            public_id_prefix=f"real_model_ornament_{ornament_base}",
        )
        generated_cloud_url = _upload_bytes_to_cloudinary(
            generated_bytes,
            folder="imgbackend/generated_models",
            public_id_prefix=f"real_model_with_ornament_{model_base}{suffix}",
        )

        model_url = model_cloud_url or _path_to_media_url(model_image_path)
        ornament_url = ornament_cloud_url or _path_to_media_url(ornament_image_path)
        generated_url = generated_cloud_url or _path_to_media_url(local_generated_path)

        # Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=user_prompt,
            model_image_url=model_url,
            uploaded_image_url=ornament_url,
            generated_image_url=generated_url,
            uploaded_image_path=model_image_path,
            generated_image_path=local_generated_path,
            type="real_model_with_ornament",
            user_id=user_id,
            original_prompt=prompt,
            reference_analysis=reference_analysis or "",
        )
        ornament_doc.save()

        _finish_credit_reservation(credit_reservation_id, True, self)
        return {
            "status": "success",
            "message": "Generated AI image of the model wearing ornament successfully.",
            "prompt": prompt,
            "measurements": measurements,
            "model_image_url": model_url,
            "ornament_image_url": ornament_url,
            "generated_image_url": generated_url,
            "mongo_id": str(ornament_doc.id),
            "type": "real_model_with_ornament"
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        _finish_credit_reservation(credit_reservation_id, False, self)
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
    theme_image_paths,
    prompt,
    dimension,
    ornament_measurements='[]',
    batch_index=None,
    theme_reference_analysis=None,
    credit_reservation_id=None,
):
    """
    Celery task to generate campaign shot. Use batch_index for multi-image generation.
    theme_reference_analysis: optional text from analyzing theme reference image(s) (campaign).
    """
    try:
        # Cloudinary URLs (or local fallbacks) for ornaments
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
            with open(ornament_path, "rb") as f:
                ornament_bytes = f.read()

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

            ornament_cloud_url = _upload_bytes_to_cloudinary(
                ornament_bytes,
                folder="imgbackend/uploaded_ornaments",
                public_id_prefix=f"campaign_ornament_{os.path.splitext(os.path.basename(ornament_path))[0]}_{idx}",
            )
            ornament_urls.append(ornament_cloud_url or _path_to_media_url(ornament_path))

            ornament_b64_list.append({
                "name": ornament_name,
                "type": ornament_type,
                "measurements": per_ornament_measurements,
                "data": base64.b64encode(ornament_bytes).decode('utf-8')
            })

        # Model: use Cloudinary URL (or local fallback) and encoding
        model_url = None
        model_b64 = None
        if model_image_path and os.path.exists(model_image_path):
            with open(model_image_path, "rb") as f:
                model_bytes = f.read()
            model_cloud_url = _upload_bytes_to_cloudinary(
                model_bytes,
                folder="imgbackend/uploaded_models",
                public_id_prefix=f"campaign_model_{os.path.splitext(os.path.basename(model_image_path))[0]}",
            )
            model_url = model_cloud_url or _path_to_media_url(model_image_path)
            model_b64 = base64.b64encode(model_bytes).decode('utf-8')

        # Theme images encoding
        theme_b64_list = []
        for theme_path in theme_image_paths:
            if os.path.exists(theme_path):
                with open(theme_path, "rb") as f:
                    theme_bytes = f.read()
                theme_b64_list.append(base64.b64encode(
                    theme_bytes).decode('utf-8'))

        # Check Gemini configuration
        if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == 'your_api_key_here':
            raise Exception("GOOGLE_API_KEY not configured")
        if not has_genai:
            raise Exception("Gemini SDK not available. Please install or configure it.")

        # Build Gemini request
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)

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

        # Themes (optional)
        for theme_b64 in theme_b64_list:
            parts.append(
                {"inline_data": {"mime_type": "image/jpeg", "data": theme_b64}})
            parts.append(
                {"text": "Reference for background or theme styling."})
        if theme_reference_analysis:
            parts.append({"text": f"Theme/style reference description: {theme_reference_analysis}"})

        # Get prompt from database
        from probackendapp.prompt_initializer import get_prompt_from_db

        if model_type == 'real_model':
            theme_ref_text = f" Match theme/style/mood: {theme_reference_analysis}." if theme_reference_analysis else ""
            default_prompt = (
                "Generate a realistic image of the uploaded real model wearing all the uploaded ornaments. "
                "Preserve the model's facial features and natural pose while making a small smile. "
                f"{theme_ref_text} Campaign instructions: {prompt}"
            )
            user_prompt = get_prompt_from_db(
                'images_campaign_shot_real',
                default_prompt,
                user_prompt=prompt
            )
        else:
            theme_ref_text = f" Match theme/style/mood: {theme_reference_analysis}." if theme_reference_analysis else ""
            default_prompt = (
                "Generate a high-quality campaign image of a model wearing all the uploaded ornaments. "
                "Use realistic lighting, texture, and cohesive fashion aesthetics. "
                f"{theme_ref_text} Campaign instructions: {prompt}"
            )
            user_prompt = get_prompt_from_db(
                'images_campaign_shot_ai',
                default_prompt,
                user_prompt=prompt
            )
            if prompt:
                user_prompt = f"{user_prompt} {prompt}"
        
        dimension_text = f" Generate the ultra high quality image in {dimension} aspect ratio (width:height)." if dimension else ""
        if dimension and dimension not in user_prompt:
            user_prompt = f"{user_prompt}{dimension_text}"

        parts.append({"text": user_prompt})
        contents = [{"parts": parts}]

        config = types.GenerateContentConfig(
            response_modalities=[types.Modality.IMAGE]
        )

        # Generate via Gemini
        resp = client.models.generate_content(
            model=model_name, contents=contents, config=config)
        candidate = resp.candidates[0]

        generated_bytes = None
        for part in candidate.content.parts:
            if getattr(part, "inline_data", None):
                data = part.inline_data.data
                generated_bytes = data if isinstance(
                    data, bytes) else base64.b64decode(data)
                break

        if not generated_bytes:
            raise Exception("No image returned from Gemini")

        # Save generated image locally and upload to Cloudinary for viewing
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated")
        os.makedirs(gen_dir, exist_ok=True)
        campaign_filename = f"campaign_{len(ornament_image_paths)}{f'_batch_{batch_index}' if batch_index is not None else ''}.jpg"
        local_campaign_path = os.path.join(gen_dir, campaign_filename)
        with open(local_campaign_path, "wb") as f:
            f.write(generated_bytes)
        campaign_cloud_url = _upload_bytes_to_cloudinary(
            generated_bytes,
            folder="imgbackend/generated_campaigns",
            public_id_prefix=f"campaign_shot_{len(ornament_image_paths)}{f'_batch_{batch_index}' if batch_index is not None else ''}",
        )
        generated_url = campaign_cloud_url or _path_to_media_url(local_campaign_path)

        # Save record to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=prompt,
            type="campaign_shot_advanced",
            model_image_url=model_url,
            uploaded_ornament_urls=ornament_urls,
            generated_image_url=generated_url,
            uploaded_image_path="Multiple ornaments",
            generated_image_path=local_campaign_path,
            user_id=user_id,
            original_prompt=prompt,
            reference_analysis=theme_reference_analysis or "",
        )
        ornament_doc.save()

        _finish_credit_reservation(credit_reservation_id, True, self)
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
            "type": "campaign_shot_advanced"
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        _finish_credit_reservation(credit_reservation_id, False, self)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "status": "error",
            "message": str(e)
        }


@shared_task(bind=True, max_retries=3)
def regenerate_image_task(self, image_id, user_id, new_prompt, credit_reservation_id=None):
    """
    Celery task to regenerate an image.
    """
    try:
        import re

        # Validate MongoDB ObjectId format
        object_id_pattern = re.compile(r'^[0-9a-fA-F]{24}$')
        if not object_id_pattern.match(image_id):
            _finish_credit_reservation(credit_reservation_id, False, self)
            return {
                "success": False,
                "error": f"Invalid image_id: '{image_id}' is not a valid MongoDB ObjectId.",
                "user_friendly_message": get_user_friendly_message("Invalid image_id"),
            }

        # Fetch the previous image record from MongoDB
        try:
            prev_doc = OrnamentMongo.objects.get(id=ObjectId(image_id))
        except OrnamentMongo.DoesNotExist:
            _finish_credit_reservation(credit_reservation_id, False, self)
            return {
                "success": False,
                "error": "Image record not found",
                "user_friendly_message": get_user_friendly_message("Image record not found"),
            }

        # Verify that the image belongs to the user
        if prev_doc.user_id != user_id:
            _finish_credit_reservation(credit_reservation_id, False, self)
            return {
                "success": False,
                "error": "You don't have permission to regenerate this image",
                "user_friendly_message": get_user_friendly_message("permission to regenerate"),
            }

        # Get the previous generated image (local URL or Cloudinary URL)
        prev_generated_url = prev_doc.generated_image_url

        # Build prompt using admin-configured regeneration prompt (same for all types: white background, background replace, model, campaign)
        original_prompt = prev_doc.original_prompt or prev_doc.prompt
        reference_analysis = getattr(prev_doc, "reference_analysis", None) or ""
        measurements = getattr(prev_doc, "measurements", None)
        measurements_placeholder = f"measurements: {measurements}. " if measurements else ""
        image_type = getattr(prev_doc, "type", None) or ""

        from probackendapp.prompt_initializer import get_prompt_from_db
        default_regen_prompt = (
            "Reference context: {reference_analysis}. {original_prompt}. User modifications: {new_prompt}. {measurements}"
        )
        combined_prompt = get_prompt_from_db(
            "image_regeneration_prompt",
            default_prompt=default_regen_prompt,
            reference_analysis=reference_analysis,
            original_prompt=original_prompt or "",
            new_prompt=new_prompt or "",
            measurements=measurements_placeholder,
            image_type=image_type,
        )
        if not combined_prompt:
            combined_prompt = f"Reference context: {reference_analysis}. {original_prompt}. {new_prompt}. {measurements_placeholder}"
        measurements_text = measurements_placeholder

        # Load the previous generated image (supports /media/ URLs, local paths, and http/https URLs)
        img_bytes = _url_or_path_to_bytes(prev_generated_url)
        if not img_bytes:
            raise Exception(f"Could not load previous generated image: {prev_generated_url}")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        
        # Generate new image using Gemini
        generated_bytes = None

        if has_genai:
            if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == 'your_api_key_here':
                raise Exception("GOOGLE_API_KEY not configured")

            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            model_name = get_image_model_name(default_model=settings.IMAGE_MODEL_NAME)

            contents = [
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                {"text": combined_prompt},
                {"text": measurements_text}
            ]

            config = types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE]
            )

            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )

            candidate = resp.candidates[0]
            for part in candidate.content.parts:
                if getattr(part, 'inline_data', None):
                    data = part.inline_data.data
                    generated_bytes = data if isinstance(
                        data, bytes) else base64.b64decode(data)
                    break

            if not generated_bytes:
                raise Exception("Gemini response had no image inline_data")
        else:
            # Fallback: Use OpenCV/PIL processing
            original = Image.open(BytesIO(img_bytes)).convert("RGB")
            img_array = np.array(original)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blur, 240, 255, cv2.THRESH_BINARY_INV)

            kernel = np.ones((3, 3), np.uint8)
            thresh = cv2.morphologyEx(
                thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
            thresh = cv2.morphologyEx(
                thresh, cv2.MORPH_OPEN, kernel, iterations=1)

            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                mask = np.zeros_like(gray)
                cv2.drawContours(mask, [largest_contour], -1, 255, -1)
                mask = cv2.GaussianBlur(mask, (5, 5), 0)
                rgba_array = np.dstack((img_array, mask))
                transparent_img = Image.fromarray(rgba_array, 'RGBA')
                white_bg = Image.new("RGB", original.size, (255, 255, 255))
                white_bg.paste(transparent_img,
                               mask=transparent_img.split()[3])
                buf = BytesIO()
                white_bg.save(buf, format="JPEG", quality=95)
                generated_bytes = buf.getvalue()
            else:
                raise Exception(
                    "Could not process image using fallback method.")
       

        # Save regenerated image locally
        regen_filename = f"regen_{image_id}_{int(time.time())}.jpg"
        regen_dir = os.path.join(settings.MEDIA_ROOT, "generated")
        os.makedirs(regen_dir, exist_ok=True)
        local_regen_path = os.path.join(regen_dir, regen_filename)

        with open(local_regen_path, "wb") as f:
            f.write(generated_bytes)

        # Upload regenerated image to Cloudinary for viewing
        regen_cloud_url = _upload_bytes_to_cloudinary(
            generated_bytes,
            folder="imgbackend/generated_regenerated",
            public_id_prefix=f"regen_{image_id}",
        )
        regenerated_url = regen_cloud_url or _path_to_media_url(local_regen_path)

        # Create new MongoDB document for the regenerated image
        new_doc = OrnamentMongo(
            prompt=combined_prompt,
            type=prev_doc.type,
            user_id=user_id,
            parent_image_id=ObjectId(image_id),
            original_prompt=original_prompt,
            uploaded_image_url=prev_doc.uploaded_image_url,
            generated_image_url=regenerated_url,
            uploaded_image_path=prev_doc.uploaded_image_path,
            generated_image_path=local_regen_path,
            model_image_url=prev_doc.model_image_url if hasattr(
                prev_doc, 'model_image_url') else None,
            uploaded_ornament_urls=prev_doc.uploaded_ornament_urls if hasattr(
                prev_doc, 'uploaded_ornament_urls') else None,
            reference_analysis=getattr(prev_doc, "reference_analysis", None) or "",
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
                local_path=local_regen_path,
                metadata={
                    "uploaded_image_url": prev_doc.uploaded_image_url,
                    "model_image_url": getattr(prev_doc, 'model_image_url', None)
                }
            )
            
        except Exception as history_error:
            print(f"Error tracking regeneration history: {history_error}")

        _finish_credit_reservation(credit_reservation_id, True, self)
        return {
            "success": True,
            "message": "Image regenerated successfully",
            "mongo_id": str(new_doc.id),
            "parent_image_id": image_id,
            "generated_image_url": regenerated_url,
            "uploaded_image_url": prev_doc.uploaded_image_url,
            "combined_prompt": combined_prompt,
            "original_prompt": original_prompt,
            "new_prompt": new_prompt,
            "type": prev_doc.type
        }

    except Exception as e:
        traceback.print_exc()
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        _finish_credit_reservation(credit_reservation_id, False, self)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e),
            "user_friendly_message": get_user_friendly_message(e),
        }
