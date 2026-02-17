"""
Celery tasks for image generation in imgbackendapp.
These tasks handle asynchronous image generation using Gemini API.
"""
import os
import base64
import traceback
import time
from io import BytesIO
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

# Check for Gemini SDK
try:
    from google import genai
    from google.genai import types
    has_genai = True
except ImportError:
    has_genai = False


@shared_task(bind=True, max_retries=3)
def generate_white_background_task(self, ornament_id, user_id, bg_color, extra_prompt, dimension):
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

        # Upload original and generated to Cloudinary
        ornament_buf = BytesIO(img_bytes)
        ornament_buf.seek(0)
        upload_orig = cloudinary.uploader.upload(
            ornament_buf,
            folder="ornaments",
            public_id=f"ornament_original_{ornament.id}",
            overwrite=True
        )
        uploaded_image_url = upload_orig["secure_url"]

        buf = BytesIO(generated_bytes)
        buf.seek(0)
        upload_gen = cloudinary.uploader.upload(
            buf,
            folder="ornaments",
            public_id=f"ornament_generated_{ornament.id}",
            overwrite=True
        )
        generated_image_url = upload_gen["secure_url"]

        # Save in MongoDB
        filename = f"{ornament.id}_generated.jpg"
        ornament_doc = OrnamentMongo(
            prompt=text_prompt,
            uploaded_image_url=uploaded_image_url,
            generated_image_url=generated_image_url,
            uploaded_image_path=ornament.image.path,
            generated_image_path=filename,
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
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e)
        }


@shared_task(bind=True, max_retries=3)
def change_background_task(self, uploaded_image_path, user_id, bg_color, background_image_path, prompt, dimension):
    """
    Celery task to change background of an image.
    
    Args:
        uploaded_image_path: Path to uploaded ornament image
        user_id: User ID string
        bg_color: Background color (if no background image)
        background_image_path: Path to background image (optional)
        prompt: User prompt
        dimension: Aspect ratio dimension
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
            final_prompt = f"{user_prompt} {bg_prompt}"
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

        # Upload original ornament to Cloudinary
        uploaded_result = cloudinary.uploader.upload(
            uploaded_image_path,
            folder="ornaments_originals",
            public_id=f"ornament_original_{os.path.splitext(os.path.basename(uploaded_image_path))[0]}",
            overwrite=True
        )
        uploaded_url = uploaded_result["secure_url"]

        # Save generated image locally
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)
        local_generated_path = os.path.join(
            gen_dir, f"generated_{os.path.basename(uploaded_image_path)}")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # Upload final generated image
        upload_result = cloudinary.uploader.upload(
            local_generated_path,
            folder="ornaments_bg_change",
            public_id=f"ornament_bg_{os.path.splitext(os.path.basename(uploaded_image_path))[0]}",
            overwrite=True
        )
        generated_url = upload_result['secure_url']

        # Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=final_prompt,
            uploaded_image_url=uploaded_url,
            generated_image_url=generated_url,
            uploaded_image_path=uploaded_image_path,
            generated_image_path=local_generated_path,
            type="background_change",
            user_id=user_id,
            original_prompt=prompt
        )
        ornament_doc.save()

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
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e)
        }


@shared_task(bind=True, max_retries=3)
def generate_model_with_ornament_task(self, ornament_image_path, user_id, pose_image_path, prompt, measurements, ornament_type, ornament_measurements, dimension):
    """
    Celery task to generate model with ornament.
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

        # Upload ornament to Cloudinary
        uploaded_result = cloudinary.uploader.upload(
            ornament_image_path,
            folder="ornaments_originals",
            public_id=f"ornament_original_{os.path.splitext(os.path.basename(ornament_image_path))[0]}",
            overwrite=True
        )
        uploaded_url = uploaded_result["secure_url"]

        # Save generated image locally
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)
        local_generated_path = os.path.join(
            gen_dir, f"generated_{os.path.basename(ornament_image_path)}")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # Upload generated image to Cloudinary
        upload_result = cloudinary.uploader.upload(
            local_generated_path,
            folder="model_ornament",
            public_id=f"ornament_generated_{os.path.splitext(os.path.basename(ornament_image_path))[0]}",
            overwrite=True
        )
        generated_url = upload_result['secure_url']

        # Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=user_prompt,
            uploaded_image_url=uploaded_url,
            generated_image_url=generated_url,
            uploaded_image_path=ornament_image_path,
            generated_image_path=local_generated_path,
            type="model_with_ornament",
            user_id=user_id,
            original_prompt=prompt
        )
        ornament_doc.save()

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
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "status": "error",
            "message": str(e),
            "user_friendly_message": get_user_friendly_message(e),
        }


@shared_task(bind=True, max_retries=3)
def generate_real_model_with_ornament_task(self, model_image_path, ornament_image_path, user_id, pose_image_path, prompt, measurements, ornament_type, ornament_measurements, dimension):
    """
    Celery task to generate real model with ornament.
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

        # Upload images to Cloudinary
        model_upload = cloudinary.uploader.upload(
            model_image_path,
            folder="models_originals",
            public_id=f"model_original_{os.path.splitext(os.path.basename(model_image_path))[0]}",
            overwrite=True
        )
        ornament_upload = cloudinary.uploader.upload(
            ornament_image_path,
            folder="ornaments_originals",
            public_id=f"ornament_original_{os.path.splitext(os.path.basename(ornament_image_path))[0]}",
            overwrite=True
        )

        model_url = model_upload["secure_url"]
        ornament_url = ornament_upload["secure_url"]

        # Save generated image locally
        generated_dir = os.path.join(
            settings.MEDIA_ROOT, "generated_models")
        os.makedirs(generated_dir, exist_ok=True)
        local_generated_path = os.path.join(
            generated_dir, f"generated_{os.path.basename(model_image_path)}")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # Upload generated image to Cloudinary
        upload_result = cloudinary.uploader.upload(
            local_generated_path,
            folder="real_model_output",
            public_id=f"model_generated_{os.path.splitext(os.path.basename(model_image_path))[0]}",
            overwrite=True
        )
        generated_url = upload_result["secure_url"]

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
            original_prompt=prompt
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
            "type": "real_model_with_ornament"
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
def generate_campaign_shot_advanced_task(self, user_id, model_type, model_image_path, ornament_image_paths, ornament_names, theme_image_paths, prompt, dimension):
    """
    Celery task to generate campaign shot.
    """
    try:
        # Upload ornaments to Cloudinary & encode
        ornament_urls = []
        ornament_b64_list = []
        for idx, ornament_path in enumerate(ornament_image_paths):
            with open(ornament_path, "rb") as f:
                ornament_bytes = f.read()
            
            # Upload
            result = cloudinary.uploader.upload(
                ornament_path, folder="ornaments", overwrite=True)
            ornament_urls.append(result['secure_url'])

            # Encode
            ornament_name = ornament_names[idx] if idx < len(
                ornament_names) else f"Ornament {idx+1}"
            ornament_b64_list.append({
                "name": ornament_name,
                "data": base64.b64encode(ornament_bytes).decode('utf-8')
            })

        # Model upload & encoding
        model_url = None
        model_b64 = None
        if model_image_path and os.path.exists(model_image_path):
            with open(model_image_path, "rb") as f:
                model_bytes = f.read()
            model_upload = cloudinary.uploader.upload(
                model_image_path, folder="models", overwrite=True)
            model_url = model_upload['secure_url']
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
                {"inline_data": {"mime_type": "image/jpeg", "data": ornament["data"]}})
            parts.append(
                {"text": f"Reference for ornament: {ornament['name']}"})

        # Themes (optional)
        for theme_b64 in theme_b64_list:
            parts.append(
                {"inline_data": {"mime_type": "image/jpeg", "data": theme_b64}})
            parts.append(
                {"text": "Reference for background or theme styling."})

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

        # Upload generated image
        buf = BytesIO(generated_bytes)
        buf.seek(0)
        upload_result = cloudinary.uploader.upload(
            buf, folder="campaign_shots", overwrite=True)
        generated_url = upload_result['secure_url']

        # Save record to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=prompt,
            type="campaign_shot_advanced",
            model_image_url=model_url,
            uploaded_ornament_urls=ornament_urls,
            generated_image_url=generated_url,
            uploaded_image_path="Multiple ornaments",
            generated_image_path=f"media/generated/campaign_{len(ornament_image_paths)}.jpg",
            user_id=user_id,
            original_prompt=prompt
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
            "type": "campaign_shot_advanced"
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
def regenerate_image_task(self, image_id, user_id, new_prompt):
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

        # Get the previous generated image URL from Cloudinary
        prev_generated_url = prev_doc.generated_image_url

        # Combine the original prompt with the new prompt
        original_prompt = prev_doc.original_prompt or prev_doc.prompt
        combined_prompt = f"{original_prompt}. {new_prompt}"
        measurements = prev_doc.measurements
        measurements_text = f"measurements: {measurements}. " if measurements else ""
        
        # Download the previous generated image from Cloudinary
        with urlopen(prev_generated_url) as resp:
            img_bytes = resp.read()
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

        # Upload regenerated image to Cloudinary
        buf = BytesIO(generated_bytes)
        buf.seek(0)
        upload_result = cloudinary.uploader.upload(
            buf,
            folder="ornaments_regenerated",
            public_id=f"regen_{image_id}_{int(time.time())}",
            overwrite=True
        )
        regenerated_url = upload_result['secure_url']

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
                prev_doc, 'uploaded_ornament_urls') else None
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
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {
            "success": False,
            "error": str(e),
            "user_friendly_message": get_user_friendly_message(e),
        }
