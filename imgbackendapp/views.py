

# imgbackendapp/views.py
import base64
import traceback
from io import BytesIO
from django.shortcuts import render
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib import messages
from django.http import JsonResponse
import cloudinary.uploader
from .forms import OrnamentForm, BackgroundChangeForm
from .models import Ornament
from .mongo_models import OrnamentMongo
from PIL import Image
import numpy as np
import cv2
import os
import time
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from rest_framework.response import Response
from rest_framework.decorators import api_view
from common.middleware import authenticate
from urllib.request import urlopen
from bson import ObjectId
import re

# Check for Gemini SDK
try:
    from google import genai
    from google.genai import types
    has_genai = True
except ImportError:
    has_genai = False


@api_view(['POST'])
@csrf_exempt
@authenticate
def upload_ornament(request):
    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    form = OrnamentForm(request.POST, request.FILES)
    if form.is_valid():
        ornament = form.save()
        try:
            bg_color = request.POST.get(
                "background_color", "white").strip()
            extra_prompt = request.POST.get("prompt", "").strip()
            dimension = request.POST.get("dimension", "1:1").strip()

            with open(ornament.image.path, "rb") as f:
                img_bytes = f.read()
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            generated_bytes = None
            # Get prompt from database
            from probackendapp.prompt_initializer import get_prompt_from_db
            extra_prompt_text = f" {extra_prompt}" if extra_prompt else ""
            dimension_text = f" Generate the image in {dimension} aspect ratio (width:height)." if dimension else ""
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

            if has_genai:
                if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == "your_api_key_here":
                    raise Exception("GOOGLE_API_KEY not configured")

                client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                model_name = "gemini-3-pro-image-preview"

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
                    messages.warning(
                        request, "Gemini did not return an image. Using local fallback.")

            # ---- Fallback ----
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

            # ---- Upload original and generated to Cloudinary ----
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

            # ---- Save in MongoDB ----
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
                print(
                    f"Error tracking image generation history: {history_error}")

            # ---- Save locally in Django model ----
            ornament.generated_image.save(
                filename, ContentFile(generated_bytes), save=True)

            return JsonResponse({
                "success": True,
                "message": "Image generated successfully",
                "uploaded_image_url": uploaded_image_url,
                "generated_image_url": generated_image_url,
                "prompt": text_prompt,
                "ornament_id": ornament.id,
                "mongo_id": str(ornament_doc.id),
                "type": "white_background"
            })

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({"success": False, "error": str(e)})

    else:
        print("Form errors:", form.errors)
        return JsonResponse({"success": False, "error": "Invalid form submission"})


@api_view(['POST'])
@csrf_exempt
@authenticate
def change_background(request):
    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    # === Credit Check and Deduction ===
    from CREDITS.utils import deduct_credits, get_user_organization
    from users.models import Role

    # Credits per image generation: 2 credits for new image generation
    CREDITS_PER_IMAGE = 2

    # Check if user has organization - if not, allow generation without credit deduction
    organization = get_user_organization(user)
    if organization:
        # Check and deduct credits before generation
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Background change image generation",
            metadata={"type": "change_background"}
        )

        if not credit_result['success']:
            return Response({"error": credit_result['message']}, status=400)
    # If no organization, allow generation to proceed without credit deduction

    print("POST keys:", request.POST.keys())
    print("FILES keys:", request.FILES.keys())

    form = BackgroundChangeForm(request.POST, request.FILES)

    if form.is_valid():
        ornament = form.cleaned_data['ornament_image']
        background = form.cleaned_data.get('background_image')
        bg_color = form.cleaned_data.get('background_color')
        prompt = form.cleaned_data.get('prompt', '')
        dimension = request.POST.get('dimension', '1:1').strip()

        try:
            # -----------------------------
            # SAVE ORNAMENT LOCALLY
            # -----------------------------
            upload_dir = os.path.join(
                settings.MEDIA_ROOT, "uploaded_ornaments")
            os.makedirs(upload_dir, exist_ok=True)
            local_uploaded_path = os.path.join(upload_dir, ornament.name)

            with open(local_uploaded_path, "wb+") as dest:
                for chunk in ornament.chunks():
                    dest.write(chunk)

            # Upload original ornament to Cloudinary
            uploaded_result = cloudinary.uploader.upload(
                local_uploaded_path,
                folder="ornaments_originals",
                public_id=f"ornament_original_{os.path.splitext(ornament.name)[0]}",
                overwrite=True
            )
            uploaded_url = uploaded_result["secure_url"]

            # Convert ornament to base64
            ornament_img = Image.open(local_uploaded_path).convert("RGB")
            buf_ornament = BytesIO()
            ornament_img.save(buf_ornament, format="JPEG")
            img_b64 = base64.b64encode(buf_ornament.getvalue()).decode("utf-8")

            # -----------------------------
            # BACKGROUND IMAGE → BASE64
            # -----------------------------
            if background:
                bg_img = Image.open(background).convert("RGB")
                buf_bg = BytesIO()
                bg_img.save(buf_bg, format="JPEG")
                bg_b64 = base64.b64encode(buf_bg.getvalue()).decode("utf-8")
            else:
                bg_b64 = None

            # -----------------------------
            # PROMPT BUILDING (NEW PRIORITY LOGIC)
            # -----------------------------
            from probackendapp.prompt_initializer import get_prompt_from_db
            user_prompt = prompt.strip()

            # Priority 1 → BACKGROUND IMAGE ALWAYS OVERRIDES COLOR
            if bg_b64:
                bg_prompt = get_prompt_from_db(
                    'images_background_change_with_image',
                    "Replace the background using the uploaded background image."
                )
                # print("bg_prompt", bg_prompt)
                final_prompt = f"{user_prompt} {bg_prompt}"
                print("final_prompt", final_prompt)
            # Priority 2 → BACKGROUND COLOR (ONLY IF NO IMAGE)
            elif bg_color:
                color_prompt = get_prompt_from_db(
                    'images_background_change_with_color',
                    f"Replace the background with a clean solid {bg_color} color.",
                    bg_color=bg_color
                )
                final_prompt = f"{user_prompt} {color_prompt}"

            # Priority 3 → DEFAULT
            else:
                default_prompt = get_prompt_from_db(
                    'images_background_change_default',
                    "Change only the background without modifying the ornament."
                )
                final_prompt = f"{user_prompt} {default_prompt}"

            # Add dimension to prompt
            dimension_text = f" Generate the image in {dimension} aspect ratio (width:height)." if dimension else ""
            final_prompt_with_dimension = f"{final_prompt}{dimension_text}"
            
            # Wrap prompt for Gemini
            base_prompt = get_prompt_from_db(
                'images_background_change_base',
                "{final_prompt}",
                final_prompt=final_prompt_with_dimension
            )
            # Ensure dimension is in the final prompt if not already included
            if dimension and dimension not in base_prompt:
                base_prompt = f"{base_prompt} Generate the image in {dimension} aspect ratio (width:height)."

            generated_bytes = None

            # ========================================================
            #                GEMINI IMAGE GENERATION
            # ========================================================
            # ========================================================
            #                GEMINI 3 PRO IMAGE GENERATION
            # ========================================================
            if has_genai:
                client = genai.Client(api_key=settings.GOOGLE_API_KEY)

                # ✅ Gemini 3 Pro Image (Nano Banana Pro)
                model_name = "gemini-3-pro-image-preview"

                parts = []

                # ORNAMENT (main subject)
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_b64
                    }
                })
                parts.append(
                    {"text": "This is the ornament whose background must be changed."})

                # BACKGROUND IMAGE (highest priority)
                if bg_b64:
                    parts.append({
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": bg_b64
                        }
                    })
                    parts.append(
                        {"text": "Use this image strictly as the new background."})

                # PROMPT LAST (important for Gemini)
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
                generated_bytes = None

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
                # -----------------------------
                # FALLBACK — PIL background changer
                # -----------------------------
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

            # -----------------------------
            # SAVE GENERATED IMAGE LOCALLY
            # -----------------------------
            gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
            os.makedirs(gen_dir, exist_ok=True)

            local_generated_path = os.path.join(
                gen_dir, f"generated_{ornament.name}")

            with open(local_generated_path, "wb") as f:
                f.write(generated_bytes)

            # Upload final generated image
            upload_result = cloudinary.uploader.upload(
                local_generated_path,
                folder="ornaments_bg_change",
                public_id=f"ornament_bg_{os.path.splitext(ornament.name)[0]}",
                overwrite=True
            )
            generated_url = upload_result['secure_url']

            # -----------------------------
            # SAVE TO MONGO
            # -----------------------------
            ornament_doc = OrnamentMongo(
                prompt=final_prompt,
                uploaded_image_url=uploaded_url,
                generated_image_url=generated_url,
                uploaded_image_path=local_uploaded_path,
                generated_image_path=local_generated_path,
                type="background_change",
                user_id=user_id,
                original_prompt=prompt
            )
            ornament_doc.save()

            return JsonResponse({
                "success": True,
                "message": "Background changed successfully",
                "uploaded_image_url": uploaded_url,
                "generated_image_url": generated_url,
                "prompt": prompt,
                "mongo_id": str(ornament_doc.id),
                "type": "background_change"
            })

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({"success": False, "error": str(e)})

    else:
        return JsonResponse({"success": False, "error": "Invalid form data"})


@api_view(['POST'])
@csrf_exempt
@authenticate
def generate_model_with_ornament(request):
    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    # === Credit Check and Deduction ===
    from CREDITS.utils import deduct_credits, get_user_organization
    from users.models import Role

    # Credits per image generation: 2 credits for new image generation
    CREDITS_PER_IMAGE = 2

    # Check if user has organization - if not, allow generation without credit deduction
    organization = get_user_organization(user)
    if organization:
        # Check and deduct credits before generation
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Model with ornament image generation",
            metadata={"type": "generate_model_with_ornament"}
        )

        if not credit_result['success']:
            return Response({"error": credit_result['message']}, status=400)
    # If no organization, allow generation to proceed without credit deduction

    try:
        ornament_img = request.FILES.get('ornament_image')
        pose_img = request.FILES.get('pose_style')
        prompt = request.POST.get('prompt', '')
        print(prompt)
        measurements = request.POST.get('measurements', '')
        ornament_type = request.POST.get('ornament_type', '')
        ornament_measurements = request.POST.get(
            'ornament_measurements', '{}')
        dimension = request.POST.get('dimension', '1:1').strip()
        print(ornament_type, ornament_measurements)

        if not ornament_img:
            return Response({"error": "Please upload an ornament image."}, status=400)

        # STEP 1: Save ornament locally
        upload_dir = os.path.join(
            settings.MEDIA_ROOT, "uploaded_ornaments")
        os.makedirs(upload_dir, exist_ok=True)
        local_uploaded_path = os.path.join(upload_dir, ornament_img.name)
        with open(local_uploaded_path, "wb+") as dest:
            for chunk in ornament_img.chunks():
                dest.write(chunk)

        # STEP 2: Upload ornament to Cloudinary
        uploaded_result = cloudinary.uploader.upload(
            local_uploaded_path,
            folder="ornaments_originals",
            public_id=f"ornament_original_{os.path.splitext(ornament_img.name)[0]}",
            overwrite=True
        )
        uploaded_url = uploaded_result["secure_url"]

        # Convert uploaded images to base64
        ornament_b64 = base64.b64encode(
            open(local_uploaded_path, "rb").read()).decode("utf-8")
        pose_b64 = None
        if pose_img:
            pose_b64 = base64.b64encode(pose_img.read()).decode('utf-8')

        if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == 'your_api_key_here':
            raise Exception("GOOGLE_API_KEY not configured")

        generated_bytes = None

        if has_genai:
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            model_name = "gemini-3-pro-image-preview"

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

            # Build ornament type and measurements description
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
            # Add dimension to prompt
            dimension_text = f" Generate the image in {dimension} aspect ratio (width:height)." if dimension else ""
            if dimension and dimension not in user_prompt:
                user_prompt = f"{user_prompt}{dimension_text}"
            print("user_prompt", user_prompt)

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

        # STEP 4: Save generated image locally
        gen_dir = os.path.join(settings.MEDIA_ROOT, "generated_ornaments")
        os.makedirs(gen_dir, exist_ok=True)
        local_generated_path = os.path.join(
            gen_dir, f"generated_{ornament_img.name}")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # STEP 5: Upload generated image to Cloudinary
        upload_result = cloudinary.uploader.upload(
            local_generated_path,
            folder="model_ornament",
            public_id=f"ornament_generated_{os.path.splitext(ornament_img.name)[0]}",
            overwrite=True
        )
        generated_url = upload_result['secure_url']

        # STEP 6: Save to MongoDB
        ornament_doc = OrnamentMongo(
            prompt=user_prompt,
            uploaded_image_url=uploaded_url,
            generated_image_url=generated_url,
            uploaded_image_path=local_uploaded_path,
            generated_image_path=local_generated_path,
            type="model_with_ornament",
            user_id=user_id,
            original_prompt=prompt
        )
        ornament_doc.save()

        return JsonResponse({
            "status": "success",
            "message": "Generated AI close-up model wearing ornament successfully.",
            "prompt": prompt,
            "measurements": measurements,
            "uploaded_image_url": uploaded_url,
            "generated_image_url": generated_url,
            "mongo_id": str(ornament_doc.id),
            "type": "model_with_ornament"
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


# Assuming OrnamentMongo is imported
# from your_app.models import OrnamentMongo


@api_view(['POST'])
@csrf_exempt
@authenticate
def generate_real_model_with_ornament(request):
    """
    Generate an AI image of a real uploaded model wearing the uploaded ornament.
    Ensures output is realistic, jewelry-focused, and high-quality.
    """
    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    # === Credit Check and Deduction ===
    from CREDITS.utils import deduct_credits, get_user_organization
    from users.models import Role

    # Credits per image generation: 2 credits for new image generation
    CREDITS_PER_IMAGE = 2

    # Check if user has organization - if not, allow generation without credit deduction
    organization = get_user_organization(user)
    if organization:
        # Check and deduct credits before generation
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Real model with ornament image generation",
            metadata={"type": "generate_real_model_with_ornament"}
        )

        if not credit_result['success']:
            return Response({"error": credit_result['message']}, status=400)
    # If no organization, allow generation to proceed without credit deduction

    try:
        model_img = request.FILES.get('model_image')
        ornament_img = request.FILES.get('ornament_image')
        pose_img = request.FILES.get('pose_style')
        prompt = request.POST.get('prompt', '')
        measurements = request.POST.get('measurements', '')
        ornament_type = request.POST.get('ornament_type', '')
        ornament_measurements = request.POST.get(
            'ornament_measurements', '{}')
        dimension = request.POST.get('dimension', '1:1').strip()

        if not model_img or not ornament_img:
            return Response({"error": "Please upload both model and ornament images."}, status=400)

        # === STEP 1: Save images locally ===
        model_dir = os.path.join(settings.MEDIA_ROOT, "uploaded_models")
        ornament_dir = os.path.join(
            settings.MEDIA_ROOT, "uploaded_ornaments")
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(ornament_dir, exist_ok=True)

        local_model_path = os.path.join(model_dir, model_img.name)
        local_ornament_path = os.path.join(ornament_dir, ornament_img.name)

        # Save model image locally
        with open(local_model_path, "wb+") as dest:
            for chunk in model_img.chunks():
                dest.write(chunk)

        # Save ornament image locally
        with open(local_ornament_path, "wb+") as dest:
            for chunk in ornament_img.chunks():
                dest.write(chunk)

        # === STEP 2: Upload both to Cloudinary ===
        model_upload = cloudinary.uploader.upload(
            local_model_path,
            folder="models_originals",
            public_id=f"model_original_{os.path.splitext(model_img.name)[0]}",
            overwrite=True
        )
        ornament_upload = cloudinary.uploader.upload(
            local_ornament_path,
            folder="ornaments_originals",
            public_id=f"ornament_original_{os.path.splitext(ornament_img.name)[0]}",
            overwrite=True
        )

        model_url = model_upload["secure_url"]
        ornament_url = ornament_upload["secure_url"]

        # === STEP 3: Prepare images for AI model (Base64) ===
        model_b64 = base64.b64encode(
            open(local_model_path, "rb").read()).decode("utf-8")
        ornament_b64 = base64.b64encode(
            open(local_ornament_path, "rb").read()).decode("utf-8")
        pose_b64 = base64.b64encode(pose_img.read()).decode(
            "utf-8") if pose_img else None

        if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == 'your_api_key_here':
            raise Exception("GOOGLE_API_KEY not configured")

        generated_bytes = None

        # === STEP 4: Generate AI image ===
        if has_genai:
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            model_name = "gemini-3-pro-image-preview"

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

            # Build ornament type and measurements description
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
            # Add dimension to prompt
            dimension_text = f" Generate the image in {dimension} aspect ratio (width:height)." if dimension else ""
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

        # === STEP 5: Save generated image locally ===
        generated_dir = os.path.join(
            settings.MEDIA_ROOT, "generated_models")
        os.makedirs(generated_dir, exist_ok=True)
        local_generated_path = os.path.join(
            generated_dir, f"generated_{model_img.name}")

        with open(local_generated_path, "wb") as f:
            f.write(generated_bytes)

        # === STEP 6: Upload generated image to Cloudinary ===
        upload_result = cloudinary.uploader.upload(
            local_generated_path,
            folder="real_model_output",
            public_id=f"model_generated_{os.path.splitext(model_img.name)[0]}",
            overwrite=True
        )
        generated_url = upload_result["secure_url"]

        # === STEP 7: Save to MongoDB ===
        ornament_doc = OrnamentMongo(
            prompt=user_prompt,
            model_image_url=model_url,  # main input model image
            uploaded_image_url=ornament_url,  # optionally add this field in your model
            generated_image_url=generated_url,
            uploaded_image_path=local_model_path,
            generated_image_path=local_generated_path,
            type="real_model_with_ornament",
            user_id=user_id,
            original_prompt=prompt
        )
        ornament_doc.save()

        # === STEP 8: Return response ===
        return JsonResponse({
            "status": "success",
            "message": "Generated AI image of the model wearing ornament successfully.",
            "prompt": prompt,
            "measurements": measurements,
            "model_image_url": model_url,
            "ornament_image_url": ornament_url,
            "generated_image_url": generated_url,
            "mongo_id": str(ornament_doc.id),
            "type": "real_model_with_ornament"
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def generate_campaign_shot_advanced(request):
    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    try:
        # === Credit Check and Deduction ===
        from CREDITS.utils import deduct_credits, get_user_organization
        from users.models import Role

        # Credits per image generation: 2 credits for new image generation
        CREDITS_PER_IMAGE = 2

        # Check if user has organization - if not, allow generation without credit deduction
        organization = get_user_organization(user)
        if organization:
            # Check and deduct credits before generation
            credit_result = deduct_credits(
                organization=organization,
                user=user,
                amount=CREDITS_PER_IMAGE,
                reason="Campaign shot image generation",
                metadata={"type": "campaign_shot_advanced",
                          "model_type": request.POST.get('model_type', 'ai')}
            )

            if not credit_result['success']:
                return Response({"error": credit_result['message']}, status=400)
        # If no organization, allow generation to proceed without credit deduction

        model_type = request.POST.get('model_type')
        model_img = request.FILES.get(
            'model_image') if model_type == 'real_model' else None
        ornaments = request.FILES.getlist('ornament_images')
        ornament_names = request.POST.getlist('ornament_names')
        theme_images = request.FILES.getlist('theme_images')
        prompt = request.POST.get('prompt', '')
        dimension = request.POST.get('dimension', '1:1').strip()

        # === Validation ===
        if not ornaments:
            return Response({"error": "Please upload at least one ornament image."}, status=400)
        if model_type == 'real_model' and not model_img:
            return Response({"error": "Please upload a model image for Real Model option."}, status=400)

        # === Upload ornaments to Cloudinary & encode ===
        ornament_urls = []
        ornament_b64_list = []
        for idx, ornament in enumerate(ornaments):
            ornament_bytes = ornament.read()
            ornament.seek(0)

            # Upload
            result = cloudinary.uploader.upload(
                ornament, folder="ornaments", overwrite=True)
            ornament_urls.append(result['secure_url'])

            # Encode
            ornament_name = ornament_names[idx] if idx < len(
                ornament_names) else f"Ornament {idx+1}"
            ornament_b64_list.append({
                "name": ornament_name,
                "data": base64.b64encode(ornament_bytes).decode('utf-8')
            })

        # === Model upload & encoding ===
        model_url = None
        model_b64 = None
        if model_img:
            model_bytes = model_img.read()
            model_img.seek(0)
            model_upload = cloudinary.uploader.upload(
                model_img, folder="models", overwrite=True)
            model_url = model_upload['secure_url']
            model_b64 = base64.b64encode(model_bytes).decode('utf-8')

        # === Theme images encoding ===
        theme_b64_list = []
        for theme in theme_images:
            theme_bytes = theme.read()
            theme.seek(0)
            theme_b64_list.append(base64.b64encode(
                theme_bytes).decode('utf-8'))

        # === Check Gemini configuration ===
        if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == 'your_api_key_here':
            raise Exception("GOOGLE_API_KEY not configured")
        if not has_genai:
            raise Exception(
                "Gemini SDK not available. Please install or configure it.")

        # === Build Gemini request ===
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = "gemini-3-pro-image-preview"

        # Build parts array
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
        # Add dimension to prompt
        dimension_text = f" Generate the image in {dimension} aspect ratio (width:height)." if dimension else ""
        if dimension and dimension not in user_prompt:
            user_prompt = f"{user_prompt}{dimension_text}"
        print("user_prompt : ", user_prompt)

        parts.append({"text": user_prompt})

        # Wrap parts in contents array
        contents = [{"parts": parts}]

        config = types.GenerateContentConfig(
            response_modalities=[types.Modality.IMAGE]
        )

        # === Generate via Gemini ===
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

        # === Upload generated image ===
        buf = BytesIO(generated_bytes)
        buf.seek(0)
        upload_result = cloudinary.uploader.upload(
            buf, folder="campaign_shots", overwrite=True)
        generated_url = upload_result['secure_url']

        # === Save record to MongoDB ===
        ornament_doc = OrnamentMongo(
            prompt=prompt,
            type="campaign_shot_advanced",
            model_image_url=model_url,
            uploaded_ornament_urls=ornament_urls,
            generated_image_url=generated_url,
            uploaded_image_path="Multiple ornaments",
            generated_image_path=f"media/generated/campaign_{len(ornaments)}.jpg",
            user_id=user_id,
            original_prompt=prompt
        )
        ornament_doc.save()

        return JsonResponse({
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
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

# @csrf_exempt
# @authenticate
# def generate_campaign_shot_advanced(request):
#     if request.method != 'POST':
#         return JsonResponse({"error": "Invalid request method. Use POST."}, status=405)

#     user = request.user
#     user_id = str(user.id)

#     try:
#         # ==========================
#         # INPUT EXTRACTION
#         # ==========================
#         model_type = request.POST.get('model_type')
#         model_img = request.FILES.get(
#             'model_image') if model_type == 'real_model' else None
#         ornaments = request.FILES.getlist('ornament_images')
#         ornament_names = request.POST.getlist('ornament_names')
#         theme_images = request.FILES.getlist('theme_images')
#         prompt = request.POST.get('prompt', '')

#         # ==========================
#         # VALIDATION
#         # ==========================
#         if not ornaments:
#             return JsonResponse({"error": "Please upload at least one ornament image."}, status=400)
#         if model_type == 'real_model' and not model_img:
#             return JsonResponse({"error": "Please upload a model image for Real Model option."}, status=400)

#         # ==========================
#         # ORNAMENT UPLOAD + ENCODE
#         # ==========================
#         ornament_urls = []
#         ornament_b64_list = []

#         for idx, ornament in enumerate(ornaments):
#             bytes_data = ornament.read()
#             ornament.seek(0)

#             upload = cloudinary.uploader.upload(
#                 ornament,
#                 folder="ornaments",
#                 overwrite=True
#             )

#             ornament_urls.append(upload["secure_url"])

#             name = ornament_names[idx] if idx < len(
#                 ornament_names) else f"Ornament {idx+1}"
#             ornament_b64_list.append({
#                 "name": name,
#                 "data": base64.b64encode(bytes_data).decode("utf-8")
#             })

#         # ==========================
#         # MODEL UPLOAD + ENCODE
#         # ==========================
#         model_url = None
#         model_b64 = None

#         if model_img:
#             model_bytes = model_img.read()
#             model_img.seek(0)

#             upload_model = cloudinary.uploader.upload(
#                 model_img,
#                 folder="models",
#                 overwrite=True
#             )
#             model_url = upload_model["secure_url"]
#             model_b64 = base64.b64encode(model_bytes).decode("utf-8")

#         # ==========================
#         # THEME ENCODE
#         # ==========================
#         theme_b64_list = []
#         for theme in theme_images:
#             t_bytes = theme.read()
#             theme.seek(0)
#             theme_b64_list.append(base64.b64encode(t_bytes).decode("utf-8"))

#         # ==========================
#         # GEMINI SETUP
#         # ==========================
#         if not settings.GOOGLE_API_KEY:
#             raise Exception("GOOGLE_API_KEY not configured")

#         if not has_genai:
#             raise Exception("Gemini SDK not installed")

#         client = genai.Client(api_key=settings.GOOGLE_API_KEY)
#         model_name = "gemini-3-pro-image-preview"

#         parts = []

#         # Model
#         if model_b64:
#             parts.append(
#                 {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}})
#             parts.append({"text": "Reference for the real model."})

#         # Ornaments
#         for orn in ornament_b64_list:
#             parts.append(
#                 {"inline_data": {"mime_type": "image/jpeg", "data": orn["data"]}})
#             parts.append({"text": f"Reference for ornament: {orn['name']}"})

#         # Themes
#         for t in theme_b64_list:
#             parts.append(
#                 {"inline_data": {"mime_type": "image/jpeg", "data": t}})
#             parts.append(
#                 {"text": "Reference for background or theme styling."})

#         # Prompt builder
#         from probackendapp.prompt_initializer import get_prompt_from_db

#         if model_type == "real_model":
#             default_prompt = (
#                 "Generate a realistic image of the uploaded real model wearing all the uploaded ornaments. "
#                 "Preserve the model’s face and natural pose. Make a subtle smile. "
#                 f"Campaign instructions: {prompt}"
#             )
#             final_prompt = get_prompt_from_db(
#                 "images_campaign_shot_real", default_prompt, user_prompt=prompt)
#         else:
#             default_prompt = (
#                 "Generate a high-quality campaign image of an AI model wearing the uploaded ornaments. "
#                 "Use realistic lighting and cohesive fashion aesthetics. "
#                 f"Campaign instructions: {prompt}"
#             )
#             final_prompt = get_prompt_from_db(
#                 "images_campaign_shot_ai", default_prompt, user_prompt=prompt)

#         parts.append({"text": final_prompt})

#         contents = [{"parts": parts}]

#         config = types.GenerateContentConfig(
#             response_modalities=[types.Modality.IMAGE]
#         )

#         # ==========================
#         # GEMINI IMAGE GENERATION
#         # ==========================
#         resp = client.models.generate_content(
#             model=model_name, contents=contents, config=config
#         )

#         candidate = resp.candidates[0]

#         generated_bytes = None
#         for part in candidate.content.parts:
#             if getattr(part, "inline_data", None):
#                 raw = part.inline_data.data
#                 generated_bytes = raw if isinstance(
#                     raw, bytes) else base64.b64decode(raw)
#                 break

#         if not generated_bytes:
#             raise Exception("No image returned from Gemini")

#         # ==========================
#         # CLOUDINARY ENHANCEMENT (SIGNED URL)
#         # ==========================
#         buf = BytesIO(generated_bytes)
#         buf.seek(0)

#         upload_raw = cloudinary.uploader.upload(
#             buf,
#             folder="campaign_shots/original",
#             overwrite=True,
#             resource_type="image"
#         )

#         public_id = upload_raw["public_id"]

#         # Build final enhanced URL (SIGNED)
#         generated_url = cloudinary.CloudinaryImage(public_id).build_url(
#             transformation=[
#                 {"quality": "auto:best"},
#                 {"fetch_format": "auto"},
#                 {"effect": "sharpen:50"},
#                 {"crop": "limit", "width": 2400}
#             ],
#             sign_url=True
#         )

#         # ==========================
#         # SAVE TO MONGODB
#         # ==========================
#         ornament_doc = OrnamentMongo(
#             prompt=prompt,
#             type="campaign_shot_advanced",
#             model_image_url=model_url,
#             uploaded_ornament_urls=ornament_urls,
#             generated_image_url=generated_url,
#             uploaded_image_path="Multiple ornaments",
#             generated_image_path=f"media/generated/campaign_{len(ornaments)}.jpg",
#             user_id=user_id,
#             original_prompt=prompt
#         )
#         ornament_doc.save()

#         # ==========================
#         # RESPONSE
#         # ==========================
#         return JsonResponse({
#             "status": "success",
#             "message": "Campaign shot generated and enhanced successfully.",
#             "generated_image_url": generated_url,
#             "model_image_url": model_url,
#             "uploaded_ornament_urls": ornament_urls,
#             "prompt": prompt,
#             "mongo_id": str(ornament_doc.id),
#             "type": "campaign_shot_advanced"
#         }, status=200)

#     except Exception as e:
#         traceback.print_exc()
#         return JsonResponse({"status": "error", "message": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def regenerate_image(request):
    """
    Regenerate an image from a previously generated image.
    Works for all image types. Combines the original prompt with the new prompt.
    Stores the regenerated image in the same collection with parent_image_id reference.
    """

    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    # === Credit Check and Deduction ===
    from CREDITS.utils import deduct_credits, get_user_organization
    from users.models import Role

    # Credits per image regeneration: 1 credit for regenerating an existing image
    CREDITS_PER_REGENERATION = 1

    # Check if user has organization - if not, allow generation without credit deduction
    organization = get_user_organization(user)
    if organization:
        # Check and deduct credits before regeneration
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_REGENERATION,
            reason="Image regeneration",
            metadata={"type": "regenerate_image"}
        )

        if not credit_result['success']:
            return Response({"error": credit_result['message']}, status=400)
    # If no organization, allow generation to proceed without credit deduction

    try:
        # Get parameters
        # MongoDB ID of the image to regenerate
        image_id = request.POST.get('image_id')
        new_prompt = request.POST.get('prompt', '').strip()
        print(new_prompt)

        if not image_id:
            return Response({"error": "image_id is required"}, status=400)

        if not new_prompt:
            return Response({"error": "New prompt is required"}, status=400)

        # Validate MongoDB ObjectId format before attempting to use it
        # ObjectId must be exactly 24 hex characters
        object_id_pattern = re.compile(r'^[0-9a-fA-F]{24}$')
        if not object_id_pattern.match(image_id):
            return JsonResponse({
                "error": f"Invalid image_id: '{image_id}' is not a valid MongoDB ObjectId. It must be a 24-character hex string. Please ensure you are using mongo_id, not ornament_id."
            }, status=400)

        # Fetch the previous image record from MongoDB
        try:
            prev_doc = OrnamentMongo.objects.get(id=ObjectId(image_id))
        except OrnamentMongo.DoesNotExist:
            return JsonResponse({"error": "Image record not found"}, status=404)
        except Exception as e:
            # This should rarely happen now due to format validation above
            return Response({"error": f"Invalid image_id: {str(e)}"}, status=400)

        # Verify that the image belongs to the user (security check)
        if prev_doc.user_id != user_id:
            return JsonResponse({"error": "You don't have permission to regenerate this image"}, status=403)

        # Get the previous generated image URL from Cloudinary
        prev_generated_url = prev_doc.generated_image_url

        # Combine the original prompt with the new prompt
        original_prompt = prev_doc.original_prompt or prev_doc.prompt
        combined_prompt = f"{original_prompt}. {new_prompt}"
        print("combined_prompt", combined_prompt)

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
            model_name = "gemini-3-pro-image-preview"

            contents = [
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                {"text": combined_prompt}
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
            type=prev_doc.type,  # Keep the same type
            user_id=user_id,
            parent_image_id=ObjectId(image_id),  # Reference to parent
            original_prompt=original_prompt,  # Keep the original prompt
            uploaded_image_url=prev_doc.uploaded_image_url,  # Same uploaded image
            generated_image_url=regenerated_url,  # New generated URL
            uploaded_image_path=prev_doc.uploaded_image_path,  # Same uploaded path
            generated_image_path=local_regen_path,  # New local path
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

        return JsonResponse({
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
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@authenticate
def get_user_images(request):
    """
    Fetch all images generated by the authenticated user.
    Supports filtering by type and pagination.
    """
    if request.method != 'GET':
        return JsonResponse({"error": "Invalid request method. Use GET."}, status=405)

    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    try:
        # Get query parameters
        image_type = request.GET.get('type', None)  # Optional filter by type
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))

        # Build query
        query = {"user_id": user_id}
        if image_type:
            query["type"] = image_type

        # Fetch images from MongoDB with pagination
        skip = (page - 1) * limit
        images = OrnamentMongo.objects(
            **query).order_by('-created_at').skip(skip).limit(limit)
        total_count = OrnamentMongo.objects(**query).count()

        # Convert to list of dictionaries
        images_list = []
        for img in images:
            img_dict = {
                "id": str(img.id),
                "prompt": img.prompt,
                "type": img.type,
                "uploaded_image_url": img.uploaded_image_url,
                "generated_image_url": img.generated_image_url,
                "created_at": img.created_at.isoformat() if img.created_at else None,
                "parent_image_id": str(img.parent_image_id) if img.parent_image_id else None,
                "original_prompt": img.original_prompt,
            }

            # Add optional fields if they exist
            if hasattr(img, 'model_image_url') and img.model_image_url:
                img_dict["model_image_url"] = img.model_image_url
            if hasattr(img, 'uploaded_ornament_urls') and img.uploaded_ornament_urls:
                img_dict["uploaded_ornament_urls"] = img.uploaded_ornament_urls

            images_list.append(img_dict)

        return JsonResponse({
            "success": True,
            "images": images_list,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit
            }
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)
