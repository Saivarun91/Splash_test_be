

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
from common.user_friendly_errors import get_user_friendly_message
from urllib.request import urlopen
from bson import ObjectId
import re
from .tasks import (
    generate_white_background_task,
    change_background_task,
    generate_model_with_ornament_task,
    generate_real_model_with_ornament_task,
    generate_campaign_shot_advanced_task,
    regenerate_image_task
)

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

            # Call Celery task asynchronously
            task = generate_white_background_task.delay(
                ornament_id=ornament.id,
                user_id=user_id,
                bg_color=bg_color,
                extra_prompt=extra_prompt,
                dimension=dimension
            )

            return JsonResponse({
                "success": True,
                "message": "Image generation task started",
                "task_id": task.id,
                "ornament_id": ornament.id,
                "status": "processing"
            })

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({"success": False, "error": get_user_friendly_message(e)})

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
    from CREDITS.utils import (
        deduct_credits,
        get_user_organization,
        get_credit_settings,
        deduct_user_credits,
    )

    # Use admin-configured credits per image
    credit_settings = get_credit_settings()
    CREDITS_PER_IMAGE = credit_settings["credits_per_image_generation"]

    # Check if user has organization; if not, fall back to individual credits
    organization = get_user_organization(user)
    if organization:
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Background change image generation",
            metadata={"type": "change_background"},
        )
    else:
        credit_result = deduct_user_credits(
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Background change image generation",
            metadata={"type": "change_background"},
        )

    if not credit_result["success"]:
        return Response(
            print("insufficient credits pls recharge",credit_result["message"]),
            {"error": credit_result["message"]},
            status=400,
        )

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

            # -----------------------------
            # SAVE BACKGROUND IMAGE LOCALLY (if provided)
            # -----------------------------
            background_image_path = None
            if background:
                bg_dir = os.path.join(settings.MEDIA_ROOT, "uploaded_backgrounds")
                os.makedirs(bg_dir, exist_ok=True)
                background_image_path = os.path.join(bg_dir, background.name)
                with open(background_image_path, "wb+") as dest:
                    for chunk in background.chunks():
                        dest.write(chunk)

            # Call Celery task asynchronously
            task = change_background_task.delay(
                uploaded_image_path=local_uploaded_path,
                user_id=user_id,
                bg_color=bg_color,
                background_image_path=background_image_path,
                prompt=prompt,
                dimension=dimension
            )

            return JsonResponse({
                "success": True,
                "message": "Background change task started",
                "task_id": task.id,
                "status": "processing"
            })

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({"success": False, "error": get_user_friendly_message(e)})

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
    from CREDITS.utils import (
        deduct_credits,
        get_user_organization,
        get_credit_settings,
        deduct_user_credits,
    )

    credit_settings = get_credit_settings()
    CREDITS_PER_IMAGE = credit_settings["credits_per_image_generation"]

    organization = get_user_organization(user)
    if organization:
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Model with ornament image generation",
            metadata={"type": "generate_model_with_ornament"},
        )
    else:
        credit_result = deduct_user_credits(
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Model with ornament image generation",
            metadata={"type": "generate_model_with_ornament"},
        )

    if not credit_result["success"]:
        return Response(
            print("insufficient credits pls recharge",e),
            {"error": "insufficient credits pls recharge"},
            status=400,
        )

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

        # STEP 2: Save pose image locally (if provided)
        pose_image_path = None
        if pose_img:
            pose_dir = os.path.join(settings.MEDIA_ROOT, "uploaded_poses")
            os.makedirs(pose_dir, exist_ok=True)
            pose_image_path = os.path.join(pose_dir, pose_img.name)
            with open(pose_image_path, "wb+") as dest:
                for chunk in pose_img.chunks():
                    dest.write(chunk)

        # Call Celery task asynchronously
        task = generate_model_with_ornament_task.delay(
            ornament_image_path=local_uploaded_path,
            user_id=user_id,
            pose_image_path=pose_image_path,
            prompt=prompt,
            measurements=measurements,
            ornament_type=ornament_type,
            ornament_measurements=ornament_measurements,
            dimension=dimension
        )

        return JsonResponse({
            "status": "success",
            "message": "Model with ornament generation task started",
            "task_id": task.id,
            "status": "processing"
        }, status=200)

        

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": get_user_friendly_message(e)}, status=500)



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
    from CREDITS.utils import (
        deduct_credits,
        get_user_organization,
        get_credit_settings,
        deduct_user_credits,
    )

    credit_settings = get_credit_settings()
    CREDITS_PER_IMAGE = credit_settings["credits_per_image_generation"]

    organization = get_user_organization(user)
    if organization:
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Real model with ornament image generation",
            metadata={"type": "generate_real_model_with_ornament"},
        )
    else:
        credit_result = deduct_user_credits(
            user=user,
            amount=CREDITS_PER_IMAGE,
            reason="Real model with ornament image generation",
            metadata={"type": "generate_real_model_with_ornament"},
        )

    if not credit_result["success"]:
        return Response(
            {"error": "insufficient credits pls recharge"},
            status=400,
        )

    try:
        model_img = request.FILES.get('model_image')
        ornament_img = request.FILES.get('ornament_image')
        pose_img = request.FILES.get('pose_style')
        prompt = request.POST.get('prompt', '')
        print("prompt from request : ", prompt)
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

        # Save pose image locally (if provided)
        pose_image_path = None
        if pose_img:
            pose_dir = os.path.join(settings.MEDIA_ROOT, "uploaded_poses")
            os.makedirs(pose_dir, exist_ok=True)
            pose_image_path = os.path.join(pose_dir, pose_img.name)
            with open(pose_image_path, "wb+") as dest:
                for chunk in pose_img.chunks():
                    dest.write(chunk)

        # Call Celery task asynchronously
        task = generate_real_model_with_ornament_task.delay(
            model_image_path=local_model_path,
            ornament_image_path=local_ornament_path,
            user_id=user_id,
            pose_image_path=pose_image_path,
            prompt=prompt,
            measurements=measurements,
            ornament_type=ornament_type,
            ornament_measurements=ornament_measurements,
            dimension=dimension
        )

        return JsonResponse({
            "status": "success",
            "message": "Real model with ornament generation task started",
            "task_id": task.id,
            "status": "processing"
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": get_user_friendly_message(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def generate_campaign_shot_advanced(request):
    # Get user from authentication middleware
    user = request.user
    user_id = str(user.id)

    try:
        # === Credit Check and Deduction ===
        from CREDITS.utils import (
            deduct_credits,
            get_user_organization,
            get_credit_settings,
            deduct_user_credits,
        )

        credit_settings = get_credit_settings()
        CREDITS_PER_IMAGE = credit_settings["credits_per_image_generation"]

        organization = get_user_organization(user)
        if organization:
            credit_result = deduct_credits(
                organization=organization,
                user=user,
                amount=CREDITS_PER_IMAGE,
                reason="Campaign shot image generation",
                metadata={
                    "type": "campaign_shot_advanced",
                    "model_type": request.POST.get("model_type", "ai"),
                },
            )
        else:
            credit_result = deduct_user_credits(
                user=user,
                amount=CREDITS_PER_IMAGE,
                reason="Campaign shot image generation",
                metadata={
                    "type": "campaign_shot_advanced",
                    "model_type": request.POST.get("model_type", "ai"),
                },
            )

        if not credit_result["success"]:
            return Response(
                {"error": "insufficient credits pls recharge"},
                status=400,
            )

        model_type = request.POST.get('model_type')
        model_img = request.FILES.get(
            'model_image') if model_type == 'real_model' else None
        ornaments = request.FILES.getlist('ornament_images')
        ornament_names = request.POST.getlist('ornament_names')
        theme_images = request.FILES.getlist('theme_images')
        prompt = request.POST.get('prompt')
        dimension = request.POST.get('dimension', '1:1').strip()

        # === Validation ===
        if not ornaments:
            return Response({"error": "Please upload at least one ornament image."}, status=400)
        if model_type == 'real_model' and not model_img:
            return Response({"error": "Please upload a model image for Real Model option."}, status=400)

        # === Save ornaments locally ===
        ornament_dir = os.path.join(settings.MEDIA_ROOT, "uploaded_ornaments")
        os.makedirs(ornament_dir, exist_ok=True)
        ornament_image_paths = []
        for idx, ornament in enumerate(ornaments):
            ornament_path = os.path.join(ornament_dir, ornament.name)
            with open(ornament_path, "wb+") as dest:
                for chunk in ornament.chunks():
                    dest.write(chunk)
            ornament_image_paths.append(ornament_path)

        # === Save model image locally (if provided) ===
        model_image_path = None
        if model_img:
            model_dir = os.path.join(settings.MEDIA_ROOT, "uploaded_models")
            os.makedirs(model_dir, exist_ok=True)
            model_image_path = os.path.join(model_dir, model_img.name)
            with open(model_image_path, "wb+") as dest:
                for chunk in model_img.chunks():
                    dest.write(chunk)

        # === Save theme images locally ===
        theme_dir = os.path.join(settings.MEDIA_ROOT, "uploaded_themes")
        os.makedirs(theme_dir, exist_ok=True)
        theme_image_paths = []
        for theme in theme_images:
            theme_path = os.path.join(theme_dir, theme.name)
            with open(theme_path, "wb+") as dest:
                for chunk in theme.chunks():
                    dest.write(chunk)
            theme_image_paths.append(theme_path)

        # Call Celery task asynchronously
        task = generate_campaign_shot_advanced_task.delay(
            user_id=user_id,
            model_type=model_type,
            model_image_path=model_image_path,
            ornament_image_paths=ornament_image_paths,
            ornament_names=ornament_names,
            theme_image_paths=theme_image_paths,
            prompt=prompt,
            dimension=dimension
        )

        return JsonResponse({
            "status": "success",
            "message": "Campaign shot generation task started",
            "task_id": task.id,
            "status": "processing"
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": get_user_friendly_message(e)}, status=500)

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
#         return JsonResponse({"status": "error", "message": get_user_friendly_message(e)}, status=500)


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
    from CREDITS.utils import (
        deduct_credits,
        get_user_organization,
        get_credit_settings,
        deduct_user_credits,
    )

    credit_settings = get_credit_settings()
    CREDITS_PER_REGENERATION = credit_settings["credits_per_regeneration"]

    organization = get_user_organization(user)
    if organization:
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=CREDITS_PER_REGENERATION,
            reason="Image regeneration",
            metadata={"type": "regenerate_image"},
        )
    else:
        credit_result = deduct_user_credits(
            user=user,
            amount=CREDITS_PER_REGENERATION,
            reason="Image regeneration",
            metadata={"type": "regenerate_image"},
        )

    if not credit_result["success"]:
        return Response(
            {"error": "insufficient credits pls recharge"},
            status=400,
        )

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
                "error": get_user_friendly_message("Invalid image_id"),
            }, status=400)

        # Fetch the previous image record from MongoDB
        try:
            prev_doc = OrnamentMongo.objects.get(id=ObjectId(image_id))
        except OrnamentMongo.DoesNotExist:
            return JsonResponse({"error": "Image record not found"}, status=404)
        except Exception as e:
            # This should rarely happen now due to format validation above
            return Response({"error": get_user_friendly_message(e)}, status=400)

        # Verify that the image belongs to the user (security check)
        if prev_doc.user_id != user_id:
            return JsonResponse({"error": "You don't have permission to regenerate this image"}, status=403)

        # Call Celery task asynchronously
        task = regenerate_image_task.delay(
            image_id=image_id,
            user_id=user_id,
            new_prompt=new_prompt
        )

        return JsonResponse({
            "success": True,
            "message": "Image regeneration task started",
            "task_id": task.id,
            "image_id": image_id,
            "status": "processing"
        }, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"success": False, "error": get_user_friendly_message(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def get_task_status(request):
    """Get the status of a Celery task"""
    try:
        from celery.result import AsyncResult
        
        task_id = request.GET.get('task_id')
        if not task_id:
            return JsonResponse({"success": False, "error": "Task ID is required."}, status=400)
        
        result = AsyncResult(task_id)
        
        response_data = {
            "task_id": task_id,
            "status": result.status,
        }
        
        # If task is complete, include the result
        if result.ready():
            if result.successful():
                response_data["result"] = result.result
                response_data["success"] = True
            else:
                # Prefer user-friendly message from task result
                raw = result.result
                if isinstance(raw, dict):
                    err_msg = raw.get("user_friendly_message") or get_user_friendly_message(
                        raw.get("error") or raw.get("message") or str(raw)
                    )
                else:
                    err_msg = get_user_friendly_message(str(raw) if raw else "Task failed")
                response_data["error"] = err_msg
                response_data["success"] = False
        else:
            # Task is still running
            response_data["success"] = None  # In progress
        
        return JsonResponse(response_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "success": False,
            "error": get_user_friendly_message(e),
        }, status=500)


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
        return JsonResponse({"success": False, "error": get_user_friendly_message(e)}, status=500)


@csrf_exempt
@authenticate
def delete_user_image(request, image_id):
    """
    Delete a single image generated by the authenticated user.
    """
    if request.method != 'DELETE':
        return JsonResponse(
            {"error": "Invalid request method. Use DELETE."},
            status=405
        )

    user = request.user
    user_id = str(user.id)

    try:
        # Find image belonging to the user
        image = OrnamentMongo.objects(
            id=image_id,
            user_id=user_id
        ).first()

        if not image:
            return JsonResponse(
                {"success": False, "error": "Image not found or not authorized"},
                status=404
            )

        # OPTIONAL: delete files from storage (S3 / Cloudinary / local)
        # delete_file(image.generated_image_url)
        # delete_file(image.uploaded_image_url)

        image.delete()

        return JsonResponse(
            {"success": True, "message": "Image deleted successfully"},
            status=200
        )

    except Exception as e:
        traceback.print_exc()
        return JsonResponse(
            {"success": False, "error": get_user_friendly_message(e)},
            status=500
        )
