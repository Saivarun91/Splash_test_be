from google import genai
from google.genai import types
from .models import Collection, ProductImage  # ✅ ensure ProductImage is imported
import io
import cloudinary.uploader
import traceback
import base64
from .models import Project, Collection, CollectionItem
from django.shortcuts import render, redirect
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import os
import requests
import json
from django.conf import settings
import ast
import re
from datetime import timezone
from .models import Project, Collection, CollectionItem, GeneratedImage
from .utils import request_suggestions
from mongoengine.errors import DoesNotExist
from rest_framework.response import Response
from .utils import request_suggestions, call_gemini_api, parse_gemini_response
from common.middleware import authenticate
# -------------------------
# Dashboard - Shows all projects
# -------------------------


def dashboard(request):
    projects = Project.objects.all()
    return render(request, "probackendapp/dashboard.html", {"projects": projects})

# -------------------------
# Create a new project
# -------------------------


def create_project(request):
    if request.method == "POST":
        name = request.POST.get("name")
        about = request.POST.get("about")
        if name:
            project = Project(name=name, about=about)
            project.save()
            return redirect("probackendapp:project_setup_description", str(project.id))
    return render(request, "probackendapp/create_project.html")

# -------------------------
# Set collection description and get suggestions from Gemini API


def generate_ai_images_page(request, collection_id):
    from .models import Collection
    collection = Collection.objects.get(id=collection_id)
    return render(request, "probackendapp/generate_ai_images.html", {"collection": collection})


# -------------------------


def project_setup_description(request, project_id):
    try:
        project = Project.objects.get(id=project_id)
    except DoesNotExist:
        return redirect("probackendapp:dashboard")

    # Check if a collection already exists for this project
    collection = Collection.objects(project=project).first()

    if request.method == "POST":
        description = request.POST.get("description", "").strip()
        uploaded_image = request.FILES.get("uploaded_image")

        # Create a new collection if not found
        if not collection:
            collection = Collection(project=project)
            item = CollectionItem()
            collection.items.append(item)
        else:
            # Use the first item (or create if missing)
            item = collection.items[0] if collection.items else CollectionItem(
            )
            if not collection.items:
                collection.items.append(item)

        # Update collection description
        collection.description = description

        # Handle uploaded image
        if uploaded_image:
            item.uploaded_theme_images.append(uploaded_image)

        # Generate suggestions (refresh on each submit)
        suggestions = request_suggestions(description, uploaded_image)
        item.suggested_themes = suggestions.get("themes", [])
        item.suggested_backgrounds = suggestions.get("backgrounds", [])
        item.suggested_poses = suggestions.get("poses", [])
        item.suggested_locations = suggestions.get("locations", [])
        item.suggested_colors = suggestions.get("colors", [])

        collection.save()

        return redirect("probackendapp:project_setup_select", str(project.id), str(collection.id))

    # For GET request — show existing description
    existing_description = collection.description if collection else ""

    return render(request, "probackendapp/project_setup_description.html", {
        "project": project,
        "existing_description": existing_description,
        "collection_exists": bool(collection),
        "collection_id": str(collection.id) if collection else None,
    })

# -------------------------
# Step 2: User selects / refines → Generate final moodboard prompts
# -------------------------
# from django.shortcuts import render, redirect
# from django.http import Response
# from mongoengine.errors import DoesNotExist
# import json
# from .models import Project, Collection, CollectionItem
# from .utils import request_suggestions, call_gemini_api
# def project_setup_select(request, project_id, collection_id):
#     try:
#         project = Project.objects.get(id=project_id)
#         collection = Collection.objects.get(id=collection_id, project=project)
#     except DoesNotExist:
#         return redirect("probackendapp:dashboard")

#     # Use first item or create a new one
#     item = collection.items[0] if collection.items else CollectionItem()
#     if not collection.items:
#         collection.items.append(item)
#         collection.save()

#     ai_response = {}
#     detailed_prompt_text = ""
#     ai_json_text = ""  # initialize

#     if request.method == "POST" and request.POST.get("action") == "save":
#         def getlist(name):
#             return request.POST.getlist(name)

#         # Save user selections
#         item.selected_themes = getlist("themes") or []
#         item.selected_backgrounds = getlist("backgrounds") or []
#         item.selected_poses = getlist("poses") or []
#         item.selected_locations = getlist("locations") or []
#         item.selected_colors = getlist("colors") or []

#         # Save uploaded images for each category
#         for category in ["theme", "background", "pose", "location", "color"]:
#             files = request.FILES.getlist(f"uploaded_{category}_images")
#             if files:
#                 getattr(item, f"uploaded_{category}_images").extend(files)

#         # Prepare uploaded images info
#         uploaded_images_info = ""
#         for cat in ["theme", "background", "pose", "location", "color"]:
#             imgs = getattr(item, f"uploaded_{cat}_images")
#             if imgs:
#                 uploaded_images_info += f"{cat.capitalize()} references: {', '.join([str(f) for f in imgs])}\n"

#         # -----------------------------
#         # Build Gemini AI structured prompt
#         # -----------------------------
#         gemini_prompt = f"""
# You are a professional creative AI assistant. Analyze the collection description and user selections carefully and generate structured image generation prompts.

# Collection Description: {collection.description}
# Selected Themes: {', '.join(item.selected_themes) or 'None'}
# Selected Backgrounds: {', '.join(item.selected_backgrounds) or 'None'}
# Selected Poses: {', '.join(item.selected_poses) or 'None'}
# Selected Locations: {', '.join(item.selected_locations) or 'None'}
# Selected Colors: {', '.join(item.selected_colors) or 'None'}
# Uploaded Image References: {uploaded_images_info if uploaded_images_info else 'None'}

# Generate prompts for the following 5 types. Explain each prompt clearly in context of the collection. Respond ONLY in valid JSON:
# {{
#     "white_background": "Prompt for white background images of the ornament, sharp, clean, isolated.",
#     "background_replace": "Prompt for images with themed backgrounds while keeping the ornament identical.",
#     "model_image": "Prompt to generate realistic model wearing the ornament. Model face and body must be accurate. Match selected poses and expressions, photo should focused mainly on the ornament.",
#     "campaign_image": "Prompt for campaign/promotional shots with models wearing ornaments in themed backgrounds, stylish composition.",

# }}
# """

#         # -----------------------------
#         # Call Gemini API and parse result
#         # -----------------------------
#         ai_json_text = call_gemini_api(gemini_prompt)

#         # Use the proper parsing function from utils
#         ai_response = parse_gemini_response(ai_json_text)

#         # Debug logging
#         print("=== Raw Gemini Response ===")
#         print(ai_json_text)
#         print("=== Parsed Response ===")
#         print(ai_response)
#         print("==========================")

#         # If parsing failed or response is empty, provide fallback
#         if not ai_response or "error" in ai_response or not isinstance(ai_response, dict):
#             print("Using fallback prompts due to parsing issues")
#             ai_response = {
#                 "white_background": "Professional product photography with clean white background, studio lighting, sharp focus on ornament details",
#                 "background_replace": "Same ornament with themed background replacement, maintaining product integrity and lighting",
#                 "model_image": "Realistic model wearing the ornament, professional fashion photography, accurate facial features and body proportions,photo should focused mainly on the ornament",
#                 "campaign_image": "Stylish campaign shot with model in themed setting, creative composition, promotional quality",

#             }

#         # Ensure all required keys exist
#         required_keys = ["white_background", "background_replace", "model_image", "campaign_image"]
#         for key in required_keys:
#             if key not in ai_response or not ai_response[key]:
#                 ai_response[key] = f"Generated prompt for {key.replace('_', ' ')} based on your collection theme"

#         # Save prompts in item
#         item.final_moodboard_prompt = gemini_prompt
#         item.moodboard_explanation = ai_json_text
#         item.generated_prompts = ai_response
#         collection.save()


#     # -----------------------------
#     # Prepare context for template
#     # -----------------------------
#     context = {
#     "project": project.name,
#     "collection": collection,  # pass full object so you can use collection.id in template
#     "item": 0,
#     "themes": item.selected_themes or item.suggested_themes,
#     "backgrounds": item.selected_backgrounds or item.suggested_backgrounds,
#     "poses": item.selected_poses or item.suggested_poses,
#     "locations": item.selected_locations or item.suggested_locations,
#     "colors": item.selected_colors or item.suggested_colors,
#     "item_obj": item,
#     "ai_response": ai_response,
#     "detailed_prompt_text": detailed_prompt_text,
#     "generate_ai_url": f"/probackendapp/generate_ai_images/{collection.id}/",  # pass full URL
# }

#     return render(request, "probackendapp/project_setup_select.html", context)


def project_setup_select(request, project_id, collection_id):
    try:
        project = Project.objects.get(id=project_id)
        collection = Collection.objects.get(id=collection_id, project=project)
    except DoesNotExist:
        return redirect("probackendapp:dashboard")

    # Get first item or create a new one if empty
    item = collection.items[0] if collection.items else CollectionItem()
    if not collection.items:
        collection.items.append(item)
        collection.save()

    # Use previously generated prompts if exist
    ai_response = item.generated_prompts or {}
    detailed_prompt_text = item.moodboard_explanation or ""

    if request.method == "POST" and request.POST.get("action") == "save":
        def getlist(name):
            return request.POST.getlist(name)

        # -----------------------------
        # Save selected options
        # -----------------------------
        item.selected_themes = getlist("themes") or []
        item.selected_backgrounds = getlist("backgrounds") or []
        item.selected_poses = getlist("poses") or []
        item.selected_locations = getlist("locations") or []
        item.selected_colors = getlist("colors") or []

        # Save uploaded images for each category
        for category in ["theme", "background", "pose", "location", "color"]:
            files = request.FILES.getlist(f"uploaded_{category}_images")
            if files:
                getattr(item, f"uploaded_{category}_images").extend(files)

        # Prepare uploaded images info for Gemini prompt
        uploaded_images_info = ""
        for cat in ["theme", "background", "pose", "location", "color"]:
            imgs = getattr(item, f"uploaded_{cat}_images")
            if imgs:
                uploaded_images_info += f"{cat.capitalize()} references: {', '.join([str(f) for f in imgs])}\n"

        # -----------------------------
        # Build Gemini AI structured prompt
        # -----------------------------
        gemini_prompt = f"""
You are a professional creative AI assistant. Analyze the collection description and user selections carefully and generate structured image generation prompts.

Collection Description: {collection.description}
Selected Themes: {', '.join(item.selected_themes) or 'None'}
Selected Backgrounds: {', '.join(item.selected_backgrounds) or 'None'}
Selected Poses: {', '.join(item.selected_poses) or 'None'}
Selected Locations: {', '.join(item.selected_locations) or 'None'}
Selected Colors: {', '.join(item.selected_colors) or 'None'}
Uploaded Image References: {uploaded_images_info if uploaded_images_info else 'None'}

Generate prompts for the following 4 types. Respond ONLY in valid JSON:
{{
    "white_background": "Prompt for white background images of the ornament, sharp, clean, isolated.",
    "background_replace": "Prompt for images with themed backgrounds while keeping the ornament identical.",
    "model_image": "Prompt to generate realistic model wearing the ornament. Model face and body must be accurate. Match selected poses and expressions, photo should focused mainly on the ornament.",
    "campaign_image": "Prompt for campaign/promotional shots with models wearing ornaments in themed backgrounds, stylish composition."
}}
"""

        # -----------------------------
        # Call Gemini API and parse result
        # -----------------------------
        ai_json_text = call_gemini_api(gemini_prompt)
        ai_response = parse_gemini_response(ai_json_text)

        # Fallback if parsing failed
        if not ai_response or "error" in ai_response or not isinstance(ai_response, dict):
            ai_response = {
                "white_background": "Professional product photography with clean white background, studio lighting, sharp focus on ornament details",
                "background_replace": "Same ornament with themed background replacement, maintaining product integrity and lighting",
                "model_image": "Realistic model wearing the ornament, professional fashion photography, accurate facial features and body proportions, photo focused mainly on the ornament",
                "campaign_image": "Stylish campaign shot with model in themed setting, creative composition, promotional quality",
            }

        # Ensure all keys exist
        for key in ["white_background", "background_replace", "model_image", "campaign_image"]:
            if key not in ai_response or not ai_response[key]:
                ai_response[key] = f"Generated prompt for {key.replace('_', ' ')} based on your collection theme"

        # Save prompts in item
        item.final_moodboard_prompt = gemini_prompt
        item.moodboard_explanation = ai_json_text
        item.generated_prompts = ai_response
        collection.save()

        # Refresh detailed_prompt_text to show in template
        detailed_prompt_text = ai_json_text

    # -----------------------------
    # Prepare context for template
    # -----------------------------
    # context = {
    #     "project": project.name,
    #     "collection": collection,  # full object for template
    #     "item_obj": item,
    #     "themes": item.selected_themes or item.suggested_themes,
    #     "backgrounds": item.selected_backgrounds or item.suggested_backgrounds,
    #     "poses": item.selected_poses or item.suggested_poses,
    #     "locations": item.selected_locations or item.suggested_locations,
    #     "colors": item.selected_colors or item.suggested_colors,
    #     "ai_response": ai_response,
    #     "detailed_prompt_text": detailed_prompt_text,
    #     "generate_ai_url": f"/probackendapp/generate_ai_images/{collection.id}/",
    # }
    def merge_unique(selected, suggested):
        """Merge selected and suggested items, removing duplicates while preserving order"""
        combined = list(suggested or [])
        for val in selected or []:
            if val not in combined:
                combined.append(val)
        return combined

    def categorize_options(selected, suggested):
        """Categorize options into suggested, selected, and combined for better display"""
        suggested_only = [item for item in (
            suggested or []) if item not in (selected or [])]
        selected_only = [item for item in (
            selected or []) if item not in (suggested or [])]
        both = [item for item in (selected or []) if item in (suggested or [])]

        return {
            'suggested_only': suggested_only,
            'selected_only': selected_only,
            'both': both,
            'all': merge_unique(selected, suggested)
        }

    context = {
        "project": project.name,
        "collection": collection,
        "item_obj": item,
        "themes": merge_unique(item.selected_themes, item.suggested_themes),
        "backgrounds": merge_unique(item.selected_backgrounds, item.suggested_backgrounds),
        "poses": merge_unique(item.selected_poses, item.suggested_poses),
        "locations": merge_unique(item.selected_locations, item.suggested_locations),
        "colors": merge_unique(item.selected_colors, item.suggested_colors),
        "themes_categorized": categorize_options(item.selected_themes, item.suggested_themes),
        "backgrounds_categorized": categorize_options(item.selected_backgrounds, item.suggested_backgrounds),
        "poses_categorized": categorize_options(item.selected_poses, item.suggested_poses),
        "locations_categorized": categorize_options(item.selected_locations, item.suggested_locations),
        "colors_categorized": categorize_options(item.selected_colors, item.suggested_colors),
        "ai_response": ai_response,
        "detailed_prompt_text": detailed_prompt_text,
        "generate_ai_url": f"/probackendapp/generate_ai_images/{collection.id}/",
    }

    return render(request, "probackendapp/project_setup_select.html", context)


try:
    from google import genai
    from google.genai import types
    has_genai = True
except ImportError:
    has_genai = False

# def generate_ai_images(request, collection_id):
#     if request.method != "POST":
#         return Response({"error": "Invalid request method."})

#     try:
#         collection = Collection.objects.get(id=collection_id)
#         description = collection.description
#         generated_images = []

#         if has_genai:
#             client = genai.Client(api_key=settings.GOOGLE_API_KEY)
#             model_name = "gemini-3-pro-image-preview"

#             for i in range(4):
#                 contents = [
#                     {"text": f"Generate a realistic human model image (face and shoulders visible) that model should sutalbe to the description of the collection and every model should be different: {description}. High-quality, photorealistic."}
#                 ]
#                 config = types.GenerateContentConfig(response_modalities=[types.Modality.IMAGE])
#                 resp = client.models.generate_content(model=model_name, contents=contents, config=config)
#                 candidate = resp.candidates[0]

#                 image_bytes = None
#                 for part in candidate.content.parts:
#                     if part.inline_data:
#                         data = part.inline_data.data
#                         image_bytes = data if isinstance(data, bytes) else base64.b64decode(data)
#                         break

#                 if not image_bytes:
#                     continue

#                 buf = io.BytesIO(image_bytes)
#                 buf.seek(0)
#                 upload_result = cloudinary.uploader.upload(
#                     buf,
#                     folder="collection_ai_models",
#                     public_id=f"collection_{collection.id}_{i+1}",
#                     overwrite=True
#                 )
#                 generated_images.append(upload_result['secure_url'])

#         else:
#             return Response({"error": "Gemini SDK not available."})

#         return Response({"images": generated_images})

#     except Exception as e:
#         traceback.print_exc()
#         return Response({"error": str(e)})


# Constants for image generation
MAX_IMAGE_BYTES = 9 * 1024 * 1024  # 9MB maximum image size
CLOUDINARY_UPLOAD_TIMEOUT = 120  # 120 seconds timeout for Cloudinary uploads


def generate_ai_images_background(collection_id, user_id):
    """
    Background function for generating AI model images for a collection.
    This function is called by Celery and doesn't use request object.
    Returns a dict with success status and results.
    """
    # === Credit Check and Deduction ===
    from CREDITS.utils import deduct_credits, get_user_organization
    from users.models import User

    # Credits per image generation: 2 credits for new image generation
    CREDITS_PER_IMAGE = 2
    # This function generates 4 AI model images, so total credits = 4 * 2 = 8
    TOTAL_IMAGES_TO_GENERATE = 4
    TOTAL_CREDITS_NEEDED = TOTAL_IMAGES_TO_GENERATE * CREDITS_PER_IMAGE

    # Get user
    user = User.objects(id=user_id).first()
    if not user:
        return {"success": False, "error": "User not found"}

    # Get collection first to access project
    try:
        collection = Collection.objects.get(id=collection_id)
    except Collection.DoesNotExist:
        return {"success": False, "error": "Collection not found."}

    # Check if user has organization - if not, allow generation without credit deduction
    organization = get_user_organization(user)
    if organization:
        # Check and deduct credits before generation (for all 4 images)
        credit_result = deduct_credits(
            organization=organization,
            user=user,
            amount=TOTAL_CREDITS_NEEDED,
            reason=f"AI model images generation ({TOTAL_IMAGES_TO_GENERATE} images)",
            project=collection.project if hasattr(
                collection, 'project') else None,
            metadata={"type": "generate_ai_images_background",
                      "total_images": TOTAL_IMAGES_TO_GENERATE}
        )

        if not credit_result['success']:
            return {"success": False, "error": credit_result['message']}
    # If no organization, allow generation to proceed without credit deduction

    description = getattr(collection, "description", "") or ""
    generated_images = []

    if not has_genai:
        return {"success": False, "error": "Gemini SDK not available."}

    client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    model_name = "gemini-3-pro-image-preview"

    for i in range(4):
        prompt_text = (
            f"Generate a realistic human model image (face and shoulders visible) "
            f"suitable for the collection description: {description}. "
            f"High-quality, photorealistic."
        )

        contents = [{"role": "user", "parts": [{"text": prompt_text}]}]

        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=[types.Modality.IMAGE]
                ),
            )
        except Exception as gen_err:
            print(f"❌ Error generating image (iteration {i+1}): {gen_err}")
            traceback.print_exc()
            continue

        # Validate response candidates
        if not getattr(resp, "candidates", None):
            print(f"⚠️ No candidates returned for iteration {i+1}: {resp}")
            continue

        candidate = resp.candidates[0]
        if not getattr(candidate, "content", None):
            print(
                f"⚠️ Candidate has no content for iteration {i+1}: {candidate}")
            continue

        # Extract first inline image data we can find
        image_bytes = None
        try:
            for part in candidate.content.parts:
                # defensive checks for inline_data presence
                if hasattr(part, "inline_data") and getattr(part, "inline_data"):
                    data = getattr(part.inline_data, "data", None)
                    if data:
                        if isinstance(data, (bytes, bytearray)):
                            image_bytes = bytes(data)
                        else:
                            # assume base64 string
                            image_bytes = base64.b64decode(data)
                        break
        except Exception as e:
            print(f"⚠️ Error extracting image bytes (iteration {i+1}): {e}")
            traceback.print_exc()
            image_bytes = None

        if not image_bytes:
            print(
                f"⚠️ No image data found in parts for iteration {i+1}. Skipping.")
            continue

        # Safety checks
        if len(image_bytes) == 0:
            print(
                f"⚠️ Generated image buffer is empty for iteration {i+1}. Skipping.")
            continue

        if len(image_bytes) > MAX_IMAGE_BYTES:
            print(
                f"⚠️ Generated image too large ({len(image_bytes)} bytes) for iteration {i+1}. Skipping.")
            continue

        # Upload to Cloudinary inside try/except with a timeout and checks
        buf = io.BytesIO(image_bytes)
        buf.seek(0)

        try:
            upload_result = cloudinary.uploader.upload(
                buf,
                folder="collection_ai_models",
                public_id=f"collection_{collection.id}_{i+1}",
                overwrite=True,
                timeout=CLOUDINARY_UPLOAD_TIMEOUT,
                resource_type="image",
            )
        except Exception as upload_err:
            print(
                f"❌ Cloudinary upload failed for iteration {i+1}: {upload_err}")
            traceback.print_exc()
            continue

        # Validate upload result
        secure_url = upload_result.get("secure_url")
        if not secure_url:
            print(
                f"⚠️ Cloudinary returned no secure_url for iteration {i+1}: {upload_result}")
            continue

        generated_images.append(secure_url)

        # Track generation in history (non-blocking)
        try:
            from .history_utils import track_project_image_generation
            track_project_image_generation(
                user_id=str(user_id),
                collection_id=str(collection.id),
                image_type="project_ai_model_generation",
                image_url=secure_url,
                prompt=prompt_text,
                metadata={
                    "action": "ai_model_generation",
                    "model_index": i + 1,
                    "total_generated": len(generated_images)
                }
            )
        except Exception as history_error:
            print(
                f"Error tracking AI model generation history: {history_error}")

    # Get already saved images from the collection (defensive)
    saved_images = []
    try:
        if getattr(collection, "items", None) and len(collection.items) > 0:
            first_item = collection.items[0]
            if hasattr(first_item, "generated_model_images") and first_item.generated_model_images:
                saved_images = [img.get(
                    "cloud") for img in first_item.generated_model_images if img and "cloud" in img]
    except Exception as e:
        print(f"⚠️ Error collecting saved images: {e}")
        traceback.print_exc()

    return {
        "success": True,
        "images": generated_images,
        "saved_images": saved_images,
        "total_generated": len(generated_images)
    }


def generate_ai_images(request, collection_id):
    """
    Generate AI images for a collection using Celery for background processing.
    Now uses Celery for background processing.
    """
    from .tasks import generate_ai_images_task
    from .utils import enqueue_task_with_load_balancing

    try:
        # Get user_id from request
        user_id = str(request.user.id) if hasattr(
            request, 'user') and request.user else None

        # Start Celery task using load-based queue selection
        task = enqueue_task_with_load_balancing(
            generate_ai_images_task, collection_id, user_id
        )

        return JsonResponse({
            "success": True,
            "message": "AI image generation started.",
            "task_id": task.id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)

# def save_generated_images(request, collection_id):
#     if request.method != "POST":
#         return Response({"success": False, "error": "Invalid request method."})

#     try:
#         data = json.loads(request.body)
#         selected_images = data.get("images", [])

#         if not selected_images:
#             return Response({"success": False, "error": "No images selected."})

#         collection = Collection.objects.get(id=collection_id)

#         if not collection.items:
#             return Response({"success": False, "error": "No items found in collection."})

#         item = collection.items[0]  # Assuming single item per collection

#         # Ensure field exists
#         if not hasattr(item, "generated_model_images"):
#             item.generated_model_images = []

#         saved_images = []
#         local_dir = os.path.join(settings.MEDIA_ROOT, "model_images")
#         os.makedirs(local_dir, exist_ok=True)

#         # Extract existing cloud URLs to avoid duplicates
#         existing_urls = {entry.get(
#             "cloud") for entry in item.generated_model_images if "cloud" in entry}

#         for url in selected_images:
#             if url in existing_urls:
#                 continue  # Skip duplicates

#             # Download image from Cloudinary
#             filename = url.split("/")[-1]
#             local_path = os.path.join(local_dir, filename)
#             resp = requests.get(url)
#             if resp.status_code == 200:
#                 with open(local_path, "wb") as f:
#                     f.write(resp.content)

#             # Save both paths (local + cloud)
#             entry = {"local": local_path, "cloud": url}
#             item.generated_model_images.append(entry)
#             saved_images.append(entry)

#         collection.save()

#         return Response({
#             "success": True,
#             "saved": saved_images,
#             "skipped_duplicates": len(selected_images) - len(saved_images)
#         })

#     except DoesNotExist:
#         return Response({"success": False, "error": "Collection not found."})
#     except Exception as e:
#         traceback.print_exc()
#         return Response({"success": False, "error": str(e)})


@authenticate
def save_generated_images(request, collection_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method."})

    try:
        data = json.loads(request.body)
        selected_images = set(data.get("images", []))

        collection = Collection.objects.get(id=collection_id)

        # Ensure collection has at least 1 item
        if not collection.items or len(collection.items) == 0:
            # Create the item dynamically if missing
            item = CollectionItem()
            collection.items.append(item)
            collection.save()

        item = collection.items[0]

        existing = item.generated_model_images or []
        existing_urls = {img.get("cloud")
                         for img in existing if img and isinstance(img, dict)}

        local_dir = os.path.join(settings.MEDIA_ROOT, "model_images")
        os.makedirs(local_dir, exist_ok=True)

        updated_images = [img for img in existing if img and isinstance(
            img, dict) and img.get("cloud") in selected_images]

        for url in selected_images - existing_urls:
            filename = url.split("/")[-1]
            local_path = os.path.join(local_dir, filename)

            resp = requests.get(url)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)

            updated_images.append({"local": local_path, "cloud": url})

        # Save back
        item.generated_model_images = updated_images
        collection.save()

        return JsonResponse({
            "success": True,
            "total_selected": len(selected_images),
            "stored_images": len(updated_images),
            "images": updated_images
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)})
# -------------------------
# Collection detail view
# -------------------------


def collection_detail(request, project_id, collection_id):
    collection = get_object_or_404(
        Collection, id=collection_id, project_id=project_id)
    return render(request, "probackendapp/collection_detail.html", {"collection": collection})


def upload_product_images_page(request, collection_id):
    from django.shortcuts import render
    collection = Collection.objects.get(id=collection_id)
    return render(request, "probackendapp/upload_product_images.html", {"collection": collection})


@authenticate
def upload_product_images_api(request, collection_id):
    if request.method != "POST":
        return Response({"success": False, "error": "Invalid request method."})

    try:
        collection = Collection.objects.get(id=collection_id)
        if not collection.items:
            return Response({"success": False, "error": "No items found in collection."})

        item = collection.items[0]  # assuming single item per collection
        uploaded_files = request.FILES.getlist("images")

        if not uploaded_files:
            return Response({"success": False, "error": "No images uploaded."})

        # Get ornament types from request
        ornament_types_json = request.POST.get("ornament_types", "[]")
        try:
            import json
            ornament_types = json.loads(ornament_types_json)
        except (json.JSONDecodeError, ValueError):
            ornament_types = []

        # Ensure ornament_types list matches the number of files
        if len(ornament_types) != len(uploaded_files):
            return Response({"success": False, "error": "Number of ornament types must match number of files."})

        local_dir = os.path.join(settings.MEDIA_ROOT, "product_images")
        os.makedirs(local_dir, exist_ok=True)

        new_product_images = []

        for index, file in enumerate(uploaded_files):
            upload_result = cloudinary.uploader.upload(
                file,
                folder="collection_product_images",
                overwrite=True
            )
            cloud_url = upload_result.get("secure_url")

            local_path = os.path.join(local_dir, file.name)
            with open(local_path, "wb") as f:
                for chunk in file.chunks():
                    f.write(chunk)

            # ✅ Create EmbeddedDocument object instead of dict
            product_img = ProductImage(
                uploaded_image_url=cloud_url,
                uploaded_image_path=local_path,
                generated_images=[],
                ornament_type=ornament_types[index] if index < len(
                    ornament_types) else None,
                generation_selections={
                    "plainBg": False,
                    "bgReplace": False,
                    "model": False,
                    "campaign": False
                }
            )

            new_product_images.append(product_img)

        # ✅ Append properly
        if not hasattr(item, "product_images"):
            item.product_images = []
        item.product_images.extend(new_product_images)

        # ✅ Save back properly to MongoEngine
        collection.items[0] = item
        collection.save()

        # Track product image uploads in history
        try:
            from .history_utils import track_project_image_generation
            user_id = str(request.user.id) if hasattr(
                request, 'user') and request.user else "system"
            for product_img in new_product_images:
                track_project_image_generation(
                    user_id=user_id,
                    collection_id=str(collection.id),
                    image_type="project_product_upload",
                    image_url=product_img.uploaded_image_url,
                    prompt="Product image uploaded to project",
                    local_path=product_img.uploaded_image_path,
                    metadata={
                        "action": "product_upload",
                        "total_products": len(new_product_images)
                    }
                )
        except Exception as history_error:
            print(f"Error tracking product upload history: {history_error}")

        return Response({"success": True, "count": len(new_product_images)})

    except Exception as e:
        traceback.print_exc()
        return Response({"success": False, "error": str(e)})


def generate_product_model_page(request, collection_id):
    """Render the template with product images and available model images"""
    try:
        collection = Collection.objects.get(id=collection_id)
        item = collection.items[0]

        product_images = item.product_images if hasattr(
            item, "product_images") else []
        model_images = item.generated_model_images if hasattr(
            item, "generated_model_images") else []

        return render(request, "probackendapp/generate_product_model.html", {
            "collection": collection,
            "product_images": product_images,
            "model_images": model_images,
        })
    except Exception as e:
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


@csrf_exempt
def generate_product_model_api(request, collection_id):
    """
    Generate composite AI image combining a product and selected model
    using Gemini, aligning naturally with realistic shadows & lighting.
    """
    try:
        collection = Collection.objects.get(id=collection_id)
        item = collection.items[0]

        product_url = request.POST.get("product_url")
        model_url = request.POST.get("model_url")
        prompt_text = request.POST.get("prompt")

        if not all([product_url, model_url, prompt_text]):
            return Response({"success": False, "error": "Missing data."})

        if not settings.GOOGLE_API_KEY:
            return Response({"success": False, "error": "GOOGLE_API_KEY not configured."})

        # ✅ Initialize Gemini client
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = "gemini-3-pro-image-preview"

        import requests
        import base64
        import os
        import uuid

        # Download both images
        product_data = base64.b64encode(
            requests.get(product_url).content).decode("utf-8")
        model_data = base64.b64encode(
            requests.get(model_url).content).decode("utf-8")

        contents = [
            {"inline_data": {"mime_type": "image/jpeg", "data": model_data}},
            {"inline_data": {"mime_type": "image/jpeg", "data": product_data}},
            {"text": f"Place the product naturally on the model according to this prompt: {prompt_text}. Maintain realism, shadows, proportions, and lighting."}
        ]

        config = types.GenerateContentConfig(
            response_modalities=[types.Modality.IMAGE])

        resp = client.models.generate_content(
            model=model_name, contents=contents, config=config)

        candidate = resp.candidates[0]
        generated_bytes = None
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                data = part.inline_data.data
                generated_bytes = data if isinstance(
                    data, bytes) else base64.b64decode(data)
                break

        if not generated_bytes:
            return Response({"success": False, "error": "Gemini did not return an image."})

        # Save locally
        output_dir = os.path.join("media", "composite_images", str(
            collection_id), str(uuid.uuid4()))
        os.makedirs(output_dir, exist_ok=True)
        local_path = os.path.join(output_dir, "composite.png")
        with open(local_path, "wb") as f:
            f.write(generated_bytes)

        # Upload to Cloudinary
        import cloudinary.uploader
        cloud_upload = cloudinary.uploader.upload(
            local_path,
            folder=f"ai_studio/composite/{collection_id}/{uuid.uuid4()}/",
            use_filename=True,
            unique_filename=False,
            resource_type="image"
        )

        result = {
            "url": cloud_upload["secure_url"],
            "path": local_path
        }

        return Response({"success": True, "image": result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


# @csrf_exempt
# def generate_all_product_model_images(request, collection_id):
#     """
#     Generate AI images for all product images in a collection using a local model image
#     and prompts stored in `generated_prompts`. Saves both locally and in Cloudinary.
#     """
#     import os
#     import base64
#     import uuid
#     import requests
#     import traceback
#     import cloudinary.uploader

#     try:
#         collection = Collection.objects.get(id=collection_id)
#         item = collection.items[0]
#         body = json.loads(request.body.decode("utf-8"))

#         # Local model image path (you can adjust where it is stored)
#         model_local_path = body.get("model_local_path")
#         print(model_local_path)
#         if not os.path.exists(model_local_path):
#             return Response({"success": False, "error": "Local model image not found."})

#         # Ensure prompts exist
#         if not hasattr(item, "generated_prompts") or not item.generated_prompts:
#             return Response({"success": False, "error": "No generated prompts found."})

#         # Read model image once
#         with open(model_local_path, "rb") as f:
#             model_bytes = f.read()
#         model_b64 = base64.b64encode(model_bytes).decode("utf-8")

#         client = genai.Client(api_key=settings.GOOGLE_API_KEY)
#         model_name = "gemini-3-pro-image-preview"

#         # Loop through each uploaded product image
#         for product in item.product_images:  # adjust field name
#             product_path = product.uploaded_image_path
#             if not os.path.exists(product_path):
#                 print(f"⚠️ Product image not found: {product_path}")
#                 continue

#             with open(product_path, "rb") as f:
#                 product_bytes = f.read()
#             product_b64 = base64.b64encode(product_bytes).decode("utf-8")

#             generated_dict = {}
#             prompt_templates = {
#     "white_background": (
#         "Create a product photo with a clean, elegant white background. "
#         "The product should be centered, well-lit with studio lighting, and displayed naturally. "
#         "Keep reflections, shadows, and proportions realistic. "
#         "Follow this specific style prompt: {prompt_text}"
#     ),
#     "background_replace": (
#         "Replace the background of the product image with one that enhances its visual appeal "
#         "and makes the product stand out. Ensure correct positioning, perspective, and realistic lighting. "
#         "Follow this specific style prompt: {prompt_text}"
#     ),
#     "model_image": (
#         "Overlay or dress the uploaded model with the product realistically. "
#         "Ensure proportions, fitting, and lighting match naturally. "
#         "Make it elegant and fashion-photography style. "
#         "Follow this specific style prompt: {prompt_text}"
#     ),
#     "campaign_image": (
#         "Create a professional campaign shot where the model is wearing the product in a lifestyle or editorial setting. "
#         "Use cinematic lighting, balanced colors, and realistic shadow integration. "
#         "The overall output should look like a magazine photoshoot. "
#         "Follow this specific style prompt: {prompt_text}"
#     ),
# }

#             # Generate images for each prompt key
#             for key, prompt_text in item.generated_prompts.items():
#                 try:
#                     contents = [
#                         {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}},
#                         {"inline_data": {"mime_type": "image/jpeg", "data": product_b64}},
#                         {"text": f"Place the product naturally on the model according to this prompt: {prompt_text}. Maintain realism, shadows, proportions, and lighting."}
#                     ]

#                     config = types.GenerateContentConfig(
#                         response_modalities=[types.Modality.IMAGE])

#                     resp = client.models.generate_content(
#                         model=model_name, contents=contents, config=config
#                     )

#                     candidate = resp.candidates[0]
#                     generated_bytes = None
#                     for part in candidate.content.parts:
#                         if part.inline_data and part.inline_data.data:
#                             data = part.inline_data.data
#                             generated_bytes = data if isinstance(
#                                 data, bytes) else base64.b64decode(data)
#                             break

#                     if not generated_bytes:
#                         print(
#                             f"⚠️ No image returned for {key} of {product.uploaded_image_url}")
#                         continue

#                     # Save locally
#                     output_dir = os.path.join("media", "composite_images", str(
#                         collection_id), str(uuid.uuid4()))
#                     os.makedirs(output_dir, exist_ok=True)
#                     local_path = os.path.join(output_dir, f"{key}.png")
#                     with open(local_path, "wb") as f:
#                         f.write(generated_bytes)

#                     # Upload to Cloudinary
#                     cloud_upload = cloudinary.uploader.upload(
#                         local_path,
#                         folder=f"ai_studio/composite/{collection_id}/{uuid.uuid4()}/",
#                         use_filename=True,
#                         unique_filename=False,
#                         resource_type="image"
#                     )

#                     generated_dict[key] = {
#                         "url": cloud_upload["secure_url"],
#                         "path": local_path
#                     }

#                 except Exception as e:
#                     traceback.print_exc()
#                     print(
#                         f"⚠️ Failed to generate {key} for {product.uploaded_image_url}: {e}")
#                     continue

#             # Save generated images for this product
#             product.generated_images = generated_dict

#         # Save collection after all images generated
#         collection.save()
#         return Response({"success": True, "message": "All product model images generated successfully."})

#     except Exception as e:
#         traceback.print_exc()
#         return Response({"success": False, "error": str(e)}, status=500)


def _extract_ornament_types_from_analysis(analysis_text):
    """
    Extract ornament types mentioned in the master analysis text.
    Returns a list of ornament descriptions found, preserving specificity (e.g., "long necklace", "multi-strand necklace").
    """
    if not analysis_text:
        return []

    import re
    # Normalize the text to lowercase for matching
    text_lower = analysis_text.lower()

    found_descriptions = []

    # Extract full ornament descriptions with modifiers (order matters - more specific first)
    # Pattern: modifier + ornament type (e.g., "long necklace", "multi-strand pearl and gold necklace")
    specific_patterns = [
        # Very specific patterns first
        r'\b(multi-strand pearl and gold choker-style necklace|multi-strand pearl and gold choker|choker-style necklace|choker style necklace)\b',
        r'\b(multi-strand pearl and gold necklace|multi-strand pearl necklace|multi strand pearl necklace)\b',
        r'\b(multi-tiered elaborate gold haram|multi-tiered haram|elaborate gold haram)\b',
        r'\b(jhumka-style earring|jhumka-style earrings|jhumka earring|jhumka earrings)\b',
        r'\b(stud earring|stud earrings)\b',
        r'\b(long necklace|long necklaces)\b',
        r'\b(short necklace|short necklaces)\b',
        r'\b(delicate necklace|delicate necklaces)\b',
        r'\b(chunky necklace|chunky necklaces)\b',
        r'\b(pendant necklace|pendant necklaces)\b',
        r'\b(multi-strand necklace|multi strand necklace|multi-strand|multi strand)\b',
        r'\b(choker|chokers)\b',
        r'\b(haram)\b',
    ]

    # Extract specific descriptions
    for pattern in specific_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            # Normalize but preserve specificity
            normalized = match.rstrip('s') if match.endswith('s') else match
            if normalized not in found_descriptions:
                found_descriptions.append(normalized)

    # Also extract basic types (for fallback matching)
    basic_patterns = [
        r'\b(bangle|bangles)\b',
        r'\b(necklace|necklaces)\b',
        r'\b(earring|earrings)\b',
        r'\b(ring|rings)\b',
        r'\b(bracelet|bracelets)\b',
        r'\b(pendant|pendants)\b',
        r'\b(choker|chokers)\b',
        r'\b(anklet|anklets)\b',
        r'\b(brooch|brooches)\b',
        r'\b(chain|chains)\b',
    ]

    for pattern in basic_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            normalized = match.rstrip('s') if match.endswith('s') else match
            # Only add if not already covered by a specific description
            if normalized not in found_descriptions:
                # Check if this basic type is already part of a more specific description
                is_covered = False
                for desc in found_descriptions:
                    if normalized in desc:
                        is_covered = True
                        break
                if not is_covered:
                    found_descriptions.append(normalized)

    return found_descriptions


def _get_ornament_category(ornament_type):
    """
    Get the main category for an ornament type.
    Maps specific types to their main categories for fallback matching.
    Returns the main category name.
    """
    if not ornament_type:
        return None

    normalized = ornament_type.lower().strip()
    normalized = normalized.replace('_', ' ')

    # Remove common suffixes
    if normalized.endswith('s'):
        normalized = normalized[:-1]

    # Category mapping: specific types -> main categories
    # Necklace series: necklace, choker, pendant, chain, haram, etc.
    necklace_series = ['necklace', 'choker',
                       'pendant', 'chain', 'collar', 'haram']
    # Earring series: earring, stud, jhumka, etc.
    earring_series = ['earring', 'stud', 'jhumka']
    # Ring series: ring, band, etc.
    ring_series = ['ring', 'band']
    # Bracelet series: bracelet, bangle, cuff, etc.
    bracelet_series = ['bracelet', 'bangle', 'cuff']

    # Check which category the ornament belongs to
    for necklace_type in necklace_series:
        if necklace_type in normalized:
            return 'necklace'

    for earring_type in earring_series:
        if earring_type in normalized:
            return 'earring'

    for ring_type in ring_series:
        if ring_type in normalized:
            return 'ring'

    for bracelet_type in bracelet_series:
        if bracelet_type in normalized:
            return 'bracelet'

    # Default fallback
    if 'anklet' in normalized:
        return 'anklet'
    if 'brooch' in normalized:
        return 'brooch'

    return None


def _normalize_ornament_type(ornament_type):
    """
    Normalize ornament type string for matching.
    Converts to lowercase, handles underscores/spaces, but preserves specificity.
    Returns both the full normalized form and base type.
    """
    if not ornament_type:
        return None, None

    normalized = ornament_type.lower().strip()

    # Replace underscores with spaces for matching
    normalized = normalized.replace('_', ' ')

    # Remove common suffixes
    base_normalized = normalized
    if base_normalized.endswith('s'):
        base_normalized = base_normalized[:-1]

    # Extract base type (for fallback matching)
    base_type = None
    if 'necklace' in base_normalized:
        base_type = 'necklace'
    elif 'choker' in base_normalized:
        base_type = 'necklace'  # Choker is part of necklace series
    elif 'pendant' in base_normalized:
        base_type = 'necklace'  # Pendant is part of necklace series
    elif 'chain' in base_normalized:
        base_type = 'necklace'  # Chain is part of necklace series
    elif 'haram' in base_normalized:
        base_type = 'necklace'  # Haram is part of necklace series
    elif 'earring' in base_normalized:
        base_type = 'earring'
    elif 'stud' in base_normalized:
        base_type = 'earring'  # Stud is part of earring series
    elif 'jhumka' in base_normalized:
        base_type = 'earring'  # Jhumka is part of earring series
    elif 'bangle' in base_normalized:
        base_type = 'bracelet'  # Bangle is part of bracelet series
    elif 'bracelet' in base_normalized:
        base_type = 'bracelet'
    elif 'ring' in base_normalized:
        base_type = 'ring'
    elif 'anklet' in base_normalized:
        base_type = 'anklet'
    elif 'brooch' in base_normalized:
        base_type = 'brooch'

    return normalized, base_type


def _check_ornament_type_match(product_ornament_type, master_analysis_text):
    """
    Check if the product's ornament type matches any ornament type mentioned in the master analysis.
    Returns True if there's a match, False otherwise.
    Handles specific types like "long_necklace" matching "long necklace" in analysis.
    Also falls back to category-level matching (e.g., "choker" matches "necklace" category).
    Handles both JSON format (with type and description) and plain text format.
    """
    if not product_ornament_type or not master_analysis_text:
        return False

    # Check if master_analysis_text is JSON format and extract type/description
    import json
    analysis_text_to_search = master_analysis_text
    analysis_type = None

    try:
        analysis_json = json.loads(master_analysis_text.strip())
        if isinstance(analysis_json, dict):
            analysis_type = analysis_json.get('type', '')
            analysis_description = analysis_json.get('description', '')
            # Combine type and description for searching
            if analysis_type and analysis_description:
                analysis_text_to_search = f"{analysis_type} {analysis_description}"
            elif analysis_description:
                analysis_text_to_search = analysis_description
            elif analysis_type:
                analysis_text_to_search = analysis_type
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Not JSON, use as-is
        pass

    # Normalize product ornament type (preserve specificity)
    normalized_product_type, product_base_type = _normalize_ornament_type(
        product_ornament_type)
    if not normalized_product_type:
        return False

    # Get product's main category for fallback matching
    product_category = _get_ornament_category(product_ornament_type)

    # Convert product type to space-separated format for matching
    # e.g., "long_necklace" -> "long necklace"
    product_type_for_matching = normalized_product_type.replace('_', ' ')

    # If we have analysis_type from JSON, check direct match first
    if analysis_type:
        normalized_analysis_type, _ = _normalize_ornament_type(analysis_type)
        if normalized_analysis_type:
            normalized_analysis_type_spaces = normalized_analysis_type.replace(
                '_', ' ')
            # Exact match
            if product_type_for_matching == normalized_analysis_type_spaces:
                return True
            # Check if product type is contained in analysis type or vice versa
            if product_type_for_matching in normalized_analysis_type_spaces or normalized_analysis_type_spaces in product_type_for_matching:
                return True

    # Extract ornament descriptions from master analysis (using the text we prepared)
    analysis_ornament_descriptions = _extract_ornament_types_from_analysis(
        analysis_text_to_search)

    # Step 1: Check for exact or close match first (preserving specificity)
    for analysis_desc in analysis_ornament_descriptions:
        analysis_normalized = analysis_desc.lower().strip()

        # Exact match (e.g., "long necklace" == "long necklace")
        if product_type_for_matching == analysis_normalized:
            return True

        # Check if product type is contained in analysis description
        # e.g., "long necklace" contains "long necklace" from product
        if product_type_for_matching in analysis_normalized:
            return True

        # Check if analysis description is contained in product type
        # e.g., product "long necklace" contains analysis "necklace"
        if analysis_normalized in product_type_for_matching:
            return True

        # Check word-by-word match for compound types
        # e.g., "long necklace" matches "long necklace" even if word order differs slightly
        product_words = set(product_type_for_matching.split())
        analysis_words = set(analysis_normalized.split())

        # If all product words are in analysis (specific match)
        if product_words.issubset(analysis_words) and len(product_words) > 1:
            return True

    # Step 2: Fallback to base type match (e.g., both are "necklace" type)
    if product_base_type:
        for analysis_desc in analysis_ornament_descriptions:
            analysis_normalized = analysis_desc.lower().strip()
            if product_base_type in analysis_normalized:
                # Make sure it's not a false positive (e.g., "earring" matching "wearing")
                # Check if it's a standalone word or part of a compound
                import re
                if re.search(r'\b' + re.escape(product_base_type) + r'\b', analysis_normalized):
                    return True

    # Step 3: Category-level fallback matching
    # If product is "long necklace" (necklace series) and analysis has "choker" or "choker-style necklace", match them
    if product_category:
        for analysis_desc in analysis_ornament_descriptions:
            analysis_normalized = analysis_desc.lower().strip()
            # Get the category of the analysis ornament type
            analysis_category = _get_ornament_category(analysis_desc)

            # If both belong to the same category, match them
            # e.g., product "long necklace" (category: necklace) matches analysis "choker-style necklace" (category: necklace)
            if analysis_category == product_category:
                return True

            # Also check if the category name appears in the analysis description
            # e.g., analysis mentions "necklace" and product is "long necklace" (category: necklace)
            if product_category in analysis_normalized:
                import re
                if re.search(r'\b' + re.escape(product_category) + r'\b', analysis_normalized):
                    return True

    # Step 4: Check if the product type appears directly in the master analysis text
    # This handles cases where the ornament type might be mentioned but not captured by patterns
    master_analysis_lower = analysis_text_to_search.lower()

    # Check if product type (with spaces) appears in the analysis
    if product_type_for_matching in master_analysis_lower:
        return True

    # Check if product type (with underscores) appears in the analysis
    product_type_underscore = normalized_product_type.replace(' ', '_')
    if product_type_underscore in master_analysis_lower:
        return True

    # Step 5: Final fallback - check if product's category appears in analysis
    if product_category and product_category in master_analysis_lower:
        import re
        if re.search(r'\b' + re.escape(product_category) + r'\b', master_analysis_lower):
            return True

    return False


def generate_single_product_model_image_background(collection_id, user_id, product_index, prompt_key, job_id=None):
    """
    Generate a single image for a specific product index and prompt key.
    This is the core worker logic used by Celery so that each task
    is responsible for exactly ONE image.
    """
    import os
    import base64
    import uuid
    import json
    import traceback
    import cloudinary.uploader
    from datetime import datetime
    from google import genai
    from google.genai import types
    from django.conf import settings

    from .job_models import ImageGenerationJob

    try:
        # === Credit Check and Deduction ===
        from CREDITS.utils import deduct_credits, get_user_organization
        from users.models import User, Role

        # Credits per image generation: 2 credits for new image generation
        CREDITS_PER_IMAGE = 2

        # Get user
        user = User.objects(id=user_id).first()
        if not user:
            return {"success": False, "error": "User not found"}

        # Get collection first to access project
        collection = Collection.objects.get(id=collection_id)

        # Check if user has organization - if not, allow generation without credit deduction
        organization = get_user_organization(user)
        if organization:
            # Check and deduct credits before generation
            credit_result = deduct_credits(
                organization=organization,
                user=user,
                amount=CREDITS_PER_IMAGE,
                reason=f"Product model image generation - {prompt_key}",
                project=collection.project if hasattr(
                    collection, 'project') else None,
                metadata={"type": "product_model_image",
                          "prompt_key": prompt_key, "product_index": product_index}
            )

            if not credit_result['success']:
                return {"success": False, "error": credit_result['message']}
        # If no organization, allow generation to proceed without credit deduction
        if not collection.items:
            return {"success": False, "error": "No items found in collection."}

        item = collection.items[0]

        if not hasattr(item, "selected_model") or not item.selected_model:
            return {"success": False, "error": "No model selected. Please select a model first."}

        selected_model = item.selected_model
        model_local_path = selected_model.get("local")
        model_cloud_url = selected_model.get("cloud")

        # Check if model local path exists, if not try to download from cloud URL
        if not model_local_path or not os.path.exists(model_local_path):
            return {"success": False, "error": "Selected model image not found on server."}

        if not hasattr(item, "generated_prompts") or not item.generated_prompts:
            return {"success": False, "error": "No generated prompts found."}

        # Bound check for product index
        if product_index < 0 or product_index >= len(item.product_images):
            return {"success": False, "error": "Invalid product index."}

        if prompt_key not in item.generated_prompts:
            return {"success": False, "error": f"Prompt key '{prompt_key}' not found."}

        # Read model image once
        with open(model_local_path, "rb") as f:
            model_bytes = f.read()
        model_b64 = base64.b64encode(model_bytes).decode("utf-8")

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = "gemini-3-pro-image-preview"

        # Prompt templates
        from .prompt_initializer import get_prompt_from_db

        default_white_bg = """remove the background from the product image and replace it with a clean, elegant white studio background.
        Do NOT modify, alter, or redesign the product in any way — its color, shape, texture, and proportions must remain exactly the same.(important dont change the product image) 
Generate a high-quality product photo on a clean, elegant white studio background. 
The product should appear exactly as in the input image, only placed against a professional white background. 
Ensure balanced, soft studio lighting with natural shadows and realistic reflections. 
Highlight product clarity and detail. 
Follow this specific style prompt: {prompt_text}"""

        default_bg_replace = """Use the provided ornament product image as the hero subject of a professional product photography shot. 
Do NOT redraw, reinterpret, or change the ornament in any way. Do NOT modify the ornament's shape, texture, color, size, material, reflections, orientation, or proportions. The ornament must appear exactly as in the original product image.

CAMERA ANGLE AND PERSPECTIVE (CRITICAL): Follow the EXACT camera angle and perspective described in the style reference below. If the style reference specifies a camera angle (e.g., "elevated diagonal perspective", "overhead 90-degree angle", "flat-lay top-down view"), you MUST use that EXACT angle. Do NOT default to a flat-lay view unless explicitly specified in the style reference.

The ornament must stay clearly visible, well-framed, and the dominant focal point of the composition.

Surround the ornament with carefully chosen supporting elements and objects that enhance its appeal, such as coordinated fabrics, jewelry props, trays, soft decor pieces, or festive details, while keeping the scene clean and premium. 
All added elements must support the ornament, not compete with it.

Place the ornament on a realistic premium surface such as silk fabric, velvet, marble, or textured stone, maintaining full physical contact between the ornament and the surface with grounded shadows directly beneath it (unless the style reference specifies a different placement or arrangement).

Create a studio-quality product photography environment with:
- soft diffused lighting (adjust based on style reference)
- gentle warm highlights
- clean, natural shadow falloff
- high surface and material realism
- crisp focus on the ornament and slightly softer focus on surrounding elements

Background and props may add mood and storytelling but must remain visually secondary to the ornament. 
The ornament must always remain the sharpest, brightest, and most visually dominant element in the frame.

MASTER ANALYSIS FOLLOWING (CRITICAL): If the style prompt below is a comprehensive master theme analysis, you MUST follow it EXACTLY without missing a single detail. The master analysis contains specific information about:
- Exact camera angle and perspective (e.g., "elevated diagonal perspective", "photographed from an overhead 90-degree angle", "flat-lay top-down view") - FOLLOW THIS EXACTLY
- Exact placement and positioning of ornaments (e.g., "rests diagonally", "gracefully drapes", "positioned elegantly beside", "commands attention") - FOLLOW THIS EXACTLY
- Precise lighting conditions (e.g., "soft, warm ambient lighting", "shallow depth of field", "soft diffused top lighting") - FOLLOW THIS EXACTLY
- Specific surface materials and textures (e.g., "light beige, rectangular jewelry box", "soft, neutral surface", "silk fabric, velvet, marble") - FOLLOW THIS EXACTLY
- Exact artistic style and mood (e.g., "sophisticated minimalism", "opulent heritage", "serene luxury") - FOLLOW THIS EXACTLY
- All supporting elements and props mentioned (e.g., flowers, decorative pieces, fabrics, vintage treasure chest, ceremonial fabric) - FOLLOW THIS EXACTLY
- Follow EVERY detail from the master analysis exactly as described - do not generalize or simplify any aspect.

The style reference below contains the EXACT description including camera angle, placement, lighting, materials, and all visual elements. Follow it PRECISELY:
{prompt_text}
"""

        default_model = """CRITICAL MODEL PRESERVATION REQUIREMENTS - MANDATORY:

Use the uploaded model image as the absolute identity reference. The generated model MUST look EXACTLY the same as the uploaded model with ZERO changes to:

FACIAL STRUCTURE (MANDATORY - EXACT MATCH):
- Exact facial bone structure: jawline, cheekbones, chin shape, forehead shape
- Exact facial proportions: face width, face length, facial symmetry
- Exact eye structure: eye shape, eye size, eye spacing, eyelid shape, eyebrow shape and position
- Exact nose structure: nose shape, nose size, nostril shape, bridge height
- Exact mouth structure: lip shape, lip size, lip thickness, mouth width
- Exact facial features positioning: distance between features, feature alignment

AGE PRESERVATION (MANDATORY - EXACT MATCH):
- Exact age appearance: maintain the exact same age look as the uploaded model
- Exact skin characteristics: skin texture, skin tone, skin undertones, complexion
- Exact facial maturity: maintain the same level of facial maturity and age markers
- Do NOT make the model look younger or older - maintain EXACT age appearance

ADDITIONAL PRESERVATION REQUIREMENTS:
- Exact skin tone, skin texture, complexion, undertones, and skin characteristics
- Exact hair: hair color, hair texture, hair style, hair length, hairline, and any highlights or natural variations
- Exact body proportions: height, build, body shape, muscle definition, and physical characteristics
- Exact facial expressions style and natural features
- Exact distinctive characteristics and unique features
- Do NOT beautify, stylize, enhance, or alter the model in ANY way
- The model's identity must remain 100% identical to the original uploaded model image

PRODUCT PRESERVATION:
Place ONLY the given uploaded product (ornament/jewelry) on the model. The product must remain 100% identical to the original product image with NO changes in design, shape, stone layout, metal finish, color, texture, reflections, or micro detailing. Do NOT reinterpret, redraw, enhance, or modify the product in any way.

INTEGRATION:
Ensure natural and physically accurate product fitting on the model with correct scale, proportion, weight placement, and gravity behavior. Match the original lighting interaction between the product and the model's skin for seamless realism.

QUALITY STANDARDS:
The final image must appear as a high-end professional fashion product photography shoot with:
- soft studio lighting
- natural shadow falloff
- balanced highlights
- clean depth separation
- sharp focus on the product and model

STYLE REFERENCE:
Follow the pose, framing, and environmental styling ONLY as described in the style reference below, without changing the product or the model identity.

Use this style reference strictly for framing, mood, and environment (NOT for modifying the product or model):
{prompt_text}
"""

        default_campaign = """CRITICAL MODEL PRESERVATION REQUIREMENTS - MANDATORY:

Create a professional campaign-style image where the uploaded model MUST look EXACTLY the same as the uploaded model image with ZERO changes to:

FACIAL STRUCTURE (MANDATORY - EXACT MATCH):
- Exact facial bone structure: jawline, cheekbones, chin shape, forehead shape
- Exact facial proportions: face width, face length, facial symmetry
- Exact eye structure: eye shape, eye size, eye spacing, eyelid shape, eyebrow shape and position
- Exact nose structure: nose shape, nose size, nostril shape, bridge height
- Exact mouth structure: lip shape, lip size, lip thickness, mouth width
- Exact facial features positioning: distance between features, feature alignment

AGE PRESERVATION (MANDATORY - EXACT MATCH):
- Exact age appearance: maintain the exact same age look as the uploaded model
- Exact skin characteristics: skin texture, skin tone, skin undertones, complexion
- Exact facial maturity: maintain the same level of facial maturity and age markers
- Do NOT make the model look younger or older - maintain EXACT age appearance

ADDITIONAL PRESERVATION REQUIREMENTS:
- Exact skin tone, skin texture, complexion, undertones, and skin characteristics
- Exact hair: hair color, hair texture, hair style, hair length, hairline, and any highlights or natural variations
- Exact body proportions: height, build, body shape, muscle definition, and physical characteristics
- Exact facial expressions style and natural features
- Exact distinctive characteristics and unique features
- Do NOT beautify, stylize, enhance, or alter the model in ANY way
- The model's identity must remain 100% identical to the original uploaded model image

PRODUCT PRESERVATION:
The model is wearing ONLY the given product, keeping the product exactly as it appears in the original product image — no changes in color, shape, or design.

STYLING:
Use a lifestyle or editorial-style background that enhances the brand aesthetic while maintaining focus on the product. 
Ensure cinematic yet natural studio lighting, soft shadows, and high-end magazine-quality realism.

STYLE REFERENCE:
Follow this specific style prompt: {prompt_text}"""

        prompt_templates = {
            "white_background": get_prompt_from_db("white_background_template", default_white_bg),
            "background_replace": get_prompt_from_db("background_replace_template", default_bg_replace),
            "model_image": get_prompt_from_db("model_image_template", default_model),
            "campaign_image": get_prompt_from_db("campaign_image_template", default_campaign),
        }

        # Logger
        import logging
        from celery.utils.log import get_task_logger

        try:
            logger = get_task_logger(__name__)
        except Exception:
            logger = logging.getLogger(__name__)

        product = item.product_images[product_index]

        # Check if product has uploaded_image_path
        if not hasattr(product, 'uploaded_image_path') or not product.uploaded_image_path:
            # Fallback to uploaded_image_url if path is not available
            if hasattr(product, 'uploaded_image_url') and product.uploaded_image_url:
                # Try to download from URL if path doesn't exist
                product_path = None
                try:
                    response = requests.get(
                        product.uploaded_image_url, timeout=10)
                    if response.status_code == 200:
                        # Save temporarily
                        temp_dir = os.path.join(
                            "media", "temp_products", str(collection_id))
                        os.makedirs(temp_dir, exist_ok=True)
                        product_path = os.path.join(
                            temp_dir, f"product_{product_index}_{uuid.uuid4()}.jpg")
                        with open(product_path, "wb") as f:
                            f.write(response.content)
                    else:
                        return {"success": False, "error": f"Could not download product image from URL: {product.uploaded_image_url}"}
                except Exception as download_error:
                    logger.error(
                        f"[JOB {job_id}] Error downloading product image: {download_error}")
                    return {"success": False, "error": f"Could not access product image: {str(download_error)}"}
            else:
                return {"success": False, "error": "Product image path or URL not found."}
        else:
            product_path = product.uploaded_image_path

        if not product_path or not os.path.exists(product_path):
            msg = f"[JOB {job_id}] Product image path does not exist: {product_path}"
            logger.warning(msg)
            print(msg)
            return {"success": False, "error": "Product image path does not exist."}

        with open(product_path, "rb") as f:
            product_bytes = f.read()
        product_b64 = base64.b64encode(product_bytes).decode("utf-8")

        prompt_text = item.generated_prompts.get(prompt_key, "")
        if not prompt_text or not prompt_text.strip():
            return {"success": False, "error": f"Prompt for key '{prompt_key}' is empty."}

        # Build prompt as in bulk generator (reuse templates/logic where possible)
        custom_prompt = prompt_text
        template = prompt_templates.get(prompt_key, "")
        if template:
            custom_prompt = template.format(prompt_text=prompt_text)

        contents = [
            {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}},
            {"inline_data": {"mime_type": "image/jpeg", "data": product_b64}},
            {"text": custom_prompt},
        ]

        config = types.GenerateContentConfig(
            response_modalities=[types.Modality.IMAGE]
        )

        resp = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        if not resp.candidates:
            return {"success": False, "error": "No candidates returned from Gemini API."}

        candidate = resp.candidates[0]
        generated_bytes = None

        if candidate.content and getattr(candidate.content, "parts", None):
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    data = part.inline_data.data
                    generated_bytes = data if isinstance(
                        data, bytes) else base64.b64decode(data)
                    break

        if not generated_bytes:
            return {"success": False, "error": "No image bytes returned from Gemini API."}

        # Save locally
        output_dir = os.path.join(
            "media", "composite_images", str(collection_id))
        os.makedirs(output_dir, exist_ok=True)
        local_path = os.path.join(
            output_dir, f"{uuid.uuid4()}_{prompt_key}.png")

        with open(local_path, "wb") as f:
            f.write(generated_bytes)

        # Upload to Cloudinary
        cloud_upload = cloudinary.uploader.upload(
            local_path,
            folder=f"ai_studio/composite/{collection_id}/{uuid.uuid4()}/",
            use_filename=True,
            unique_filename=False,
            resource_type="image",
        )

        # Reload collection to avoid race conditions from concurrent tasks
        try:
            collection.reload()
        except Exception as reload_error:
            logger.warning(
                f"[JOB {job_id}] Could not reload collection: {reload_error}. Continuing with existing reference.")

        # Re-validate item and product after reload
        if not collection.items or len(collection.items) == 0:
            return {"success": False, "error": "Collection items not found after reload."}

        item = collection.items[0]

        # Validate product_index is still valid
        if not hasattr(item, "product_images") or not item.product_images:
            return {"success": False, "error": "No product images found in collection."}

        if product_index < 0 or product_index >= len(item.product_images):
            return {"success": False, "error": f"Invalid product index {product_index} after reload. Collection has {len(item.product_images)} products."}

        product = item.product_images[product_index]

        # Store result in product
        new_image_data = {
            "type": prompt_key,
            "prompt": prompt_text,
            "local_path": local_path,
            "cloud_url": cloud_upload["secure_url"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model_used": {
                "type": selected_model.get("type"),
                "local": selected_model.get("local"),
                "cloud": selected_model.get("cloud"),
                "name": selected_model.get("name", ""),
            },
        }

        # Ensure generated_images list exists
        if not hasattr(product, 'generated_images') or product.generated_images is None:
            product.generated_images = []

        product.generated_images.append(new_image_data)

        # Explicitly mark the field as modified for MongoEngine
        collection.items[0].product_images[product_index] = product

        # Save with explicit update
        collection.save()

        # Verify save worked
        try:
            collection.reload()
            if collection.items and len(collection.items) > 0:
                item = collection.items[0]
                if hasattr(item, "product_images") and item.product_images and product_index < len(item.product_images):
                    saved_product = item.product_images[product_index]
                    if hasattr(saved_product, 'generated_images') and saved_product.generated_images:
                        if len(saved_product.generated_images) == 0:
                            logger.error(
                                f"[JOB {job_id}] WARNING: Image not saved to collection! product_index={product_index}, prompt_key={prompt_key}")
                            print(
                                f"[JOB {job_id}] WARNING: Image not saved to collection! product_index={product_index}, prompt_key={prompt_key}")
        except Exception as verify_error:
            logger.warning(
                f"[JOB {job_id}] Could not verify save: {verify_error}")

        # Track history (re-use existing utility)
        try:
            from .history_utils import track_project_image_generation

            track_project_image_generation(
                user_id=str(user_id),
                collection_id=str(collection.id),
                image_type=f"project_{prompt_key}",
                image_url=cloud_upload["secure_url"],
                prompt=prompt_text,
                local_path=local_path,
                metadata={
                    "model_used": selected_model.get("type"),
                    "product_url": product.uploaded_image_url,
                    "model_name": selected_model.get("name", ""),
                    "generation_type": prompt_key,
                },
            )
        except Exception as history_error:
            print(
                f"Error tracking project image generation history: {history_error}")

        # Progressive job tracking
        if job_id:
            try:
                # Verify job is still active before tracking (prevents old jobs from adding images)
                job = ImageGenerationJob.objects(job_id=job_id).first()
                if not job:
                    logger.warning(
                        f"[JOB {job_id}] Job not found, skipping job tracking")
                    print(
                        f"[JOB {job_id}] Job not found, skipping job tracking")
                elif job.status not in ["pending", "running"]:
                    logger.warning(
                        f"[JOB {job_id}] Job is {job.status}, not tracking image (job may have been cancelled or completed)")
                    print(
                        f"[JOB {job_id}] Job is {job.status}, not tracking image (job may have been cancelled or completed)")
                else:
                    image_info = {
                        "cloud_url": cloud_upload["secure_url"],
                        "local_path": local_path,
                        "collection_id": str(collection.id),
                        "product_index": product_index,
                        "prompt_key": prompt_key,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    ImageGenerationJob.objects(job_id=job_id).update_one(
                        inc__completed_images=1,
                        push__images=image_info,
                        set__status="running",
                    )

                    # Re-fetch to check completion
                    job = ImageGenerationJob.objects(job_id=job_id).first()
                    if job and job.completed_images >= job.total_images:
                        job.status = "completed"
                        job.save()
            except Exception as job_error:
                print(
                    f"Error updating ImageGenerationJob {job_id}: {job_error}")

        return {
            "success": True,
            "cloud_url": cloud_upload["secure_url"],
            "local_path": local_path,
            "prompt_key": prompt_key,
            "product_index": product_index,
        }

    except Exception as e:
        traceback.print_exc()
        if job_id:
            try:
                job = ImageGenerationJob.objects(job_id=job_id).first()
                if job and job.status != "completed":
                    job.status = "failed"
                    job.error = str(e)
                    job.save()
            except Exception:
                pass
        return {"success": False, "error": str(e)}


def generate_all_product_model_images_background(collection_id, user_id):
    """
    Background function for generating AI images for all product images in a collection.
    This function is called by Celery and doesn't use request object.
    Returns a dict with success status and results.
    """
    import os
    import base64
    import uuid
    import json
    import traceback
    import cloudinary.uploader
    from datetime import datetime
    from google import genai
    from google.genai import types
    from django.conf import settings

    try:
        # ---------------------------
        # 1. Fetch collection and setup
        # ---------------------------
        collection = Collection.objects.get(id=collection_id)
        item = collection.items[0]  # Assuming single-item collection setup

        # Get the selected model from the collection
        if not hasattr(item, 'selected_model') or not item.selected_model:
            return {"success": False, "error": "No model selected. Please select a model first."}

        selected_model = item.selected_model
        model_local_path = selected_model.get("local")
        model_cloud_url = selected_model.get("cloud")

        # Check if model local path exists, if not try to download from cloud URL
        if not model_local_path or not os.path.exists(model_local_path):
            if model_cloud_url:
                # Try to download from cloud URL
                try:
                    print(
                        f"Model local path not found, downloading from cloud URL: {model_cloud_url}")
                    response = requests.get(model_cloud_url, timeout=30)
                    if response.status_code == 200:
                        # Save temporarily
                        temp_dir = os.path.join(
                            "media", "temp_models", str(collection_id))
                        os.makedirs(temp_dir, exist_ok=True)
                        model_local_path = os.path.join(
                            temp_dir, f"model_{uuid.uuid4()}.jpg")
                        with open(model_local_path, "wb") as f:
                            f.write(response.content)
                        print(
                            f"Model downloaded successfully to: {model_local_path}")
                    else:
                        return {"success": False, "error": f"Could not download model image from URL: {model_cloud_url}"}
                except Exception as download_error:
                    print(f"Error downloading model image: {download_error}")
                    return {"success": False, "error": f"Could not access model image: {str(download_error)}"}
            else:
                return {"success": False, "error": "Selected model image not found on server and no cloud URL available."}

        if not hasattr(item, "generated_prompts") or not item.generated_prompts:
            return {"success": False, "error": "No generated prompts found."}

        # ---------------------------
        # 2. Read model image once
        # ---------------------------
        with open(model_local_path, "rb") as f:
            model_bytes = f.read()
        model_b64 = base64.b64encode(model_bytes).decode("utf-8")

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = "gemini-3-pro-image-preview"

        # ---------------------------
        # 3. Prompt templates
        # ---------------------------
        # Get prompt templates from database with fallback
        from .prompt_initializer import get_prompt_from_db

        default_white_bg = """remove the background from the product image and replace it with a clean, elegant white studio background.
        Do NOT modify, alter, or redesign the product in any way — its color, shape, texture, and proportions must remain exactly the same.(important dont change the product image) 
Generate a high-quality product photo on a clean, elegant white studio background. 
The product should appear exactly as in the input image, only placed against a professional white background. 
Ensure balanced, soft studio lighting with natural shadows and realistic reflections. 
Highlight product clarity and detail. 
Follow this specific style prompt: {prompt_text}"""

        default_bg_replace = """Use the provided ornament product image as the hero subject of a professional product photography shot. 
Do NOT redraw, reinterpret, or change the ornament in any way. Do NOT modify the ornament's shape, texture, color, size, material, reflections, orientation, or proportions. The ornament must appear exactly as in the original product image.

CAMERA ANGLE AND PERSPECTIVE (CRITICAL): Follow the EXACT camera angle and perspective described in the style reference below. If the style reference specifies a camera angle (e.g., "elevated diagonal perspective", "overhead 90-degree angle", "flat-lay top-down view"), you MUST use that EXACT angle. Do NOT default to a flat-lay view unless explicitly specified in the style reference.

The ornament must stay clearly visible, well-framed, and the dominant focal point of the composition.

Surround the ornament with carefully chosen supporting elements and objects that enhance its appeal, such as coordinated fabrics, jewelry props, trays, soft decor pieces, or festive details, while keeping the scene clean and premium. 
All added elements must support the ornament, not compete with it.

Place the ornament on a realistic premium surface such as silk fabric, velvet, marble, or textured stone, maintaining full physical contact between the ornament and the surface with grounded shadows directly beneath it (unless the style reference specifies a different placement or arrangement).

Create a studio-quality product photography environment with:
- soft diffused lighting (adjust based on style reference)
- gentle warm highlights
- clean, natural shadow falloff
- high surface and material realism
- crisp focus on the ornament and slightly softer focus on surrounding elements

Background and props may add mood and storytelling but must remain visually secondary to the ornament. 
The ornament must always remain the sharpest, brightest, and most visually dominant element in the frame.

MASTER ANALYSIS FOLLOWING (CRITICAL): If the style prompt below is a comprehensive master theme analysis, you MUST follow it EXACTLY without missing a single detail. The master analysis contains specific information about:
- Exact camera angle and perspective (e.g., "elevated diagonal perspective", "photographed from an overhead 90-degree angle", "flat-lay top-down view") - FOLLOW THIS EXACTLY
- Exact placement and positioning of ornaments (e.g., "rests diagonally", "gracefully drapes", "positioned elegantly beside", "commands attention") - FOLLOW THIS EXACTLY
- Precise lighting conditions (e.g., "soft, warm ambient lighting", "shallow depth of field", "soft diffused top lighting") - FOLLOW THIS EXACTLY
- Specific surface materials and textures (e.g., "light beige, rectangular jewelry box", "soft, neutral surface", "silk fabric, velvet, marble") - FOLLOW THIS EXACTLY
- Exact artistic style and mood (e.g., "sophisticated minimalism", "opulent heritage", "serene luxury") - FOLLOW THIS EXACTLY
- All supporting elements and props mentioned (e.g., flowers, decorative pieces, fabrics, vintage treasure chest, ceremonial fabric) - FOLLOW THIS EXACTLY
- Follow EVERY detail from the master analysis exactly as described - do not generalize or simplify any aspect.

The style reference below contains the EXACT description including camera angle, placement, lighting, materials, and all visual elements. Follow it PRECISELY:
{prompt_text}
"""

        default_model = """CRITICAL MODEL PRESERVATION REQUIREMENTS - MANDATORY:

Use the uploaded model image as the absolute identity reference. The generated model MUST look EXACTLY the same as the uploaded model with ZERO changes to:

FACIAL STRUCTURE (MANDATORY - EXACT MATCH):
- Exact facial bone structure: jawline, cheekbones, chin shape, forehead shape
- Exact facial proportions: face width, face length, facial symmetry
- Exact eye structure: eye shape, eye size, eye spacing, eyelid shape, eyebrow shape and position
- Exact nose structure: nose shape, nose size, nostril shape, bridge height
- Exact mouth structure: lip shape, lip size, lip thickness, mouth width
- Exact facial features positioning: distance between features, feature alignment

AGE PRESERVATION (MANDATORY - EXACT MATCH):
- Exact age appearance: maintain the exact same age look as the uploaded model
- Exact skin characteristics: skin texture, skin tone, skin undertones, complexion
- Exact facial maturity: maintain the same level of facial maturity and age markers
- Do NOT make the model look younger or older - maintain EXACT age appearance

ADDITIONAL PRESERVATION REQUIREMENTS:
- Exact skin tone, skin texture, complexion, undertones, and skin characteristics
- Exact hair: hair color, hair texture, hair style, hair length, hairline, and any highlights or natural variations
- Exact body proportions: height, build, body shape, muscle definition, and physical characteristics
- Exact facial expressions style and natural features
- Exact distinctive characteristics and unique features
- Do NOT beautify, stylize, enhance, or alter the model in ANY way
- The model's identity must remain 100% identical to the original uploaded model image

PRODUCT PRESERVATION:
Place ONLY the given uploaded product (ornament/jewelry) on the model. The product must remain 100% identical to the original product image with NO changes in design, shape, stone layout, metal finish, color, texture, reflections, or micro detailing. Do NOT reinterpret, redraw, enhance, or modify the product in any way.

INTEGRATION:
Ensure natural and physically accurate product fitting on the model with correct scale, proportion, weight placement, and gravity behavior. Match the original lighting interaction between the product and the model's skin for seamless realism.

QUALITY STANDARDS:
The final image must appear as a high-end professional fashion product photography shoot with:
- soft studio lighting
- natural shadow falloff
- balanced highlights
- clean depth separation
- sharp focus on the product and model

STYLE REFERENCE:
Follow the pose, framing, and environmental styling ONLY as described in the style reference below, without changing the product or the model identity.

Use this style reference strictly for framing, mood, and environment (NOT for modifying the product or model):
{prompt_text}
"""

        default_campaign = """CRITICAL MODEL PRESERVATION REQUIREMENTS - MANDATORY:

Create a professional campaign-style image where the uploaded model MUST look EXACTLY the same as the uploaded model image with ZERO changes to:

FACIAL STRUCTURE (MANDATORY - EXACT MATCH):
- Exact facial bone structure: jawline, cheekbones, chin shape, forehead shape
- Exact facial proportions: face width, face length, facial symmetry
- Exact eye structure: eye shape, eye size, eye spacing, eyelid shape, eyebrow shape and position
- Exact nose structure: nose shape, nose size, nostril shape, bridge height
- Exact mouth structure: lip shape, lip size, lip thickness, mouth width
- Exact facial features positioning: distance between features, feature alignment

AGE PRESERVATION (MANDATORY - EXACT MATCH):
- Exact age appearance: maintain the exact same age look as the uploaded model
- Exact skin characteristics: skin texture, skin tone, skin undertones, complexion
- Exact facial maturity: maintain the same level of facial maturity and age markers
- Do NOT make the model look younger or older - maintain EXACT age appearance

ADDITIONAL PRESERVATION REQUIREMENTS:
- Exact skin tone, skin texture, complexion, undertones, and skin characteristics
- Exact hair: hair color, hair texture, hair style, hair length, hairline, and any highlights or natural variations
- Exact body proportions: height, build, body shape, muscle definition, and physical characteristics
- Exact facial expressions style and natural features
- Exact distinctive characteristics and unique features
- Do NOT beautify, stylize, enhance, or alter the model in ANY way
- The model's identity must remain 100% identical to the original uploaded model image

PRODUCT PRESERVATION:
The model is wearing ONLY the given product, keeping the product exactly as it appears in the original product image — no changes in color, shape, or design.

STYLING:
Use a lifestyle or editorial-style background that enhances the brand aesthetic while maintaining focus on the product. 
Ensure cinematic yet natural studio lighting, soft shadows, and high-end magazine-quality realism.

STYLE REFERENCE:
Follow this specific style prompt: {prompt_text}"""

        prompt_templates = {
            "white_background": get_prompt_from_db('white_background_template', default_white_bg),
            "background_replace": get_prompt_from_db('background_replace_template', default_bg_replace),
            "model_image": get_prompt_from_db('model_image_template', default_model),
            "campaign_image": get_prompt_from_db('campaign_image_template', default_campaign),
        }

        # ---------------------------
        # 4. Loop through each product image
        # ---------------------------
        # Initialize logger once for all products and image types
        import logging
        from celery.utils.log import get_task_logger
        try:
            # Try to get Celery task logger if available
            logger = get_task_logger(__name__)
        except Exception:
            # Fallback to standard logger
            logger = logging.getLogger(__name__)

        log_msg = f"[GENERATION] Starting image generation for collection {collection_id} with {len(item.product_images)} product(s)"
        logger.info(log_msg)
        print(log_msg)

        # Validate that all required prompt keys exist
        required_keys = ["white_background",
                         "background_replace", "model_image", "campaign_image"]
        missing_keys = [
            key for key in required_keys if key not in item.generated_prompts]
        if missing_keys:
            log_msg = f"[GENERATION] ⚠️ WARNING: Missing prompt keys in generated_prompts: {missing_keys}. Available keys: {list(item.generated_prompts.keys())}"
            logger.warning(log_msg)
            print(log_msg)
        else:
            log_msg = f"[GENERATION] ✅ All required prompt keys present: {required_keys}"
            logger.info(log_msg)
            print(log_msg)

        for product_idx, product in enumerate(item.product_images, 1):
            product_path = product.uploaded_image_path

            if not os.path.exists(product_path):
                log_msg = f"[PRODUCT {product_idx}] ⚠️ Product image path does not exist: {product_path}"
                logger.warning(log_msg)
                print(log_msg)
                continue

            log_msg = f"[PRODUCT {product_idx}] Starting generation for product: {product.uploaded_image_url}"
            logger.info(log_msg)
            print(log_msg)

            with open(product_path, "rb") as f:
                product_bytes = f.read()
            product_b64 = base64.b64encode(product_bytes).decode("utf-8")

            # Clear any old generated images for this run
            product.generated_images = []

            # ---------------------------
            # 5. Generate images for each prompt
            # ---------------------------
            # Log available prompt keys before generation
            available_keys = list(item.generated_prompts.keys())
            log_msg = f"[PRODUCT {product_idx}] Available prompt keys for generation: {available_keys}"
            logger.info(log_msg)
            print(log_msg)

            # Check specifically for campaign_image
            if "campaign_image" not in item.generated_prompts:
                log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ❌ CRITICAL: campaign_image key NOT FOUND in generated_prompts! Available keys: {available_keys}"
                logger.error(log_msg)
                print(log_msg)
                log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] This product will NOT have a campaign_image generated. This is likely the root cause of the issue."
                logger.error(log_msg)
                print(log_msg)
            else:
                log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ✅ campaign_image key found in generated_prompts, will be generated"
                logger.info(log_msg)
                print(log_msg)
                campaign_prompt = item.generated_prompts.get(
                    "campaign_image", "")
                if not campaign_prompt or not campaign_prompt.strip():
                    log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ⚠️ WARNING: campaign_image key exists but prompt is empty or whitespace only!"
                    logger.warning(log_msg)
                    print(log_msg)

            for key, prompt_text in item.generated_prompts.items():
                # Additional validation: Skip if prompt is empty
                if not prompt_text or not prompt_text.strip():
                    log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ⚠️ WARNING: Skipping {key} because prompt is empty or whitespace only"
                    logger.warning(log_msg)
                    print(log_msg)
                    continue
                try:
                    # Initialize variables for all image types
                    use_master_analysis = False
                    master_analysis_to_use = None
                    theme_angle_shot = None  # Store angle_shot from matched theme image
                    theme_description_only = None  # Store theme_description without angle_shot
                    # Initialize for all types, but only used for background_replace
                    # IMPORTANT: Initialize BEFORE any conditional blocks to avoid UnboundLocalError
                    product_ornament_type = getattr(
                        product, 'ornament_type', None)

                    # Log start of generation for each image type with enhanced logging for campaign_image
                    if key == "campaign_image":
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] 🎬 STARTING CAMPAIGN IMAGE GENERATION"
                        logger.info(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] Prompt length: {len(prompt_text)} chars, Product ornament_type: {product_ornament_type or 'N/A'}"
                        logger.info(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] Prompt preview (first 200 chars): {prompt_text[:200]}..."
                        logger.info(log_msg)
                        print(log_msg)
                    else:
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Starting generation for image type: {key}"
                        logger.info(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Prompt length: {len(prompt_text)} chars, Product ornament_type: {product_ornament_type or 'N/A'}"
                        logger.info(log_msg)
                        print(log_msg)

                    # Special handling ONLY for background_replace: Check if master analysis should be used
                    if key == "background_replace":
                        # Special handling: Use analysis from uploaded_theme_images instead of master analysis
                        # First, map the product image type with the type stored in the analysis
                        import logging
                        from celery.utils.log import get_task_logger
                        try:
                            # Try to get Celery task logger if available
                            logger = get_task_logger(__name__)
                        except Exception:
                            # Fallback to standard logger
                            logger = logging.getLogger(__name__)

                        log_msg = f"[BACKGROUND_REPLACE] Starting theme analysis mapping for product ornament_type: {product_ornament_type}"
                        logger.info(log_msg)
                        print(log_msg)  # Also print for Celery visibility

                        if product_ornament_type:
                            # Check uploaded_theme_images for matching ornament type
                            if hasattr(item, 'uploaded_theme_images') and item.uploaded_theme_images:
                                log_msg = f"[BACKGROUND_REPLACE] Checking {len(item.uploaded_theme_images)} uploaded theme images for matching ornament type"
                                logger.info(log_msg)
                                print(log_msg)
                                for idx, theme_img in enumerate(item.uploaded_theme_images, 1):
                                    log_msg = f"[BACKGROUND_REPLACE] Checking theme image {idx}/{len(item.uploaded_theme_images)}: {getattr(theme_img, 'original_filename', 'unknown')}"
                                    logger.debug(log_msg)
                                    print(log_msg)
                                    # Get the analysis from theme image (should be JSON string)
                                    theme_analysis_json_str = getattr(
                                        theme_img, 'analysis', '').strip()

                                    # Parse JSON analysis to get type and description
                                    import json
                                    import re
                                    theme_analysis_type = None
                                    theme_analysis_main_category = None
                                    theme_analysis_description = None

                                    if theme_analysis_json_str:
                                        try:
                                            theme_analysis_json = json.loads(
                                                theme_analysis_json_str)
                                            if isinstance(theme_analysis_json, dict):
                                                theme_analysis_type = theme_analysis_json.get(
                                                    'type', '')
                                                theme_analysis_description = theme_analysis_json.get(
                                                    'description', '')

                                                # Extract main_category from type format "subcategory(main_category)"
                                                if theme_analysis_type:
                                                    match = re.match(
                                                        r'^.+?\(([^)]+)\)$', theme_analysis_type)
                                                    if match:
                                                        theme_analysis_main_category = match.group(
                                                            1).strip().lower()
                                                        log_msg = f"[BACKGROUND_REPLACE] Extracted main_category from type: {theme_analysis_main_category}"
                                                        logger.debug(log_msg)
                                                        print(log_msg)
                                                    else:
                                                        # If no parentheses, try to extract main category from the type
                                                        main_category_patterns = [
                                                            r'\b(necklace|choker|pendant|chain|haram)\b',
                                                            r'\b(earring|earrings|stud|jhumka)\b',
                                                            r'\b(bracelet|bangle|cuff)\b',
                                                            r'\b(ring|bands?)\b',
                                                            r'\b(anklet)\b',
                                                            r'\b(brooch)\b'
                                                        ]
                                                        for pattern in main_category_patterns:
                                                            match = re.search(
                                                                pattern, theme_analysis_type, re.IGNORECASE)
                                                            if match:
                                                                theme_analysis_main_category = match.group(
                                                                    1).lower()
                                                                if theme_analysis_main_category.endswith('s') and theme_analysis_main_category != 'earrings':
                                                                    theme_analysis_main_category = theme_analysis_main_category[
                                                                        :-1]
                                                                break
                                        except (json.JSONDecodeError, TypeError):
                                            # Not JSON, treat as plain text
                                            pass

                                    # Also check if theme image has ornament_type stored (for backward compatibility)
                                    theme_ornament_type = getattr(
                                        theme_img, 'ornament_type', None)

                                    # Use theme_analysis_main_category for matching (the main highlighted ornament)
                                    # If not available, fall back to theme_analysis_type or theme_ornament_type
                                    type_to_match = None
                                    if theme_analysis_main_category:
                                        type_to_match = theme_analysis_main_category
                                    elif theme_analysis_type:
                                        type_to_match = theme_analysis_type
                                    elif theme_ornament_type:
                                        type_to_match = theme_ornament_type

                                    if type_to_match and type_to_match.strip():
                                        # Normalize both types for comparison
                                        normalized_product_type, product_base_type = _normalize_ornament_type(
                                            product_ornament_type)
                                        normalized_theme_type, _ = _normalize_ornament_type(
                                            type_to_match)

                                        # Also get product's main category for matching
                                        product_category = _get_ornament_category(
                                            product_ornament_type)

                                        log_msg = f"[BACKGROUND_REPLACE] Comparing - Product: {product_ornament_type} (category: {product_category}, base: {product_base_type}) vs Theme: {type_to_match} (main_category: {theme_analysis_main_category})"
                                        logger.debug(log_msg)
                                        print(log_msg)

                                        # Check for match (exact or similar)
                                        # Match using main_category if available, otherwise use full type
                                        match_found = False

                                        if theme_analysis_main_category:
                                            # Match product's main category with theme's main category
                                            if product_category and product_category.lower() == theme_analysis_main_category:
                                                match_found = True
                                                log_msg = f"[BACKGROUND_REPLACE] ✅ MATCH FOUND: Product category '{product_category}' == Theme main_category '{theme_analysis_main_category}'"
                                                logger.info(log_msg)
                                                print(log_msg)
                                            elif product_base_type and product_base_type.lower() == theme_analysis_main_category:
                                                match_found = True
                                                log_msg = f"[BACKGROUND_REPLACE] ✅ MATCH FOUND: Product base_type '{product_base_type}' == Theme main_category '{theme_analysis_main_category}'"
                                                logger.info(log_msg)
                                                print(log_msg)
                                            elif normalized_product_type and theme_analysis_main_category in normalized_product_type:
                                                match_found = True
                                                log_msg = f"[BACKGROUND_REPLACE] ✅ MATCH FOUND: Theme main_category '{theme_analysis_main_category}' found in product type '{normalized_product_type}'"
                                                logger.info(log_msg)
                                                print(log_msg)

                                        # Also check exact/partial match with full types
                                        if not match_found and normalized_product_type and normalized_theme_type:
                                            # Exact match
                                            if normalized_product_type == normalized_theme_type:
                                                match_found = True
                                                log_msg = f"[BACKGROUND_REPLACE] ✅ MATCH FOUND: Exact match - Product '{normalized_product_type}' == Theme '{normalized_theme_type}'"
                                                logger.info(log_msg)
                                                print(log_msg)
                                            # Check if product type is contained in theme type or vice versa
                                            elif normalized_product_type in normalized_theme_type or normalized_theme_type in normalized_product_type:
                                                match_found = True
                                                log_msg = f"[BACKGROUND_REPLACE] ✅ MATCH FOUND: Partial match - Product '{normalized_product_type}' contains/contained in Theme '{normalized_theme_type}'"
                                                logger.info(log_msg)
                                                print(log_msg)

                                        if match_found:
                                            use_master_analysis = True
                                            # Get theme_description and angle_shot separately from the theme image
                                            theme_description_from_img = getattr(
                                                theme_img, 'theme_description', None)
                                            angle_shot_from_img = getattr(
                                                theme_img, 'angle_shot', None)

                                            log_msg = f"[BACKGROUND_REPLACE] 🔍 EXTRACTING THEME DATA: Product '{product_ornament_type}' matched with theme '{type_to_match}'"
                                            logger.info(log_msg)
                                            print(log_msg)

                                            log_msg = f"[BACKGROUND_REPLACE] 📋 Theme Image Data - theme_description_from_img: {len(theme_description_from_img) if theme_description_from_img else 0} chars, angle_shot_from_img: '{angle_shot_from_img if angle_shot_from_img else 'N/A'}'"
                                            logger.info(log_msg)
                                            print(log_msg)

                                            # Use the description from the analysis (after type mapping)
                                            if theme_analysis_description:
                                                # If we have separate theme_description and angle_shot, use them
                                                if theme_description_from_img and theme_description_from_img.strip():
                                                    theme_description_only = theme_description_from_img.strip()
                                                    log_msg = f"[BACKGROUND_REPLACE] ✅ Using theme_description from theme image ({len(theme_description_only)} chars)"
                                                    logger.info(log_msg)
                                                    print(log_msg)
                                                else:
                                                    # Fallback: use theme_analysis_description as theme_description_only
                                                    theme_description_only = theme_analysis_description.strip()
                                                    log_msg = f"[BACKGROUND_REPLACE] ⚠️ Using theme_analysis_description as fallback ({len(theme_description_only)} chars)"
                                                    logger.info(log_msg)
                                                    print(log_msg)

                                                # Get angle_shot from theme image if available
                                                if angle_shot_from_img and angle_shot_from_img.strip():
                                                    theme_angle_shot = angle_shot_from_img.strip()
                                                    log_msg = f"[BACKGROUND_REPLACE] ✅ Using angle_shot from theme image: '{theme_angle_shot}'"
                                                    logger.info(log_msg)
                                                    print(log_msg)
                                                else:
                                                    log_msg = f"[BACKGROUND_REPLACE] 🔍 Angle_shot not in theme image, extracting from description..."
                                                    logger.info(log_msg)
                                                    print(log_msg)
                                                    # Try to extract angle_shot from theme_analysis_description first
                                                    angle_patterns = [
                                                        r'(?:photographed from|shot from|captured from|from)\s+(?:an?\s+)?(?:elevated\s+)?(?:diagonal|slight|oblique|overhead|top[- ]down|flat[- ]lay|90[- ]degree|ninety[- ]degree)\s*(?:angle|view|shot|perspective)?',
                                                        r'(?:elevated\s+)?(?:diagonal|slight|oblique|overhead|top[- ]down|flat[- ]lay|90[- ]degree|ninety[- ]degree)\s+(?:angle|view|shot|perspective)',
                                                    ]
                                                    for pattern in angle_patterns:
                                                        match = re.search(
                                                            pattern, theme_analysis_description, re.IGNORECASE)
                                                        if match:
                                                            theme_angle_shot = match.group(
                                                                0).strip()
                                                            log_msg = f"[BACKGROUND_REPLACE] ✅ Extracted angle_shot from theme_analysis_description: '{theme_angle_shot}'"
                                                            logger.info(
                                                                log_msg)
                                                            print(log_msg)
                                                            break
                                                    # If still not found, try extracting from theme_description_only
                                                    if not theme_angle_shot and theme_description_only:
                                                        log_msg = f"[BACKGROUND_REPLACE] 🔍 Trying to extract angle_shot from theme_description_only..."
                                                        logger.info(log_msg)
                                                        print(log_msg)
                                                        for pattern in angle_patterns:
                                                            match = re.search(
                                                                pattern, theme_description_only, re.IGNORECASE)
                                                            if match:
                                                                theme_angle_shot = match.group(
                                                                    0).strip()
                                                                log_msg = f"[BACKGROUND_REPLACE] ✅ Extracted angle_shot from theme_description_only: '{theme_angle_shot}'"
                                                                logger.info(
                                                                    log_msg)
                                                                print(log_msg)
                                                                # Remove the angle information from theme_description_only to avoid duplication
                                                                theme_description_only_before = theme_description_only
                                                                theme_description_only = re.sub(
                                                                    re.escape(match.group(0)), '', theme_description_only, flags=re.IGNORECASE
                                                                ).strip()
                                                                # Clean up any extra spaces or punctuation
                                                                theme_description_only = re.sub(
                                                                    r'\s+', ' ', theme_description_only).strip()
                                                                theme_description_only = re.sub(
                                                                    r'\s*,\s*', ', ', theme_description_only)
                                                                log_msg = f"[BACKGROUND_REPLACE] 🧹 Cleaned theme_description_only: removed angle info (before: {len(theme_description_only_before)} chars, after: {len(theme_description_only)} chars)"
                                                                logger.info(
                                                                    log_msg)
                                                                print(log_msg)
                                                                break
                                                    if not theme_angle_shot:
                                                        log_msg = f"[BACKGROUND_REPLACE] ⚠️ Could not extract angle_shot from description"
                                                        logger.warning(log_msg)
                                                        print(log_msg)

                                                # Combine theme_description and angle_shot for the prompt
                                                if theme_angle_shot and theme_angle_shot.strip():
                                                    # Convert angle_shot from underscore format to readable format
                                                    angle_shot_readable = theme_angle_shot.replace(
                                                        '_', ' ').replace('-', ' ')
                                                    master_analysis_to_use = f"{theme_description_only} The overall angle shot is {angle_shot_readable}."
                                                    log_msg = f"[BACKGROUND_REPLACE] 🔗 COMBINING: theme_description ({len(theme_description_only)} chars) + angle_shot ('{angle_shot_readable}')"
                                                    logger.info(log_msg)
                                                    print(log_msg)
                                                else:
                                                    master_analysis_to_use = theme_description_only
                                                    log_msg = f"[BACKGROUND_REPLACE] 🔗 COMBINING: Using theme_description only ({len(theme_description_only)} chars) - no angle_shot available"
                                                    logger.info(log_msg)
                                                    print(log_msg)

                                                log_msg1 = f"[BACKGROUND_REPLACE] ✅ THEME ANALYSIS MAPPED: Product '{product_ornament_type}' → Theme '{theme_analysis_type}' (main_category: {theme_analysis_main_category})"
                                                log_msg2 = f"[BACKGROUND_REPLACE] 📊 FINAL MAPPING - theme_description: {len(theme_description_only)} chars, angle_shot: '{theme_angle_shot if theme_angle_shot else 'N/A'}', combined prompt: {len(master_analysis_to_use)} chars"
                                                log_msg3 = f"[BACKGROUND_REPLACE] 📝 Combined prompt preview: {master_analysis_to_use[:300]}..."
                                                log_msg4 = f"[BACKGROUND_REPLACE] 📝 Full combined prompt: {master_analysis_to_use}"
                                                logger.info(log_msg1)
                                                logger.info(log_msg2)
                                                logger.info(log_msg3)
                                                logger.debug(log_msg4)
                                                print(log_msg1)
                                                print(log_msg2)
                                                print(log_msg3)
                                                print(log_msg4)
                                            else:
                                                # Fallback to theme_description if analysis not available
                                                if theme_description_from_img and theme_description_from_img.strip():
                                                    theme_description_only = theme_description_from_img.strip()
                                                    log_msg = f"[BACKGROUND_REPLACE] ⚠️ FALLBACK: Using theme_description_from_img ({len(theme_description_only)} chars) - no theme_analysis_description available"
                                                    logger.warning(log_msg)
                                                    print(log_msg)
                                                    if angle_shot_from_img and angle_shot_from_img.strip():
                                                        theme_angle_shot = angle_shot_from_img.strip()
                                                        angle_shot_readable = theme_angle_shot.replace(
                                                            '_', ' ').replace('-', ' ')
                                                        master_analysis_to_use = f"{theme_description_only} The overall angle shot is {angle_shot_readable}."
                                                        log_msg = f"[BACKGROUND_REPLACE] 🔗 FALLBACK COMBINING: theme_description ({len(theme_description_only)} chars) + angle_shot ('{angle_shot_readable}')"
                                                        logger.info(log_msg)
                                                        print(log_msg)
                                                    else:
                                                        master_analysis_to_use = theme_description_only
                                                        log_msg = f"[BACKGROUND_REPLACE] 🔗 FALLBACK COMBINING: Using theme_description only ({len(theme_description_only)} chars) - no angle_shot"
                                                        logger.info(log_msg)
                                                        print(log_msg)
                                                    log_msg = f"[BACKGROUND_REPLACE] 📊 FALLBACK FINAL - combined prompt: {len(master_analysis_to_use)} chars, preview: {master_analysis_to_use[:200]}..."
                                                    logger.info(log_msg)
                                                    print(log_msg)
                                                else:
                                                    master_analysis_to_use = theme_analysis_json_str
                                                    log_msg = f"[BACKGROUND_REPLACE] ⚠️ Using raw theme_analysis_json_str as fallback for product '{product_ornament_type}' ({len(master_analysis_to_use)} chars)"
                                                    logger.warning(log_msg)
                                                    print(log_msg)
                                            print(
                                                f"✅ Theme image analysis match found for {product_ornament_type} (matched with {type_to_match}) - using description and angle_shot from analysis")
                                            break

                                    # Also check if analysis text contains the product ornament type (for backward compatibility)
                                    if theme_analysis_json_str and _check_ornament_type_match(product_ornament_type, theme_analysis_json_str):
                                        use_master_analysis = True
                                        log_msg = f"[BACKGROUND_REPLACE] 🔍 TEXT MATCH FOUND: Product '{product_ornament_type}' matched via analysis text"
                                        logger.info(log_msg)
                                        print(log_msg)

                                        # Get theme_description and angle_shot separately from the theme image
                                        theme_description_from_img = getattr(
                                            theme_img, 'theme_description', None)
                                        angle_shot_from_img = getattr(
                                            theme_img, 'angle_shot', None)

                                        log_msg = f"[BACKGROUND_REPLACE] 📋 TEXT MATCH - Theme Image Data - theme_description_from_img: {len(theme_description_from_img) if theme_description_from_img else 0} chars, angle_shot_from_img: '{angle_shot_from_img if angle_shot_from_img else 'N/A'}'"
                                        logger.info(log_msg)
                                        print(log_msg)

                                        # Use the description from the analysis if it's JSON, otherwise use full analysis
                                        if theme_analysis_description:
                                            # If we have separate theme_description and angle_shot, use them
                                            if theme_description_from_img and theme_description_from_img.strip():
                                                theme_description_only = theme_description_from_img.strip()
                                                log_msg = f"[BACKGROUND_REPLACE] ✅ TEXT MATCH: Using theme_description from theme image ({len(theme_description_only)} chars)"
                                                logger.info(log_msg)
                                                print(log_msg)
                                            else:
                                                theme_description_only = theme_analysis_description.strip()
                                                log_msg = f"[BACKGROUND_REPLACE] ⚠️ TEXT MATCH: Using theme_analysis_description as fallback ({len(theme_description_only)} chars)"
                                                logger.info(log_msg)
                                                print(log_msg)

                                            # Get angle_shot from theme image if available
                                            if angle_shot_from_img and angle_shot_from_img.strip():
                                                theme_angle_shot = angle_shot_from_img.strip()
                                                log_msg = f"[BACKGROUND_REPLACE] ✅ TEXT MATCH: Using angle_shot from theme image: '{theme_angle_shot}'"
                                                logger.info(log_msg)
                                                print(log_msg)
                                            else:
                                                log_msg = f"[BACKGROUND_REPLACE] 🔍 TEXT MATCH: Angle_shot not in theme image, extracting from description..."
                                                logger.info(log_msg)
                                                print(log_msg)
                                                # Try to extract angle_shot from theme_analysis_description first
                                                angle_patterns = [
                                                    r'(?:photographed from|shot from|captured from|from)\s+(?:an?\s+)?(?:elevated\s+)?(?:diagonal|slight|oblique|overhead|top[- ]down|flat[- ]lay|90[- ]degree|ninety[- ]degree)\s*(?:angle|view|shot|perspective)?',
                                                    r'(?:elevated\s+)?(?:diagonal|slight|oblique|overhead|top[- ]down|flat[- ]lay|90[- ]degree|ninety[- ]degree)\s+(?:angle|view|shot|perspective)',
                                                ]
                                                for pattern in angle_patterns:
                                                    match = re.search(
                                                        pattern, theme_analysis_description, re.IGNORECASE)
                                                    if match:
                                                        theme_angle_shot = match.group(
                                                            0).strip()
                                                        log_msg = f"[BACKGROUND_REPLACE] ✅ TEXT MATCH: Extracted angle_shot from theme_analysis_description: '{theme_angle_shot}'"
                                                        logger.info(log_msg)
                                                        print(log_msg)
                                                        break
                                                # If still not found, try extracting from theme_description_only
                                                if not theme_angle_shot and theme_description_only:
                                                    log_msg = f"[BACKGROUND_REPLACE] 🔍 TEXT MATCH: Trying to extract angle_shot from theme_description_only..."
                                                    logger.info(log_msg)
                                                    print(log_msg)
                                                    for pattern in angle_patterns:
                                                        match = re.search(
                                                            pattern, theme_description_only, re.IGNORECASE)
                                                        if match:
                                                            theme_angle_shot = match.group(
                                                                0).strip()
                                                            log_msg = f"[BACKGROUND_REPLACE] ✅ TEXT MATCH: Extracted angle_shot from theme_description_only: '{theme_angle_shot}'"
                                                            logger.info(
                                                                log_msg)
                                                            print(log_msg)
                                                            # Remove the angle information from theme_description_only to avoid duplication
                                                            theme_description_only_before = theme_description_only
                                                            theme_description_only = re.sub(
                                                                re.escape(match.group(0)), '', theme_description_only, flags=re.IGNORECASE
                                                            ).strip()
                                                            # Clean up any extra spaces or punctuation
                                                            theme_description_only = re.sub(
                                                                r'\s+', ' ', theme_description_only).strip()
                                                            theme_description_only = re.sub(
                                                                r'\s*,\s*', ', ', theme_description_only)
                                                            log_msg = f"[BACKGROUND_REPLACE] 🧹 TEXT MATCH: Cleaned theme_description_only: removed angle info (before: {len(theme_description_only_before)} chars, after: {len(theme_description_only)} chars)"
                                                            logger.info(
                                                                log_msg)
                                                            print(log_msg)
                                                            break
                                                if not theme_angle_shot:
                                                    log_msg = f"[BACKGROUND_REPLACE] ⚠️ TEXT MATCH: Could not extract angle_shot from description"
                                                    logger.warning(log_msg)
                                                    print(log_msg)

                                            # Combine theme_description and angle_shot for the prompt
                                            if theme_angle_shot and theme_angle_shot.strip():
                                                angle_shot_readable = theme_angle_shot.replace(
                                                    '_', ' ').replace('-', ' ')
                                                master_analysis_to_use = f"{theme_description_only} The overall angle shot is {angle_shot_readable}."
                                                log_msg = f"[BACKGROUND_REPLACE] 🔗 TEXT MATCH COMBINING: theme_description ({len(theme_description_only)} chars) + angle_shot ('{angle_shot_readable}')"
                                                logger.info(log_msg)
                                                print(log_msg)
                                            else:
                                                master_analysis_to_use = theme_description_only
                                                log_msg = f"[BACKGROUND_REPLACE] 🔗 TEXT MATCH COMBINING: Using theme_description only ({len(theme_description_only)} chars) - no angle_shot"
                                                logger.info(log_msg)
                                                print(log_msg)

                                            log_msg1 = f"[BACKGROUND_REPLACE] ✅ THEME ANALYSIS MAPPED (via text match): Product '{product_ornament_type}' → Theme analysis text"
                                            log_msg2 = f"[BACKGROUND_REPLACE] 📊 TEXT MATCH FINAL - theme_description: {len(theme_description_only)} chars, angle_shot: '{theme_angle_shot if theme_angle_shot else 'N/A'}', combined prompt: {len(master_analysis_to_use)} chars"
                                            log_msg3 = f"[BACKGROUND_REPLACE] 📝 TEXT MATCH Combined prompt preview: {master_analysis_to_use[:300]}..."
                                            log_msg4 = f"[BACKGROUND_REPLACE] 📝 TEXT MATCH Full combined prompt: {master_analysis_to_use}"
                                            logger.info(log_msg1)
                                            logger.info(log_msg2)
                                            logger.info(log_msg3)
                                            logger.debug(log_msg4)
                                            print(log_msg1)
                                            print(log_msg2)
                                            print(log_msg3)
                                            print(log_msg4)
                                        else:
                                            master_analysis_to_use = theme_analysis_json_str.strip()
                                            log_msg = f"[BACKGROUND_REPLACE] ⚠️ Using raw theme_analysis_json_str for product '{product_ornament_type}' (no description extracted)"
                                            logger.warning(log_msg)
                                            print(log_msg)
                                        print(
                                            f"✅ Theme image analysis match found for {product_ornament_type} (matched via analysis text) - using description and angle_shot from analysis")
                                        break

                            # Fallback: If no match found in uploaded_theme_images, check master analysis
                            if not use_master_analysis:
                                log_msg = f"[BACKGROUND_REPLACE] No match found in uploaded_theme_images for product '{product_ornament_type}', checking master_analyses as fallback"
                                logger.info(log_msg)
                                print(log_msg)
                                # Check for master analysis in theme or background categories
                                for category in ['theme', 'background']:
                                    if (hasattr(item, 'master_analyses') and
                                        item.master_analyses and
                                        category in item.master_analyses and
                                        item.master_analyses[category] and
                                            item.master_analyses[category].strip()):

                                        master_analysis = item.master_analyses[category].strip(
                                        )

                                        # Check if product ornament type matches master analysis
                                        if _check_ornament_type_match(product_ornament_type, master_analysis):
                                            use_master_analysis = True
                                            # For theme category, extract description from JSON if stored as JSON
                                            if category == 'theme':
                                                try:
                                                    master_analysis_json = json.loads(
                                                        master_analysis)
                                                    if isinstance(master_analysis_json, dict) and 'description' in master_analysis_json:
                                                        master_analysis_to_use = master_analysis_json['description'].strip(
                                                        )
                                                        log_msg = f"[BACKGROUND_REPLACE] ✅ MASTER ANALYSIS MAPPED (fallback): Product '{product_ornament_type}' → Theme master analysis (extracted description from JSON)"
                                                        logger.info(log_msg)
                                                        print(log_msg)
                                                    else:
                                                        master_analysis_to_use = master_analysis
                                                        log_msg = f"[BACKGROUND_REPLACE] ✅ MASTER ANALYSIS MAPPED (fallback): Product '{product_ornament_type}' → Theme master analysis (plain text)"
                                                        logger.info(log_msg)
                                                        print(log_msg)
                                                except (json.JSONDecodeError, TypeError):
                                                    master_analysis_to_use = master_analysis
                                                    log_msg = f"[BACKGROUND_REPLACE] ✅ MASTER ANALYSIS MAPPED (fallback): Product '{product_ornament_type}' → Theme master analysis (not JSON, using as-is)"
                                                    logger.info(log_msg)
                                                    print(log_msg)
                                            else:
                                                master_analysis_to_use = master_analysis
                                            product_category = _get_ornament_category(
                                                product_ornament_type)
                                            log_msg = f"[BACKGROUND_REPLACE] Using master analysis from '{category}' category ({len(master_analysis_to_use)} chars) for product '{product_ornament_type}'"
                                            logger.info(log_msg)
                                            print(log_msg)
                                            print(
                                                f"✅ Master analysis match found for {product_ornament_type} (category: {product_category}) in {category} category (fallback)")
                                            break

                    # Build the prompt
                    if key == "background_replace":
                        # Special handling for background_replace only
                        if use_master_analysis and master_analysis_to_use:
                            # Use description from uploaded_theme_images analysis with the background_replace template
                            # The description includes theme description and angle shot (after type mapping)
                            # CRITICAL: The product image will NOT be changed - only the background will be replaced
                            template = prompt_templates.get(key, "")
                            if template:
                                # Format the template with description as the prompt_text
                                # This ensures the description is followed exactly while keeping product unchanged
                                custom_prompt = template.format(
                                    prompt_text=master_analysis_to_use)

                                log_msg1 = f"[BACKGROUND_REPLACE] ✅ FINAL PROMPT GENERATION: Using theme analysis for product '{product_ornament_type}'"
                                log_msg2 = f"[BACKGROUND_REPLACE] 📏 PROMPT SIZES - master_analysis_to_use: {len(master_analysis_to_use)} chars, final custom_prompt: {len(custom_prompt)} chars"
                                log_msg3 = f"[BACKGROUND_REPLACE] 📝 MASTER ANALYSIS CONTENT: {master_analysis_to_use}"
                                log_msg4 = f"[BACKGROUND_REPLACE] 📝 FINAL CUSTOM PROMPT PREVIEW: {custom_prompt[:400]}..."
                                log_msg5 = f"[BACKGROUND_REPLACE] 📝 FULL FINAL CUSTOM PROMPT: {custom_prompt}"

                                logger.info(log_msg1)
                                logger.info(log_msg2)
                                logger.info(log_msg3)
                                logger.info(log_msg4)
                                logger.debug(log_msg5)
                                print(log_msg1)
                                print(log_msg2)
                                print(log_msg3)
                                print(log_msg4)
                                print(log_msg5)
                                print(
                                    f"🎨 Using full theme image analysis for {product_ornament_type} (background_replace) - product will remain unchanged")
                            else:
                                custom_prompt = master_analysis_to_use
                                log_msg = f"[BACKGROUND_REPLACE] ⚠️ No template found for '{key}', using theme analysis directly"
                                logger.warning(log_msg)
                                print(log_msg)
                        else:
                            # This is background_replace but no theme analysis match found
                            # Use the regular generated prompt
                            if product_ornament_type:
                                log_msg = f"[BACKGROUND_REPLACE] ⚠️ No theme analysis match found for product '{product_ornament_type}', using regular generated prompt"
                                logger.info(log_msg)
                                print(log_msg)
                            template = prompt_templates.get(key, "")
                            if template:
                                custom_prompt = template.format(
                                    prompt_text=prompt_text)
                            else:
                                custom_prompt = prompt_text
                    else:
                        # For white_background, model_image, and campaign_image: Use regular prompt flow
                        # No special theme matching logic - generate as before (unchanged behavior)
                        template = prompt_templates.get(key, "")
                        if template:
                            custom_prompt = template.format(
                                prompt_text=prompt_text)
                            if key == "campaign_image":
                                log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] 📝 Using template for campaign_image, final prompt length: {len(custom_prompt)} chars"
                                logger.info(log_msg)
                                print(log_msg)
                                log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] 📝 Final prompt preview (first 300 chars): {custom_prompt[:300]}..."
                                logger.info(log_msg)
                                print(log_msg)
                        else:
                            custom_prompt = prompt_text
                            if key == "campaign_image":
                                log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ⚠️ No template found for campaign_image, using raw prompt_text, length: {len(custom_prompt)} chars"
                                logger.warning(log_msg)
                                print(log_msg)

                    contents = [
                        {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}},
                        {"inline_data": {"mime_type": "image/jpeg", "data": product_b64}},
                        {"text": custom_prompt},
                    ]

                    if key == "campaign_image":
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] 🚀 Calling Gemini API for campaign image generation"
                        logger.info(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] Model: {model_name}, Contents: {len(contents)} parts (model image, product image, prompt)"
                        logger.info(log_msg)
                        print(log_msg)

                    config = types.GenerateContentConfig(
                        response_modalities=[types.Modality.IMAGE]
                    )

                    try:
                        resp = client.models.generate_content(
                            model=model_name, contents=contents, config=config
                        )
                        if key == "campaign_image":
                            log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ✅ Gemini API call successful, processing response"
                            logger.info(log_msg)
                            print(log_msg)
                    except Exception as api_error:
                        if key == "campaign_image":
                            log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ❌ ERROR calling Gemini API: {str(api_error)}"
                            logger.error(log_msg)
                            print(log_msg)
                            traceback.print_exc()
                        raise  # Re-raise to be caught by outer exception handler

                    # Validate response and candidate
                    if not resp.candidates or len(resp.candidates) == 0:
                        error_msg = f"⚠️ No candidates returned from Gemini API for {key} of {product.uploaded_image_url}"
                        if key == "campaign_image":
                            log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ❌ CRITICAL ERROR: {error_msg}"
                            logger.error(log_msg)
                            print(log_msg)
                        else:
                            print(error_msg)
                        continue

                    candidate = resp.candidates[0]
                    generated_bytes = None

                    # Log processing for all image types
                    log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Processing response candidates, count: {len(resp.candidates)}"
                    logger.info(log_msg)
                    print(log_msg)

                    # Check finish_reason first to handle PROHIBITED_CONTENT cases
                    finish_reason = getattr(candidate, 'finish_reason', None)
                    if finish_reason:
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ⚠️ Candidate finish_reason: {finish_reason}"
                        logger.warning(log_msg)
                        print(log_msg)

                        # Handle PROHIBITED_CONTENT case - Gemini blocked the content due to safety filters
                        # Check both string representation and enum value
                        is_prohibited = (
                            "PROHIBITED_CONTENT" in str(finish_reason) or
                            (hasattr(types.FinishReason, 'PROHIBITED_CONTENT') and
                             finish_reason == types.FinishReason.PROHIBITED_CONTENT)
                        )
                        if is_prohibited:
                            error_msg = f"🚫 Content generation blocked by Gemini safety filters for {key} of {product.uploaded_image_url}"
                            log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ❌ SAFETY FILTER BLOCKED: {error_msg}"
                            logger.error(log_msg)
                            print(log_msg)

                            # Log safety ratings if available
                            if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                                log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Safety ratings: {candidate.safety_ratings}"
                                logger.error(log_msg)
                                print(log_msg)

                            # Log prompt feedback if available
                            if hasattr(resp, 'prompt_feedback') and resp.prompt_feedback:
                                log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Prompt feedback: {resp.prompt_feedback}"
                                logger.error(log_msg)
                                print(log_msg)

                            log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ⚠️ Skipping {key} generation due to safety filter. Continuing with other image types..."
                            logger.warning(log_msg)
                            print(log_msg)
                            continue

                    # Check safety ratings for all cases
                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ⚠️ Candidate safety_ratings: {candidate.safety_ratings}"
                        logger.warning(log_msg)
                        print(log_msg)

                    # Check if candidate.content exists
                    if not candidate.content:
                        error_msg = f"⚠️ Candidate content is None for {key} of {product.uploaded_image_url}"
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ❌ CRITICAL ERROR: {error_msg}"
                        logger.error(log_msg)
                        print(log_msg)

                        # Log detailed diagnostic information
                        if finish_reason:
                            log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Finish reason: {finish_reason}"
                            logger.error(log_msg)
                            print(log_msg)
                        if hasattr(candidate, 'safety_ratings'):
                            log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Safety ratings: {candidate.safety_ratings}"
                            logger.error(log_msg)
                            print(log_msg)
                        if hasattr(resp, 'prompt_feedback'):
                            log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Prompt feedback: {resp.prompt_feedback}"
                            logger.error(log_msg)
                            print(log_msg)

                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ⚠️ Skipping {key} generation. Continuing with other image types..."
                        logger.warning(log_msg)
                        print(log_msg)
                        continue

                    # Check if candidate.content.parts exists
                    if not hasattr(candidate.content, 'parts') or not candidate.content.parts:
                        error_msg = f"⚠️ Candidate content has no parts for {key} of {product.uploaded_image_url}"
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ❌ CRITICAL ERROR: {error_msg}"
                        logger.error(log_msg)
                        print(log_msg)
                        continue

                    for part in candidate.content.parts:
                        if part.inline_data and part.inline_data.data:
                            data = part.inline_data.data
                            generated_bytes = data if isinstance(
                                data, bytes) else base64.b64decode(data)
                            log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ✅ Image data extracted, size: {len(generated_bytes)} bytes"
                            logger.info(log_msg)
                            print(log_msg)
                            break

                    if not generated_bytes:
                        error_msg = f"⚠️ No image returned for {key} of {product.uploaded_image_url}"
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] ❌ CRITICAL ERROR: {error_msg}"
                        logger.error(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Debug: candidate.content.parts count: {len(candidate.content.parts) if candidate.content and hasattr(candidate.content, 'parts') else 'N/A'}"
                        logger.error(log_msg)
                        print(log_msg)
                        # Log each part type for debugging
                        if candidate.content and hasattr(candidate.content, 'parts'):
                            for idx, part in enumerate(candidate.content.parts):
                                part_type = type(part).__name__
                                has_inline_data = hasattr(
                                    part, 'inline_data') and part.inline_data
                                log_msg = f"[PRODUCT {product_idx}][{key.upper()}] Debug: Part {idx}: type={part_type}, has_inline_data={has_inline_data}"
                                logger.error(log_msg)
                                print(log_msg)
                        continue

                    # ---------------------------
                    # 6. Save locally
                    # ---------------------------
                    output_dir = os.path.join(
                        "media", "composite_images", str(collection_id))
                    os.makedirs(output_dir, exist_ok=True)
                    local_path = os.path.join(
                        output_dir, f"{uuid.uuid4()}_{key}.png")

                    if key == "campaign_image":
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] 💾 Saving image locally to: {local_path}"
                        logger.info(log_msg)
                        print(log_msg)

                    with open(local_path, "wb") as f:
                        f.write(generated_bytes)

                    if key == "campaign_image":
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ✅ Image saved locally successfully"
                        logger.info(log_msg)
                        print(log_msg)

                    # ---------------------------
                    # 7. Upload to Cloudinary
                    # ---------------------------
                    if key == "campaign_image":
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ☁️ Uploading to Cloudinary..."
                        logger.info(log_msg)
                        print(log_msg)

                    try:
                        cloud_upload = cloudinary.uploader.upload(
                            local_path,
                            folder=f"ai_studio/composite/{collection_id}/{uuid.uuid4()}/",
                            use_filename=True,
                            unique_filename=False,
                            resource_type="image",
                        )
                        if key == "campaign_image":
                            log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ✅ Cloudinary upload successful, URL: {cloud_upload.get('secure_url', 'N/A')}"
                            logger.info(log_msg)
                            print(log_msg)
                    except Exception as cloud_error:
                        if key == "campaign_image":
                            log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ❌ ERROR uploading to Cloudinary: {str(cloud_error)}"
                            logger.error(log_msg)
                            print(log_msg)
                            traceback.print_exc()
                        raise  # Re-raise to be caught by outer exception handler

                    # ---------------------------
                    # 8. Store result in product with model tracking
                    # ---------------------------
                    product.generated_images.append({
                        "type": key,
                        "prompt": prompt_text,
                        "local_path": local_path,
                        "cloud_url": cloud_upload["secure_url"],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "model_used": {
                            "type": selected_model.get("type"),
                            "local": selected_model.get("local"),
                            "cloud": selected_model.get("cloud"),
                            "name": selected_model.get("name", "")
                        }
                    })

                    if key == "campaign_image":
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] 🎉 SUCCESS: Campaign image generation completed and stored!"
                        logger.info(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] Total generated images for this product: {len(product.generated_images)}"
                        logger.info(log_msg)
                        print(log_msg)

                    # Track image generation in history
                    try:
                        from .history_utils import track_project_image_generation
                        track_project_image_generation(
                            user_id=str(user_id),
                            collection_id=str(collection.id),
                            image_type=f"project_{key}",
                            image_url=cloud_upload["secure_url"],
                            prompt=prompt_text,
                            local_path=local_path,
                            metadata={
                                "model_used": selected_model.get("type"),
                                "product_url": product.uploaded_image_url,
                                "model_name": selected_model.get("name", ""),
                                "generation_type": key
                            }
                        )
                    except Exception as history_error:
                        print(
                            f"Error tracking project image generation history: {history_error}")

                except Exception as e:
                    error_trace = traceback.format_exc()
                    if key == "campaign_image":
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] ❌ CRITICAL ERROR: Failed to generate campaign_image for {product.uploaded_image_url}"
                        logger.error(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] Error type: {type(e).__name__}, Error message: {str(e)}"
                        logger.error(log_msg)
                        print(log_msg)
                        log_msg = f"[PRODUCT {product_idx}][CAMPAIGN_IMAGE] Full traceback:\n{error_trace}"
                        logger.error(log_msg)
                        print(log_msg)
                    else:
                        traceback.print_exc()
                        print(
                            f"⚠️ Failed to generate {key} for {product.uploaded_image_url}: {e}")
                    continue

        # ---------------------------
        # 9. Save updated collection
        # ---------------------------
        collection.save()

        total_generated = sum(len(p.generated_images)
                              for p in item.product_images)

        # Log summary of generated images per product, specifically checking for campaign_image
        log_msg = f"[GENERATION] ✅ Generation complete. Total images generated: {total_generated}"
        logger.info(log_msg)
        print(log_msg)

        for product_idx, product in enumerate(item.product_images, 1):
            generated_types = [img.get("type")
                               for img in product.generated_images]
            has_campaign = "campaign_image" in generated_types
            log_msg = f"[GENERATION][PRODUCT {product_idx}] Generated {len(product.generated_images)} images. Types: {generated_types}"
            logger.info(log_msg)
            print(log_msg)
            if not has_campaign:
                log_msg = f"[GENERATION][PRODUCT {product_idx}] ⚠️ WARNING: campaign_image NOT generated for this product!"
                logger.warning(log_msg)
                print(log_msg)
            else:
                log_msg = f"[GENERATION][PRODUCT {product_idx}] ✅ campaign_image successfully generated"
                logger.info(log_msg)
                print(log_msg)

        return {
            "success": True,
            "message": f"All product model images generated successfully ({total_generated} images).",
            "total_generated": total_generated,
        }

    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def generate_all_product_model_images(request, collection_id):
    """
    Generate AI images for all product images in a collection using the selected model image
    and prompts stored in `generated_prompts`. Saves both locally and in Cloudinary.
    Now uses Celery for background processing.
    """
    from .tasks import generate_images_task
    from .utils import enqueue_task_with_load_balancing

    try:
        # Get user_id from request
        user_id = str(request.user.id) if hasattr(
            request, 'user') and request.user else None

        # Start Celery task using load-based queue selection
        task = enqueue_task_with_load_balancing(
            generate_images_task, collection_id, user_id
        )

        return Response({
            "success": True,
            "message": "Image generation started.",
            "task_id": task.id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@authenticate
def regenerate_product_model_image(request, collection_id):
    """
    Regenerate a specific generated image using Google GenAI (Gemini).
    Allows specifying a different model (AI or real) for regeneration.
    Tracks model usage statistics.
    """
    import json
    import os
    import uuid
    import base64
    import traceback
    import cloudinary.uploader
    from datetime import datetime
    from google import genai
    from google.genai import types

    # Get user from authentication middleware
    user = request.user

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
            reason="Product model image regeneration",
            project=None,
            metadata={"type": "regenerate_product_model_image",
                      "collection_id": collection_id}
        )

        if not credit_result['success']:
            return Response({"success": False, "error": credit_result['message']}, status=400)
    # If no organization, allow generation to proceed without credit deduction

    try:
        data = json.loads(request.body)
        product_image_path = data.get("product_image_path")
        generated_image_path = data.get("generated_image_path")
        new_prompt = data.get("prompt")
        use_different_model = data.get("use_different_model", False)
        # {type: 'ai'/'real', local: path, cloud: url}
        new_model_data = data.get("new_model")

        if not (product_image_path and generated_image_path):
            print("Missing parameters", product_image_path,
                  generated_image_path, new_prompt)
            return Response({"success": False, "error": "Missing parameters"}, status=400)

        # Load collection and item
        collection = Collection.objects.get(id=collection_id)
        item = collection.items[0]

        # Find the generated image we're regenerating and the product
        # This could be either an original generated image or a regenerated image
        target_generated = None
        target_product = None
        is_regenerated_image = False
        original_prompt = None

        for p in item.product_images:
            for g in p.generated_images:
                # Check if it's the original generated image
                if g.get("local_path") == generated_image_path:
                    target_generated = g
                    target_product = p
                    original_prompt = g.get("prompt")
                    break

                # Check if it's a regenerated image
                if "regenerated_images" in g:
                    for regen in g.get("regenerated_images", []):
                        if regen.get("local_path") == generated_image_path:
                            target_generated = g  # Store the parent generated image
                            target_product = p
                            is_regenerated_image = True
                            original_prompt = regen.get(
                                "prompt", g.get("prompt"))
                            break
                    if target_generated:
                        break
            if target_generated:
                break

        if not target_generated:
            return Response({"success": False, "error": "Generated image not found"}, status=404)

        # --- Google GenAI setup ---
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = "gemini-3-pro-image-preview"

        # Determine which model to use
        if use_different_model and new_model_data:
            model_to_use = new_model_data
        else:
            # Use the same model that was originally used (from selected_model)
            model_to_use = item.selected_model if hasattr(
                item, 'selected_model') else None

        if not model_to_use:
            return Response({"success": False, "error": "No model specified for regeneration"})

        # Load model image
        model_local_path = model_to_use.get("local")
        if not model_local_path or not os.path.exists(model_local_path):
            return Response({"success": False, "error": "Model image not found"})

        with open(model_local_path, "rb") as f:
            model_bytes = f.read()
        model_b64 = base64.b64encode(model_bytes).decode("utf-8")

        # Load product image
        if not os.path.exists(product_image_path):
            return Response({"success": False, "error": "Product image not found"})

        with open(product_image_path, "rb") as f:
            product_bytes = f.read()
        product_b64 = base64.b64encode(product_bytes).decode("utf-8")

        # Build custom prompt based on the original image type
        # Combine original prompt context with new modifications
        original_type = target_generated.get("type", "model_image")
        original_base_prompt = target_generated.get("prompt", "")

        # Get regeneration prompts from database with fallback
        from .prompt_initializer import get_prompt_from_db

        # If using different model without new modifications, just use original prompt
        if use_different_model and (not new_prompt or not new_prompt.strip()):
            default_regenerate_white = "Generate a high-quality product photo on a clean, elegant white studio background. \nDo NOT modify the product - keep its color, shape, texture exactly the same. \n{original_prompt}"
            default_regenerate_bg = "Replace only the background elegantly while keeping the product identical. \n{original_prompt}"
            default_regenerate_model = "Generate a realistic photo of the model wearing ONLY the given product. \nKeep the product design identical to the original. \n{original_prompt}"
            default_regenerate_campaign = "Create a professional campaign-style image with the model wearing ONLY the product. \nKeep the product exactly as it appears in the original. \n{original_prompt}"

            regenerate_templates = {
                "white_background": get_prompt_from_db('regenerate_white_background_template', default_regenerate_white),
                "background_replace": get_prompt_from_db('regenerate_background_replace_template', default_regenerate_bg),
                "model_image": get_prompt_from_db('regenerate_model_image_template', default_regenerate_model),
                "campaign_image": get_prompt_from_db('regenerate_campaign_image_template', default_regenerate_campaign),
            }

            template = regenerate_templates.get(
                original_type, "{original_prompt}")
            custom_prompt = template.format(
                original_prompt=original_base_prompt)
        else:
            # Combine original prompt with modifications
            default_with_mods_white = "Generate a high-quality product photo on a clean, elegant white studio background. \nDo NOT modify the product - keep its color, shape, texture exactly the same. \nOriginal style: {original_prompt}. \nModifications: {new_prompt}"
            default_with_mods_bg = "Replace only the background elegantly while keeping the product identical. \nOriginal style: {original_prompt}. \nModifications: {new_prompt}"
            default_with_mods_model = "Generate a realistic photo of the model wearing ONLY the given product. \nKeep the product design identical to the original. \nOriginal style: {original_prompt}. \nModifications: {new_prompt}"
            default_with_mods_campaign = "Create a professional campaign-style image with the model wearing ONLY the product. \nKeep the product exactly as it appears in the original. \nOriginal style: {original_prompt}. \nModifications: {new_prompt}"

            # Use a generic template for modifications since we have specific ones per type
            regenerate_templates = {
                "white_background": get_prompt_from_db('regenerate_with_modifications_white', default_with_mods_white),
                "background_replace": get_prompt_from_db('regenerate_with_modifications_bg', default_with_mods_bg),
                "model_image": get_prompt_from_db('regenerate_with_modifications_model', default_with_mods_model),
                "campaign_image": get_prompt_from_db('regenerate_with_modifications_campaign', default_with_mods_campaign),
            }

            template = regenerate_templates.get(
                original_type, "Original: {original_prompt}. Modifications: {new_prompt}")
            custom_prompt = template.format(
                original_prompt=original_base_prompt,
                new_prompt=new_prompt or ""
            )

        # Generate with model and product
        contents = [
            {"inline_data": {"mime_type": "image/jpeg", "data": model_b64}},
            {"inline_data": {"mime_type": "image/jpeg", "data": product_b64}},
            {"text": custom_prompt}
        ]

        config = types.GenerateContentConfig(
            response_modalities=[types.Modality.IMAGE]
        )

        resp = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )

        # Extract generated image bytes
        candidate = resp.candidates[0]
        generated_bytes = None
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                data_part = part.inline_data.data
                generated_bytes = data_part if isinstance(
                    data_part, bytes) else base64.b64decode(data_part)
                break

        if not generated_bytes:
            return Response({"success": False, "error": "No image generated by GenAI"})

        # --- Save new regenerated image locally ---
        new_filename = f"{uuid.uuid4()}_regenerated.png"
        local_dir = os.path.join(
            "media", "composite_images", str(collection_id))
        os.makedirs(local_dir, exist_ok=True)
        local_output_path = os.path.join(local_dir, new_filename)

        with open(local_output_path, "wb") as f:
            f.write(generated_bytes)

        # --- Upload to Cloudinary ---
        upload_result = cloudinary.uploader.upload(
            local_output_path,
            folder=f"ai_studio/regenerated/{collection_id}/"
        )
        cloud_url = upload_result["secure_url"]

        # --- Append regenerated image metadata with model tracking ---
        # This tracks which model was used for each regeneration, supporting both AI and Real models
        # Model count is calculated as: 1 (original) + len(regenerated_images)
        # Model types used are tracked in the model_used field for each version
        regenerated_data = {
            # Use new prompt if provided, otherwise original
            "prompt": new_prompt or original_base_prompt,
            "original_prompt": original_base_prompt,
            "combined_prompt": custom_prompt,
            "type": original_type,
            "local_path": local_output_path,
            "cloud_url": cloud_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "product_image_path": product_image_path,
            "model_used": {
                "type": model_to_use.get("type"),  # 'ai' or 'real'
                "local": model_to_use.get("local"),
                "cloud": model_to_use.get("cloud"),
                "name": model_to_use.get("name", "")
            }
        }

        target_generated.setdefault(
            "regenerated_images", []).append(regenerated_data)
        collection.save()

        # Track regeneration in history
        try:
            from .history_utils import track_image_regeneration
            track_image_regeneration(
                user_id=str(request.user.id),
                original_image_id=str(target_generated.get("id", "unknown")),
                new_image_url=cloud_url,
                new_prompt=new_prompt or "",
                original_prompt=original_base_prompt,
                image_type=original_type,
                project_id=str(collection.project.id),
                collection_id=str(collection.id),
                local_path=local_output_path,
                metadata={
                    "model_used": regenerated_data["model_used"],
                    "regeneration_count": len(target_generated.get("regenerated_images", [])),
                    "used_different_model": use_different_model
                }
            )
        except Exception as history_error:
            print(f"Error tracking regeneration history: {history_error}")

        return Response({
            "success": True,
            "url": cloud_url,
            "local_path": local_output_path,
            "model_used": regenerated_data["model_used"],
            "original_prompt": original_base_prompt,
            "new_prompt": new_prompt or "",
            "combined_prompt": custom_prompt,
            "type": original_type,
            "regeneration_count": len(target_generated.get("regenerated_images", [])),
            "product_image_url": target_product.uploaded_image_url,
            "used_different_model": use_different_model
        })

    except Exception as e:
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)
