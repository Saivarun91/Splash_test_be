import re
import logging
from cloudinary.utils import cloudinary_url
from .models import Project, ProjectInvite, ProjectMember, ImageGenerationHistory
from .job_models import ImageGenerationJob
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from mongoengine.errors import DoesNotExist
from django.conf import settings
import json
import os
from datetime import datetime, timezone
import cloudinary
import cloudinary.uploader
import jwt

logger = logging.getLogger(__name__)
from .models import Project, Collection, CollectionItem, ProjectRole, ProjectMember, UploadedImage, PromptMaster
from users.models import User
from .views import (
    project_setup_description,
    project_setup_select,
    generate_ai_images,
    save_generated_images,
    upload_product_images_api,
    generate_all_product_model_images,
    regenerate_product_model_image
)
from common.middleware import authenticate
from rest_framework.response import Response
from rest_framework.decorators import api_view

# -------------------------
# Project API Views
# -------------------------


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_projects_list(request):
    """Get projects where the user is a team member"""
    try:
        user = request.user
        all_projects = Project.objects.all()
        projects_data = []

        for project in all_projects:
            # Check if user is a team member
            user_member = None
            for member in project.team_members:
                if str(member.user.id) == str(user.id):
                    user_member = member
                    break

            # Only include projects where user is a member
            if user_member:
                # Get the first collection for each project
                collection = Collection.objects(project=project).first()

                # Calculate total images
                # Calculate total images
                total_images = 0
                if collection and collection.items:
                    for item in collection.items:
                        # Check each product image under the item
                        if item.product_images:
                            for prod_img in item.product_images:
                                total_images += 1  # count the product image itself

                                # Count generated images under this product
                                if hasattr(prod_img, "generated_images") and prod_img.generated_images:
                                    for gen_img in prod_img.generated_images:
                                        total_images += 1  # count generated image

                                        # Count regenerated images under this generated image
                                        if hasattr(gen_img, "regenerated_images") and gen_img.regenerated_images:
                                            total_images += len(
                                                gen_img.regenerated_images)

                projects_data.append({
                    'id': str(project.id),
                    'name': project.name,
                    'about': project.about,
                    'created_at': project.created_at.isoformat(),
                    'status': project.status,
                    'collection_id': str(collection.id) if collection else None,
                    'total_images': total_images,
                    'user_role': user_member.role,  # Add user's role in this project
                    "team_members": [
                        {
                            "username": member.user.username if member.user else None,
                            "full_name": member.user.full_name if member.user else None,
                            "email": member.user.email if member.user else None,
                            "role": member.role,
                            "joined_at": member.joined_at.isoformat() if member.joined_at else None
                        }
                        for member in project.team_members
                    ]
                })

        return Response({'projects': projects_data})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
def api_project_detail(request, project_id):
    """Get a specific project"""
    try:
        project = Project.objects.get(id=project_id)
        collection = Collection.objects(project=project).first()

        project_data = {
            'id': str(project.id),
            'name': project.name,
            'about': project.about,
            'created_at': project.created_at.isoformat(),
            'status': project.status,
            'collection_id': str(collection.id) if collection else None,
            'team_members': [
                {
                    'user_id': str(member.user.id),
                    'user_email': member.user.email,
                    'user_name': member.user.full_name or member.user.username,
                    'role': member.role
                } for member in project.team_members
            ] if project.team_members else []
        }

        if collection:
            project_data['collection'] = {
                'id': str(collection.id),
                'description': collection.description,
                'target_audience': collection.target_audience,
                'campaign_season': collection.campaign_season,
                'created_at': collection.created_at.isoformat(),
                'items': []
            }

            for item in collection.items:
                item_data = {
                    'suggested_themes': item.suggested_themes or [],
                    'suggested_backgrounds': item.suggested_backgrounds or [],
                    'suggested_poses': item.suggested_poses or [],
                    'suggested_locations': item.suggested_locations or [],
                    'suggested_colors': item.suggested_colors or [],
                    'selected_themes': item.selected_themes or [],
                    'selected_backgrounds': item.selected_backgrounds or [],
                    'selected_poses': item.selected_poses or [],
                    'selected_locations': item.selected_locations or [],
                    'selected_colors': item.selected_colors or [],
                    'uploaded_theme_images': [img.to_mongo().to_dict() for img in item.uploaded_theme_images],
                    'uploaded_background_images': [img.to_mongo().to_dict() for img in item.uploaded_background_images],
                    'uploaded_pose_images': [img.to_mongo().to_dict() for img in item.uploaded_pose_images],
                    'uploaded_location_images': [img.to_mongo().to_dict() for img in item.uploaded_location_images],
                    'uploaded_color_images': [img.to_mongo().to_dict() for img in item.uploaded_color_images],
                    'generated_prompts': item.generated_prompts or {},
                    'generated_model_images': item.generated_model_images or [],
                    'moodboard_explanation': item.moodboard_explanation or "",
                    'uploaded_model_images': item.uploaded_model_images or [],
                    'selected_model': item.selected_model if hasattr(item, 'selected_model') else None,
                    'product_images': []
                }

                # Add product images data
                for product_img in item.product_images:
                    product_data = {
                        'uploaded_image_url': product_img.uploaded_image_url,
                        'uploaded_image_path': product_img.uploaded_image_path,
                        'generated_images': product_img.generated_images or []
                    }
                    item_data['product_images'].append(product_data)

                project_data['collection']['items'].append(item_data)

        return Response(project_data)
    except DoesNotExist:
        return Response({'error': 'Project not found'}, status=404)
    except Exception as e:
        print(e)
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_create_project(request):
    """Create a new project"""
    try:
        user = request.user
        data = json.loads(request.body)
        name = data.get('name')
        about = data.get('about', '')

        if not name:
            return Response({'error': 'Project name is required'}, status=400)

        project = Project(name=name, about=about)
        project.save()

        # Add the owner as a team member
        owner_member = ProjectMember(user=user, role=ProjectRole.OWNER.value)
        project.team_members.append(owner_member)
        project.save()
        if project not in user.projects:
            user.projects.append(project)
            user.save()

        return Response({
            'id': str(project.id),
            'name': project.name,
            'about': project.about,
            'created_at': project.created_at.isoformat(),
            'status': project.status,
            'collection_id': None,

            'team_members': [
                {
                    'user': str(member.user.id),
                    'role': member.role
                } for member in project.team_members
            ]
        })
    except Exception as e:
        print(e)
        return Response({'error': str(e)}, status=500)


@api_view(['PUT'])
@csrf_exempt
@authenticate
def api_update_project(request, project_id):
    """Update a project"""
    try:
        user = request.user
        project = Project.objects.get(id=project_id)
        data = json.loads(request.body)

        if 'name' in data:
            project.name = data['name']
        if 'about' in data:
            project.about = data['about']
        if 'status' in data:
            # Only allow lowercase canonical statuses
            valid_statuses = ['progress', 'completed']
            new_status = data['status'].lower()

            if new_status not in valid_statuses:
                return Response({'error': 'Invalid status value'}, status=400)

            project.status = new_status

        project.save()

        return Response({
            'id': str(project.id),
            'name': project.name,
            'about': project.about,
            'status': project.status,
            'created_at': project.created_at.isoformat(),
        })
    except DoesNotExist:
        return Response({'error': 'Project not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['DELETE'])
@csrf_exempt
@authenticate
def api_delete_project(request, project_id):
    """Delete a project"""
    try:
        project = Project.objects.get(id=project_id)
        project.delete()
        return Response({'success': True})
    except DoesNotExist:
        return Response({'error': 'Project not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# -------------------------
# Collection API Views
# -------------------------


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_collection_detail(request, collection_id):
    """Get collection details"""
    try:
        collection = Collection.objects.get(id=collection_id)

        collection_data = {
            'id': str(collection.id),
            'project_id': str(collection.project.id),
            'description': collection.description,
            'target_audience': collection.target_audience,
            'campaign_season': collection.campaign_season,
            'created_at': collection.created_at.isoformat(),
            'items': []
        }

        for item in collection.items:
            item_data = {
                'suggested_themes': item.suggested_themes or [],
                'suggested_backgrounds': item.suggested_backgrounds or [],
                'suggested_poses': item.suggested_poses or [],
                'suggested_locations': item.suggested_locations or [],
                'suggested_colors': item.suggested_colors or [],
                'selected_themes': item.selected_themes or [],
                'selected_backgrounds': item.selected_backgrounds or [],
                'selected_poses': item.selected_poses or [],
                'selected_locations': item.selected_locations or [],
                'selected_colors': item.selected_colors or [],
                'uploaded_theme_images': [img.to_mongo().to_dict() for img in item.uploaded_theme_images],
                'uploaded_background_images': [img.to_mongo().to_dict() for img in item.uploaded_background_images],
                'uploaded_pose_images': [img.to_mongo().to_dict() for img in item.uploaded_pose_images],
                'uploaded_location_images': [img.to_mongo().to_dict() for img in item.uploaded_location_images],
                'uploaded_color_images': [img.to_mongo().to_dict() for img in item.uploaded_color_images],
                'generated_prompts': item.generated_prompts or {},
                'generated_model_images': item.generated_model_images or [],
                'picked_colors': item.picked_colors or [],
                "global_instructions": item.global_instructions or "",
                'moodboard_explanation': item.moodboard_explanation or "",
                'uploaded_model_images': item.uploaded_model_images or [],
                'selected_model': item.selected_model if hasattr(item, 'selected_model') else None,
                'product_images': []
            }

            for product_img in item.product_images:
                product_data = {
                    'uploaded_image_url': product_img.uploaded_image_url,
                    'uploaded_image_path': product_img.uploaded_image_path,
                    'generated_images': product_img.generated_images or []
                }
                item_data['product_images'].append(product_data)

            collection_data['items'].append(item_data)

        return Response(collection_data)
    except DoesNotExist:
        return Response({'error': 'Collection not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# -------------------------
# Workflow API Views (wrapper around existing views)
# -------------------------


@api_view(['POST'])
@csrf_exempt
def api_project_setup_description(request, project_id):
    """API wrapper for project setup description including target audience and campaign season"""
    try:
        from .utils import request_suggestions

        data = json.loads(request.body)
        description = data.get('description', '').strip()
        target_audience = data.get('target_audience', '').strip()
        campaign_season = data.get('campaign_season', '').strip()

        # Description is now optional - only validate target_audience and campaign_season
        # (These are still required for step 2 to be considered complete)
        # Note: We allow saving without description, in which case suggestions won't be generated

        # Get or create project
        try:
            project = Project.objects.get(id=project_id)
        except DoesNotExist:
            return Response({'error': 'Project not found'}, status=404)

        # Get or create collection
        collection = Collection.objects(project=project).first()
        if not collection:
            collection = Collection(project=project)
            item = CollectionItem()
            collection.items.append(item)
        else:
            item = collection.items[0] if collection.items else CollectionItem(
            )
            if not collection.items:
                collection.items.append(item)

        # Update collection fields
        collection.description = description if description else ""
        collection.target_audience = target_audience
        collection.campaign_season = campaign_season

        # Only generate suggestions if description is provided
        if description:
            # Generate fresh suggestions each time, including target_audience and campaign_season
            suggestions = request_suggestions(
                description, None, target_audience, campaign_season)
            item.suggested_themes = suggestions.get("themes", [])
            item.suggested_backgrounds = suggestions.get("backgrounds", [])
            item.suggested_poses = suggestions.get("poses", [])
            item.suggested_locations = suggestions.get("locations", [])
            item.suggested_colors = suggestions.get("colors", [])
        else:
            # No description provided - clear suggestions (user will use uploaded images instead)
            item.suggested_themes = []
            item.suggested_backgrounds = []
            item.suggested_poses = []
            item.suggested_locations = []
            item.suggested_colors = []

        collection.save()

        # Prepare collection response data - match the structure expected by frontend (items array)
        item_data = {
            'suggested_themes': item.suggested_themes or [],
            'suggested_backgrounds': item.suggested_backgrounds or [],
            'suggested_poses': item.suggested_poses or [],
            'suggested_locations': item.suggested_locations or [],
            'suggested_colors': item.suggested_colors or [],
            'selected_themes': item.selected_themes or [],
            'selected_backgrounds': item.selected_backgrounds or [],
            'selected_poses': item.selected_poses or [],
            'selected_locations': item.selected_locations or [],
            'selected_colors': item.selected_colors or [],
            'uploaded_theme_images': [img.to_mongo().to_dict() for img in item.uploaded_theme_images] if item.uploaded_theme_images else [],
            'uploaded_background_images': [img.to_mongo().to_dict() for img in item.uploaded_background_images] if item.uploaded_background_images else [],
            'uploaded_pose_images': [img.to_mongo().to_dict() for img in item.uploaded_pose_images] if item.uploaded_pose_images else [],
            'uploaded_location_images': [img.to_mongo().to_dict() for img in item.uploaded_location_images] if item.uploaded_location_images else [],
            'uploaded_color_images': [img.to_mongo().to_dict() for img in item.uploaded_color_images] if item.uploaded_color_images else [],
            'generated_prompts': item.generated_prompts or {},
            'generated_model_images': item.generated_model_images or [],
            'picked_colors': item.picked_colors or [],
            'global_instructions': item.global_instructions or "",
            'moodboard_explanation': item.moodboard_explanation or "",
            'uploaded_model_images': item.uploaded_model_images or [],
            'selected_model': item.selected_model if hasattr(item, 'selected_model') else None,
        }

        collection_data = {
            'id': str(collection.id),
            'project_id': str(collection.project.id),
            'description': collection.description,
            'target_audience': collection.target_audience,
            'campaign_season': collection.campaign_season,
            'created_at': collection.created_at.isoformat() if hasattr(collection, 'created_at') and collection.created_at else None,
            'items': [item_data]
        }

        return Response({
            'success': True,
            'collection_id': str(collection.id),
            'collection': collection_data
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


def analyze_uploaded_image(cloud_url, category):
    """
    Analyze an uploaded image using Gemini Vision API based on its category.
    Uses the utility function from utils.py for REST API calls.
    Returns a descriptive analysis paragraph.
    For theme images, also extracts ornament_type, angle_shot, and theme_description.
    """
    try:
        from .analysisprompt import (
            theme_prompt, background_prompt, pose_prompt,
            location_prompt, color_prompt
        )
        from .utils import call_gemini_api

        # Map category to appropriate prompt
        category_prompts = {
            'theme': theme_prompt,
            'background': background_prompt,
            'pose': pose_prompt,
            'location': location_prompt,
            'color': color_prompt
        }

        analysis_prompt = category_prompts.get(category, theme_prompt)

        # Check if GEMINI_API_KEY is configured
        import os
        from dotenv import load_dotenv
        load_dotenv()
        if not os.getenv("GEMINI_API_KEY"):
            print("⚠️ GEMINI_API_KEY not configured, skipping image analysis")
            return {"analysis": "", "ornament_type": "", "angle_shot": "", "theme_description": ""}

        # Use the utility function to call Gemini API with image URL
        if not cloud_url:
            print("⚠️ No cloud URL provided for image analysis")
            return {"analysis": "", "ornament_type": "", "angle_shot": "", "theme_description": ""}

        print(f"DEBUG: Analyzing {category} image from URL: {cloud_url}")
        analysis_result = call_gemini_api(analysis_prompt, image_url=cloud_url)

        if analysis_result:
            print("DEBUG: Analysis completed successfully")
            analysis_text = analysis_result.strip()

            # For theme images, extract ornament_type, angle_shot, and theme_description
            if category == 'theme':
                return extract_theme_analysis(analysis_text)
            else:
                return {"analysis": analysis_text, "ornament_type": "", "angle_shot": "", "theme_description": ""}
        else:
            print("⚠️ Gemini API returned no analysis result")
            return {"analysis": "", "ornament_type": "", "angle_shot": "", "theme_description": ""}

    except Exception as e:
        print(f"⚠️ Error in analyze_uploaded_image: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"analysis": "", "ornament_type": "", "angle_shot": "", "theme_description": ""}


def extract_theme_analysis(analysis_text):
    """
    Parse JSON response from theme analysis.
    The analysis_text should already be a JSON string with type and description.
    """
    try:
        import json
        import re

        # Try to extract JSON from the response
        result = analysis_text.strip()
        # Remove markdown code blocks if present
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        try:
            extracted = json.loads(result)
            ornament_type = extracted.get("type", "").strip()
            description = extracted.get("description", "").strip()

            # Parse ornament_type format: "subcategory(main_category)"
            # Example: "long necklace(necklace)" -> subcategory: "long necklace", main_category: "necklace"
            main_category = ""
            subcategory = ""
            if ornament_type:
                # Check if format is "subcategory(main_category)"
                match = re.match(r'^(.+?)\(([^)]+)\)$', ornament_type)
                if match:
                    subcategory = match.group(1).strip()
                    main_category = match.group(2).strip()
                else:
                    # If no parentheses format, treat entire string as subcategory and try to extract main category
                    subcategory = ornament_type
                    # Try to extract main category from subcategory (e.g., "long necklace" -> "necklace")
                    main_category_patterns = [
                        r'\b(necklace|choker|pendant|chain|haram)\b',
                        r'\b(earring|earrings|stud|jhumka)\b',
                        r'\b(bracelet|bangle|cuff)\b',
                        r'\b(ring|bands?)\b',
                        r'\b(anklet)\b',
                        r'\b(brooch)\b'
                    ]
                    for pattern in main_category_patterns:
                        match = re.search(pattern, subcategory, re.IGNORECASE)
                        if match:
                            main_category = match.group(1).lower()
                            # Normalize plural forms
                            if main_category.endswith('s') and main_category != 'earrings':
                                main_category = main_category[:-1]
                            break

            # Store only the main_category in ornament_type field (the most highlighted ornament)
            # This is what gets stored in the UploadedImage.ornament_type field
            # Convert to underscore format for matching (for backward compatibility)
            ornament_type_underscore = main_category.replace(
                ' ', '_').replace('-', '_') if main_category else ""

            # If main_category wasn't extracted, try to get it from ornament_type
            if not ornament_type_underscore and ornament_type:
                # Try to extract main category from ornament_type
                main_category_patterns = [
                    r'\b(necklace|choker|pendant|chain|haram)\b',
                    r'\b(earring|earrings|stud|jhumka)\b',
                    r'\b(bracelet|bangle|cuff)\b',
                    r'\b(ring|bands?)\b',
                    r'\b(anklet)\b',
                    r'\b(brooch)\b'
                ]
                for pattern in main_category_patterns:
                    match = re.search(pattern, ornament_type, re.IGNORECASE)
                    if match:
                        extracted_main = match.group(1).lower()
                        # Normalize plural forms
                        if extracted_main.endswith('s') and extracted_main != 'earrings':
                            extracted_main = extracted_main[:-1]
                        ornament_type_underscore = extracted_main.replace(
                            ' ', '_').replace('-', '_')
                        main_category = extracted_main
                        break

            # Extract angle_shot from description for backward compatibility
            angle_shot = ""
            angle_patterns = [
                r'(?:overhead|top[- ]down|flat[- ]lay|90[- ]degree|ninety[- ]degree)\s+(?:angle|view|shot|perspective)',
                r'(?:diagonal|slight|oblique)\s+(?:angle|view|shot)',
                r'(?:from|shot from|captured from)\s+(?:above|overhead|top)',
            ]
            for pattern in angle_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    angle_shot = match.group(0).lower().replace(
                        ' ', '_').replace('-', '_')
                    break

            # Extract theme_description (description without angle shot info, for master analysis)
            theme_description = description
            # Try to remove angle shot mentions if they're at the end
            if angle_shot:
                angle_readable = angle_shot.replace('_', ' ').replace('-', ' ')
                # Remove common angle shot phrases from end of description
                theme_description = re.sub(
                    r'\s*(?:the overall angle shot is|angle shot is|shot angle is|photographed from|captured in|shot from).*?\.?\s*$',
                    '', theme_description, flags=re.IGNORECASE
                ).strip()

            # Create structured JSON for analysis field (only type and description)
            # Store type in the format "subcategory(main_category)"
            analysis_json = {
                # Full format: "long necklace(necklace)"
                "type": ornament_type,
                "description": description  # Description already includes angle shot
            }
            analysis_json_string = json.dumps(analysis_json)

            return {
                "analysis": analysis_json_string,  # Store as JSON string with full type format
                # Keep underscore format for matching (backward compatibility)
                # This stores only the main_category (most highlighted ornament)
                "ornament_type": ornament_type_underscore,
                # Keep underscore format for matching
                "angle_shot": angle_shot,
                "theme_description": theme_description
            }
        except json.JSONDecodeError:
            print(
                f"⚠️ Failed to parse JSON from theme analysis: {result}")
            # Fallback: try to extract using regex patterns
            return extract_theme_analysis_fallback(analysis_text)
    except Exception as e:
        print(f"⚠️ Error in extract_theme_analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return extract_theme_analysis_fallback(analysis_text)


def extract_theme_analysis_fallback(analysis_text):
    """
    Fallback method to extract theme analysis using regex patterns.
    """
    import re

    ornament_type = ""
    angle_shot = ""
    theme_description = analysis_text

    # Try to extract ornament type (common patterns)
    ornament_patterns = [
        r'(?:long|short|delicate|chunky|multi[- ]strand|multi[- ]layer)\s+(?:necklace|chain|pendant|haram)',
        r'(?:stud|jhumka[- ]style|drop|hoop|chandelier)\s+(?:earring|earrings)',
        r'(?:chunky|delicate|bangle|tennis)\s+(?:bracelet|bangle)',
        r'(?:diamond|gold|silver|platinum)\s+(?:ring|rings)',
    ]

    for pattern in ornament_patterns:
        match = re.search(pattern, analysis_text, re.IGNORECASE)
        if match:
            ornament_type = match.group(0).lower().replace(
                ' ', '_').replace('-', '_')
            break

    # Try to extract angle shot (common patterns)
    angle_patterns = [
        r'(?:overhead|top[- ]down|flat[- ]lay|90[- ]degree|ninety[- ]degree)\s+(?:angle|view|shot|perspective)',
        r'(?:diagonal|slight|oblique)\s+(?:angle|view|shot)',
        r'(?:from|shot from|captured from)\s+(?:above|overhead|top)',
    ]

    for pattern in angle_patterns:
        match = re.search(pattern, analysis_text, re.IGNORECASE)
        if match:
            angle_shot = match.group(0).lower().replace(
                ' ', '_').replace('-', '_')
            break

    # Convert ornament_type and angle_shot back to readable format for JSON
    ornament_type_readable = ornament_type.replace(
        '_', ' ') if ornament_type else ""
    angle_shot_readable = angle_shot.replace('_', ' ') if angle_shot else ""

    # Extract main category from ornament_type for format "subcategory(main_category)"
    main_category = ""
    if ornament_type_readable:
        # Try to extract main category from ornament type
        main_category_patterns = [
            r'\b(necklace|choker|pendant|chain|haram)\b',
            r'\b(earring|earrings|stud|jhumka)\b',
            r'\b(bracelet|bangle|cuff)\b',
            r'\b(ring|bands?)\b',
            r'\b(anklet)\b',
            r'\b(brooch)\b'
        ]
        for pattern in main_category_patterns:
            match = re.search(pattern, ornament_type_readable, re.IGNORECASE)
            if match:
                main_category = match.group(1).lower()
                # Normalize plural forms
                if main_category.endswith('s') and main_category != 'earrings':
                    main_category = main_category[:-1]
                break

    # Format as "subcategory(main_category)" if we have both
    if ornament_type_readable and main_category:
        ornament_type_formatted = f"{ornament_type_readable}({main_category})"
    else:
        ornament_type_formatted = ornament_type_readable

    # Include angle shot in the description if it exists
    description_with_angle = theme_description
    if angle_shot_readable:
        # Only add angle shot if not already in description
        if angle_shot_readable.lower() not in theme_description.lower():
            description_with_angle = f"{theme_description} The overall angle shot is {angle_shot_readable}."

    # Create structured JSON for analysis field (only type and description)
    import json
    analysis_json = {
        "type": ornament_type_formatted,  # Format: "long necklace(necklace)"
        "description": description_with_angle
    }
    analysis_json_string = json.dumps(analysis_json)

    # Store only the main_category in ornament_type field (the most highlighted ornament)
    # Convert to underscore format for matching (for backward compatibility)
    ornament_type_underscore = main_category.replace(
        ' ', '_').replace('-', '_') if main_category else ""
    # If main_category wasn't extracted, use the original ornament_type (already in underscore format)
    if not ornament_type_underscore:
        ornament_type_underscore = ornament_type

    return {
        "analysis": analysis_json_string,  # Store as JSON string
        # Store only main_category (most highlighted ornament) in underscore format
        "ornament_type": ornament_type_underscore,
        "angle_shot": angle_shot,  # Keep underscore format for matching
        "theme_description": theme_description
    }


@api_view(['POST'])
@csrf_exempt
def api_upload_workflow_image(request, project_id, collection_id):
    """Upload images immediately when user selects them in workflow"""
    try:
        print(
            f"DEBUG: Upload request received for project {project_id}, collection {collection_id}")
        print(f"DEBUG: Request method: {request.method}")
        print(f"DEBUG: Request content type: {request.content_type}")
        print(f"DEBUG: Request FILES: {list(request.FILES.keys())}")
        print(f"DEBUG: Request POST: {dict(request.POST)}")

        # Manual authentication check
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header or not auth_header.startswith('Bearer '):
            print("DEBUG: No valid authorization header")
            return Response({'error': 'Authorization required'}, status=401)

        try:
            token = auth_header.split(' ')[1]
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=["HS256"])
            user = User.objects(id=payload.get('id')).first()
            if not user:
                print("DEBUG: User not found")
                return Response({'error': 'User not found'}, status=404)
            user_id = str(user.id)
            print(f"DEBUG: User authenticated: {user_id}")
        except Exception as auth_error:
            print(f"DEBUG: Authentication failed: {str(auth_error)}")
            return Response({'error': 'Authentication failed'}, status=401)

        # Get the collection
        try:
            collection = Collection.objects.get(id=collection_id)
            print(f"DEBUG: Collection found: {collection.id}")
        except DoesNotExist:
            print("DEBUG: Collection not found")
            return Response({'error': 'Collection not found'}, status=404)

        # Get the first item
        if not collection.items:
            print("DEBUG: No collection items found")
            return Response({'error': 'No collection items found'}, status=404)

        item = collection.items[0]
        print(f"DEBUG: Collection item found")

        # Get uploaded files and category
        uploaded_files = request.FILES.getlist('images')
        print(f"DEBUG: Uploaded files: {uploaded_files}")
        # 'theme', 'background', 'pose', 'location', 'color'
        category = request.POST.get('category')

        print(f"DEBUG: Uploaded files count: {len(uploaded_files)}")
        print(f"DEBUG: Category: {category}")

        if not uploaded_files or not category:
            print(
                f"DEBUG: Missing files or category - files: {len(uploaded_files)}, category: {category}")
            return Response({'error': 'No images or category provided'}, status=400)

        # Normalize category (convert plural to singular)
        category_mapping = {
            'themes': 'theme',
            'backgrounds': 'background',
            'poses': 'pose',
            'locations': 'location',
            'colors': 'color'
        }

        # Convert plural to singular if needed
        normalized_category = category_mapping.get(category, category)

        if normalized_category not in ['theme', 'background', 'pose', 'location', 'color']:
            print(
                f"DEBUG: Invalid category: {category} (normalized: {normalized_category})")
            return Response({'error': 'Invalid category'}, status=400)

        # Use the normalized category for the rest of the function
        category = normalized_category
        print(f"DEBUG: Using normalized category: {category}")

        # Create local directory for this category
        local_dir = os.path.join(
            settings.MEDIA_ROOT, "workflow_images", category)
        os.makedirs(local_dir, exist_ok=True)

        uploaded_images = []

        for file in uploaded_files:
            # Generate unique filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{file.name}"
            local_path = os.path.join(local_dir, filename)

            # Save locally
            with open(local_path, "wb") as f:
                for chunk in file.chunks():
                    f.write(chunk)

            # Reset file pointer to beginning for Cloudinary upload
            file.seek(0)

            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                file,
                folder=f"workflow_images/{category}",
                public_id=f"{category}_{timestamp}_{os.path.splitext(file.name)[0]}",
                overwrite=True
            )
            cloud_url = upload_result.get("secure_url")

            # Analyze the image based on its category using cloud URL
            print(f"DEBUG: Analyzing {category} image: {filename}")
            analysis_result = analyze_uploaded_image(cloud_url, category)

            # Handle both old format (string) and new format (dict)
            if isinstance(analysis_result, dict):
                analysis_text = analysis_result.get("analysis", "")
                ornament_type = analysis_result.get("ornament_type", "")
                angle_shot = analysis_result.get("angle_shot", "")
                theme_description = analysis_result.get(
                    "theme_description", analysis_text)
            else:
                # Legacy format (string)
                analysis_text = analysis_result if analysis_result else ""
                ornament_type = ""
                angle_shot = ""
                theme_description = analysis_text

            if analysis_text:
                print(f"DEBUG: Analysis completed for {filename}")
                if category == 'theme' and ornament_type:
                    print(
                        f"DEBUG: Extracted ornament_type: {ornament_type}, angle_shot: {angle_shot}")
            else:
                print(f"DEBUG: Analysis returned empty for {filename}")

            # For theme images: Store analysis as JSON with type and description (angle shot included in description)
            if category == 'theme':
                # The analysis from extract_theme_analysis is already a JSON string with type and description
                # where description includes the angle shot
                if isinstance(analysis_result, dict):
                    analysis_text = analysis_result.get("analysis", "")
                    if not analysis_text:
                        # Fallback: create JSON structure if extraction failed
                        import json
                        ornament_readable = ornament_type.replace(
                            '_', ' ').replace('-', ' ') if ornament_type else ""
                        angle_readable = angle_shot.replace(
                            '_', ' ').replace('-', ' ') if angle_shot else ""
                        description_with_angle = theme_description
                        if angle_readable and angle_readable.lower() not in theme_description.lower():
                            description_with_angle = f"{theme_description} The overall angle shot is {angle_readable}."
                        analysis_json = {
                            "type": ornament_readable,
                            "description": description_with_angle
                        }
                        analysis_text = json.dumps(analysis_json)
                    print(
                        f"DEBUG: Stored theme analysis as JSON with type and description (angle shot included in description)")
                else:
                    # Legacy format: create JSON structure
                    import json
                    ornament_readable = ornament_type.replace(
                        '_', ' ').replace('-', ' ') if ornament_type else ""
                    angle_readable = angle_shot.replace(
                        '_', ' ').replace('-', ' ') if angle_shot else ""
                    description_with_angle = theme_description
                    if angle_readable and angle_readable.lower() not in theme_description.lower():
                        description_with_angle = f"{theme_description} The overall angle shot is {angle_readable}."
                    analysis_json = {
                        "type": ornament_readable,
                        "description": description_with_angle
                    }
                    analysis_text = json.dumps(analysis_json)
                    print(
                        f"DEBUG: Created JSON analysis for theme image (type and description with angle shot)")

            # Create UploadedImage object with analysis
            uploaded_image = UploadedImage(
                local_path=local_path,
                cloud_url=cloud_url,
                original_filename=file.name,
                uploaded_by=user_id,
                file_size=file.size,
                category=category,
                analysis=analysis_text,  # Store combined analysis for theme, or original for others
                ornament_type=ornament_type if category == 'theme' else "",  # Only for theme images
                angle_shot=angle_shot if category == 'theme' else "",  # Only for theme images
                # Only for theme images
                theme_description=theme_description if category == 'theme' else ""
            )

            uploaded_images.append(uploaded_image)

        # Add to the appropriate category in the collection item
        category_field = f"uploaded_{category}_images"
        if not hasattr(item, category_field):
            setattr(item, category_field, [])

        current_images = getattr(item, category_field)
        current_images.extend(uploaded_images)
        setattr(item, category_field, current_images)

        # Save the collection
        collection.items[0] = item
        collection.save()

        # Return the uploaded images data
        response_data = []
        for img in uploaded_images:
            response_data.append({
                'id': str(img.id) if hasattr(img, 'id') else None,
                'local_path': img.local_path,
                'cloud_url': img.cloud_url,
                'original_filename': img.original_filename,
                'uploaded_by': img.uploaded_by,
                'uploaded_at': img.uploaded_at.isoformat(),
                'file_size': img.file_size,
                'category': img.category,
                'analysis': img.analysis if hasattr(img, 'analysis') else ''
            })

        return Response({
            'success': True,
            'uploaded_images': response_data,
            'message': f'Successfully uploaded {len(uploaded_images)} {category} image(s)'
        })

    except Exception as e:
        import traceback
        print(f"DEBUG: Exception occurred in upload_workflow_image: {str(e)}")
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['DELETE'])
@csrf_exempt
@authenticate
def api_remove_workflow_image(request, project_id, collection_id):
    """Remove a workflow image from a specific category"""
    try:
        data = json.loads(request.body)
        image_id = data.get('image_id')
        cloud_url = data.get('cloud_url')
        category = data.get('category')

        if not category:
            return Response({'error': 'Category is required'}, status=400)

        # Use cloud_url as primary identifier, fallback to image_id
        if not cloud_url and not image_id:
            return Response({'error': 'Image identifier (cloud_url or image_id) is required'}, status=400)

        # Normalize category (convert plural to singular)
        category_mapping = {
            'themes': 'theme',
            'backgrounds': 'background',
            'poses': 'pose',
            'locations': 'location',
            'colors': 'color'
        }
        normalized_category = category_mapping.get(category, category)

        if normalized_category not in ['theme', 'background', 'pose', 'location', 'color']:
            return Response({'error': 'Invalid category'}, status=400)

        category = normalized_category

        # Get the collection
        collection = Collection.objects.get(id=collection_id)
        if not collection.items:
            return Response({'error': 'No collection items found'}, status=404)

        item = collection.items[0]

        # Get the appropriate category field
        category_field = f"uploaded_{category}_images"
        if not hasattr(item, category_field):
            return Response({'error': f'No {category} images found'}, status=404)

        current_images = getattr(item, category_field, [])

        # Filter out the image to delete - match by cloud_url first, then by id
        original_count = len(current_images)
        new_images = []
        for img in current_images:
            # Match by cloud_url if provided
            if cloud_url and hasattr(img, 'cloud_url') and img.cloud_url == cloud_url:
                continue  # Skip this image
            # Match by id if provided and cloud_url didn't match
            elif image_id and hasattr(img, 'id') and str(img.id) == str(image_id):
                continue  # Skip this image
            # Keep the image if it doesn't match
            new_images.append(img)

        if len(new_images) == original_count:
            return Response({'error': 'Image not found'}, status=404)

        # Update the category field
        setattr(item, category_field, new_images)
        collection.items[0] = item
        collection.save()

        return Response({
            'success': True,
            'message': f'{category} image removed successfully'
        })

    except DoesNotExist:
        return Response({'error': 'Collection not found'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
def api_project_setup_select(request, project_id, collection_id):
    """API wrapper for project setup select - saves user selections and generates prompts"""
    try:
        from .utils import call_gemini_api, parse_gemini_response

        # Handle both JSON and FormData requests
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle FormData (with image uploads)
            data = json.loads(request.POST.get('selections', '{}'))
            uploaded_files = {}
            for category in ['theme', 'background', 'pose', 'location', 'color']:
                files = request.FILES.getlist(f'uploaded_{category}_images')
                if files:
                    uploaded_files[category] = files
        else:
            # Handle JSON request
            data = json.loads(request.body)
            uploaded_files = {}

        # Get the collection
        try:
            collection = Collection.objects.get(id=collection_id)
        except DoesNotExist:
            return Response({'error': 'Collection not found'}, status=404)

        # Get the first item
        if not collection.items:
            return Response({'error': 'No collection items found'}, status=404)

        item = collection.items[0]

        # Update selected items
        item.selected_themes = data.get('themes', [])
        item.selected_backgrounds = data.get('backgrounds', [])
        item.selected_poses = data.get('poses', [])
        item.selected_locations = data.get('locations', [])
        item.selected_colors = data.get('colors', [])

        # Update new color picker fields
        item.picked_colors = data.get('pickedColors', [])
        item.color_instructions = data.get('colorInstructions', '')
        item.global_instructions = data.get('globalInstructions', '')
        print("global INstructions : ", item.global_instructions)

        # Note: Uploaded images are now handled by the separate upload endpoint
        # This endpoint only handles selections and prompt generation

        # -----------------------------
        # Generate prompts using Gemini AI
        # -----------------------------
        # Collect analysis by category for targeted prompt generation
        category_analysis = {
            'theme': [],
            'background': [],
            'pose': [],
            'location': [],
            'color': []
        }
        has_uploaded_images = False
        categories_with_uploads = []

        # Check each category for uploaded images and collect their stored analysis
        # Use master analysis if multiple images exist, otherwise use individual analysis
        for category in ['theme', 'background', 'pose', 'location', 'color']:
            category_field = f"uploaded_{category}_images"
            if hasattr(item, category_field):
                uploaded_imgs = getattr(item, category_field)
                if uploaded_imgs:
                    has_uploaded_images = True
                    categories_with_uploads.append(category)

                    # Check if master analysis exists for this category (for multiple images)
                    has_master_analysis = (
                        hasattr(item, 'master_analyses') and
                        item.master_analyses and
                        category in item.master_analyses and
                        item.master_analyses[category] and
                        item.master_analyses[category].strip()
                    )

                    # If multiple images and master analysis exists, use master analysis
                    if len(uploaded_imgs) > 1 and has_master_analysis:
                        print(
                            f"DEBUG: Using stored master analysis for {category} category ({len(uploaded_imgs)} images)")
                        master_analysis_text = item.master_analyses[category].strip(
                        )
                        # For theme category, extract description from JSON if it's stored as JSON
                        if category == 'theme':
                            try:
                                # Try to parse as JSON
                                master_analysis_json = json.loads(
                                    master_analysis_text)
                                if isinstance(master_analysis_json, dict) and 'description' in master_analysis_json:
                                    master_analysis_text = master_analysis_json['description'].strip(
                                    )
                                    print(
                                        f"DEBUG: Extracted description from theme master analysis JSON")
                            except (json.JSONDecodeError, TypeError):
                                # Not JSON, use as-is
                                pass
                        # Add master analysis for all images in this category
                        for img in uploaded_imgs:
                            category_analysis[category].append({
                                'filename': img.original_filename,
                                'analysis': master_analysis_text
                            })
                    else:
                        # Use individual analysis for each image (single image or no master analysis yet)
                        for img in uploaded_imgs:
                            # Use stored analysis if available, otherwise provide generic instruction
                            if hasattr(img, 'analysis') and img.analysis and img.analysis.strip():
                                category_analysis[category].append({
                                    'filename': img.original_filename,
                                    'analysis': img.analysis
                                })
                            else:
                                # Fallback if analysis is not available
                                category_analysis[category].append({
                                    'filename': img.original_filename,
                                    'analysis': "analyze lighting, style, subject composition, camera angle, and color mood from this reference image."
                                })

        # Generate master analysis for categories with multiple images (only if not already present)
        # For each category with more than one image, generate a master analysis for each image
        # that combines all analyses from that category into a comprehensive paragraph
        for category in ['theme', 'background', 'pose', 'location', 'color']:
            category_field = f"uploaded_{category}_images"
            if hasattr(item, category_field):
                uploaded_imgs = getattr(item, category_field)
                # Check if there are more than one image in this category
                if uploaded_imgs and len(uploaded_imgs) > 1:
                    # Check if master analysis already exists
                    has_master_analysis = (
                        hasattr(item, 'master_analyses') and
                        item.master_analyses and
                        category in item.master_analyses and
                        item.master_analyses[category] and
                        item.master_analyses[category].strip()
                    )

                    if has_master_analysis:
                        print(
                            f"DEBUG: Master analysis already exists for {category} category, skipping generation")
                        continue

                    print(
                        f"DEBUG: Generating master analysis for {category} category with {len(uploaded_imgs)} images")

                    # Collect all analyses from this category
                    all_analyses = []
                    image_urls = []
                    for img in uploaded_imgs:
                        if hasattr(img, 'analysis') and img.analysis and img.analysis.strip():
                            # For theme category, extract description from JSON analysis
                            if category == 'theme':
                                try:
                                    # Try to parse as JSON
                                    analysis_json = json.loads(
                                        img.analysis.strip())
                                    if isinstance(analysis_json, dict) and 'description' in analysis_json:
                                        analysis_to_use = analysis_json['description'].strip(
                                        )
                                    else:
                                        # Fallback to theme_description if available
                                        if hasattr(img, 'theme_description') and img.theme_description and img.theme_description.strip():
                                            analysis_to_use = img.theme_description.strip()
                                        else:
                                            analysis_to_use = img.analysis.strip()
                                except (json.JSONDecodeError, TypeError):
                                    # Not JSON, fallback to theme_description or analysis
                                    if hasattr(img, 'theme_description') and img.theme_description and img.theme_description.strip():
                                        analysis_to_use = img.theme_description.strip()
                                    else:
                                        analysis_to_use = img.analysis.strip()
                            else:
                                analysis_to_use = img.analysis.strip()

                            all_analyses.append({
                                'filename': img.original_filename,
                                'analysis': analysis_to_use,
                                'cloud_url': img.cloud_url if hasattr(img, 'cloud_url') else None
                            })
                            if hasattr(img, 'cloud_url') and img.cloud_url:
                                image_urls.append(img.cloud_url)

                    # If we have multiple analyses, generate master analysis for each image
                    if len(all_analyses) > 1:
                        # Create a prompt to combine all analyses into a master paragraph
                        # Special handling for theme category to include ornament information
                        if category == 'theme':
                            master_prompt = f"""You are a professional image analysis expert specializing in theme analysis. I have {len(all_analyses)} reference images in the {category} category, each with their own theme description (artistic style, mood, creative concept).

Your task is to create a comprehensive master theme description that synthesizes all the individual theme descriptions into a single, cohesive paragraph. The master theme description MUST:
1. Combine all the key artistic styles, moods, and creative concepts from all images
2. Identify common themes, patterns, and aesthetic qualities across all images
3. Highlight unique elements that complement each other
4. Create a unified description that captures the overall artistic style and mood of the entire set
5. Focus on artistic style, mood, and creative concept (ornament type and angle shot information are not needed here)
6. Be written as a flowing, descriptive paragraph (not bullet points)

Individual theme descriptions:
"""
                        elif category == 'background':
                            master_prompt = f"""You are a professional image analysis expert specializing in background and ornament analysis. I have {len(all_analyses)} reference images in the {category} category, each with their own detailed analysis. 

Your task is to create a comprehensive master analysis that synthesizes all the individual analyses into a single, cohesive paragraph. The master analysis MUST:
1. Combine all the key visual elements, styles, and characteristics from all images
2. Identify common themes, patterns, and aesthetic qualities across all images
3. Highlight unique elements that complement each other
4. Create a unified description that captures the overall style and mood of the entire set
5. CRITICALLY IMPORTANT: If ornaments are mentioned, include ALL SPECIFIC ornament types with ALL MODIFIERS and SUBCATEGORIES (e.g., "long necklace", "short necklace", "multi-strand pearl necklace", "jhumka-style earrings", "stud earrings", "delicate necklace", etc.) - DO NOT use generic terms if specific descriptors are available
6. CRITICALLY IMPORTANT: Preserve ALL ornament type modifiers and subcategories exactly as mentioned
7. Be written as a flowing, descriptive paragraph (not bullet points)

Individual analyses:
"""
                        else:
                            master_prompt = f"""You are a professional image analysis expert. I have {len(all_analyses)} reference images in the {category} category, each with their own detailed analysis. 

Your task is to create a comprehensive master analysis that synthesizes all the individual analyses into a single, cohesive paragraph. The master analysis should:
1. Combine all the key visual elements, styles, and characteristics from all images
2. Identify common themes, patterns, and aesthetic qualities across all images
3. Highlight unique elements that complement each other
4. Create a unified description that captures the overall style and mood of the entire set
5. Be written as a flowing, descriptive paragraph (not bullet points)

Individual analyses:
"""

                        for idx, img_data in enumerate(all_analyses, 1):
                            master_prompt += f"\nImage {idx} ({img_data['filename']}):\n{img_data['analysis']}\n"

                        if category == 'theme':
                            master_prompt += f"\n\nGenerate a comprehensive master theme description paragraph that synthesizes all the above theme descriptions for the {category} category. Focus on artistic style, mood, and creative concept. The paragraph should be detailed, cohesive, and capture the essence of all the reference images combined. Do NOT include ornament type or angle shot information - only the theme description (artistic style, mood, creative concept)."
                        elif category == 'background':
                            master_prompt += f"\n\nGenerate a comprehensive master analysis paragraph that synthesizes all the above analyses for the {category} category. If ornaments are mentioned, the paragraph MUST include all SPECIFIC ornament types WITH ALL MODIFIERS and SUBCATEGORIES (e.g., 'long necklace', 'jhumka-style earrings', etc.) - DO NOT use generic terms. The paragraph should be detailed, cohesive, and capture the essence of all the reference images combined."
                        else:
                            master_prompt += f"\n\nGenerate a comprehensive master analysis paragraph that synthesizes all the above analyses for the {category} category. The paragraph should be detailed, cohesive, and capture the essence of all the reference images combined."

                        # Generate master analysis using Gemini API
                        try:
                            from .utils import call_gemini_api
                            master_analysis = call_gemini_api(master_prompt)

                            if master_analysis and master_analysis.strip():
                                master_analysis_text = master_analysis.strip()

                                # For theme category, the master analysis should already be just the theme description
                                # (since we used theme_description from individual images to build it)
                                if category == 'theme':
                                    # The master_analysis_text should already be the theme description only
                                    # But we ensure it doesn't contain ornament type or angle shot
                                    print(
                                        f"DEBUG: Master theme analysis generated (theme description only)")

                                # Store master analysis in the database for this category
                                if not hasattr(item, 'master_analyses') or item.master_analyses is None:
                                    item.master_analyses = {}
                                item.master_analyses[category] = master_analysis_text
                                print(
                                    f"DEBUG: Stored master analysis for {category} category in database")

                                # Update each image's analysis with the master analysis
                                for img in uploaded_imgs:
                                    img.analysis = master_analysis_text
                                    print(
                                        f"DEBUG: Updated master analysis for {img.original_filename} in {category} category")

                                # Also update the category_analysis dictionary for all images in this category
                                for img_data in category_analysis[category]:
                                    img_data['analysis'] = master_analysis_text

                                print(
                                    f"DEBUG: Successfully generated and applied master analysis for {category} category")
                            else:
                                print(
                                    f"⚠️ Master analysis generation returned empty for {category} category")
                        except Exception as e:
                            print(
                                f"⚠️ Error generating master analysis for {category} category: {str(e)}")
                            import traceback
                            traceback.print_exc()

        # Build category-specific analysis strings for each prompt type
        def build_analysis_string(categories):
            """Build analysis string for specific categories
            Uses master analysis if multiple images exist, otherwise uses individual analysis
            """
            analysis_text = ""
            for cat in categories:
                if category_analysis[cat]:
                    category_field = f"uploaded_{cat}_images"
                    uploaded_imgs = getattr(item, category_field, []) if hasattr(
                        item, category_field) else []

                    # Check if master analysis exists for this category (multiple images)
                    has_master_analysis = (
                        hasattr(item, 'master_analyses') and
                        item.master_analyses and
                        cat in item.master_analyses and
                        item.master_analyses[cat] and
                        item.master_analyses[cat].strip()
                    )

                    # If multiple images and master analysis exists, use master analysis (must)
                    if len(uploaded_imgs) > 1 and has_master_analysis:
                        master_analysis_text = item.master_analyses[cat].strip(
                        )
                        # For theme category, extract description from JSON if it's stored as JSON
                        if cat == 'theme':
                            try:
                                # Try to parse as JSON
                                master_analysis_json = json.loads(
                                    master_analysis_text)
                                if isinstance(master_analysis_json, dict) and 'description' in master_analysis_json:
                                    master_analysis_text = master_analysis_json['description'].strip(
                                    )
                                    print(
                                        f"DEBUG: Extracted description from theme master analysis JSON in build_analysis_string")
                            except (json.JSONDecodeError, TypeError):
                                # Not JSON, use as-is
                                pass
                        analysis_text += f"\n{cat.capitalize()} Images ({len(uploaded_imgs)} uploaded) - Master Analysis:\n"
                        analysis_text += f"{master_analysis_text}\n"
                    else:
                        # Use individual analysis for each image (single image or no master analysis)
                        analysis_text += f"\n{cat.capitalize()} Images ({len(category_analysis[cat])} uploaded):\n"
                        for img_data in category_analysis[cat]:
                            analysis_text += f"- {img_data['filename']}: {img_data['analysis']}\n"
            return analysis_text

        # Build analysis strings for each prompt type
        # Note: white_background doesn't use any analysis (left as is per requirements)
        background_replace_analysis = build_analysis_string(
            ['theme', 'background'])
        model_image_analysis = build_analysis_string(
            ['theme', 'background', 'pose', 'color'])
        campaign_image_analysis = build_analysis_string(
            ['theme', 'background', 'pose', 'location', 'color'])

        # Prepare color information for model_image (if no color images uploaded)
        # These will be used in the prompt to show color priority
        picked_colors_for_model = ""
        selected_colors_for_model = ""
        if 'color' not in categories_with_uploads:
            if item.picked_colors:
                picked_colors_for_model = ', '.join(
                    item.picked_colors) or 'None'
            elif item.selected_colors:
                selected_colors_for_model = ', '.join(
                    item.selected_colors) or 'None'
        else:
            # If color images are uploaded, they take priority
            picked_colors_for_model = 'Using uploaded color images'
            selected_colors_for_model = 'Using uploaded color images'

        # Build full uploaded images analysis for general context (used in the prompt)
        # Use master analysis if multiple images exist, otherwise use individual analysis
        uploaded_images_analysis = ""
        for category in ['theme', 'background', 'pose', 'location', 'color']:
            if category_analysis[category]:
                category_field = f"uploaded_{category}_images"
                uploaded_imgs = getattr(item, category_field, []) if hasattr(
                    item, category_field) else []

                # Check if master analysis exists for this category (multiple images)
                has_master_analysis = (
                    hasattr(item, 'master_analyses') and
                    item.master_analyses and
                    category in item.master_analyses and
                    item.master_analyses[category] and
                    item.master_analyses[category].strip()
                )

                # If multiple images and master analysis exists, use master analysis (must)
                if len(uploaded_imgs) > 1 and has_master_analysis:
                    master_analysis_text = item.master_analyses[category].strip(
                    )
                    uploaded_images_analysis += f"\n{category.capitalize()} Images ({len(uploaded_imgs)} uploaded) - Master Analysis:\n"
                    uploaded_images_analysis += f"{master_analysis_text}\n"
                else:
                    # Use individual analysis for each image (single image or no master analysis)
                    uploaded_images_analysis += f"\n{category.capitalize()} Images ({len(category_analysis[category])} uploaded):\n"
                    for img_data in category_analysis[category]:
                        uploaded_images_analysis += f"- {img_data['filename']}: {img_data['analysis']}\n"

        # Determine final selections - prioritize uploaded images over suggestions
        # If images are uploaded for a category, ignore selected suggestions for that category
        final_themes = []
        final_backgrounds = []
        final_poses = []
        final_locations = []
        final_colors = []

        # Only use selected/suggested items for categories that DON'T have uploaded images
        if 'theme' not in categories_with_uploads:
            final_themes = item.selected_themes if item.selected_themes else (
                item.suggested_themes[:3] if item.suggested_themes else [])

        if 'background' not in categories_with_uploads:
            final_backgrounds = item.selected_backgrounds if item.selected_backgrounds else (
                item.suggested_backgrounds[:3] if item.suggested_backgrounds else [])

        if 'pose' not in categories_with_uploads:
            final_poses = item.selected_poses if item.selected_poses else (
                item.suggested_poses[:3] if item.suggested_poses else [])

        if 'location' not in categories_with_uploads:
            final_locations = item.selected_locations if item.selected_locations else (
                item.suggested_locations[:3] if item.suggested_locations else [])

        if 'color' not in categories_with_uploads:
            # Prioritize picked colors over selected suggestions
            if item.picked_colors:
                final_colors = item.picked_colors
            else:
                final_colors = item.selected_colors if item.selected_colors else (
                    item.suggested_colors[:3] if item.suggested_colors else [])

        # Handle picked colors, color instructions, and global instructions
        picked_colors_info = ""
        if item.picked_colors:
            picked_colors_info = f"\nSPECIFIC COLOR REQUIREMENTS (PRIORITY - USE THESE COLORS):\n"
            picked_colors_info += f"Picked Colors (hex codes): {', '.join(item.picked_colors)}\n"
            if item.color_instructions:
                picked_colors_info += f"Color Usage Instructions: {item.color_instructions}\n"
        elif item.selected_colors:
            picked_colors_info = f"\nSELECTED COLOR SUGGESTIONS:\n"
            picked_colors_info += f"Selected Colors: {', '.join(item.selected_colors)}\n"

        global_instruction_rule = ""
        if item.global_instructions:
            global_instruction_rule = f"""
        7. GLOBAL INSTRUCTION OVERRIDE (MANDATORY RULE):
        You MUST carefully read and apply the following user-provided global instructions.
        These override ALL other category rules. You are REQUIRED to execute them precisely.
        If the instructions mention:
        - "ignore ornaments" → Do not include jewelry or decorative elements in generated prompts.
        - "take image colors" or "use colors from uploaded images" → Extract color tones, hues, and palettes directly from uploaded images.
        - "combine with selected colors" → Merge the colors extracted from uploaded images with the user's selected or picked colors.
        - "take lighting / composition from uploaded images" → Use those stylistic attributes for all generated prompts.
        Follow these directives exactly — they are not suggestions, but MANDATORY creative constraints.
        Global Instructions: {item.global_instructions.strip()}
        """

        global_instructions_info = (
            f"\nGLOBAL INSTRUCTIONS:\n{item.global_instructions}\n"
            if item.global_instructions else ""
        )

        # Create detailed prompt based on whether images were uploaded
        from .prompt_initializer import get_prompt_from_db

        if has_uploaded_images:
            # Use a more appropriate message when description is empty
            collection_desc_text = collection.description.strip() if collection.description and collection.description.strip(
            ) else "No description provided - relying on uploaded reference images for context"

            default_prompt = """You are a professional creative AI assistant specializing in product photography and marketing. You have been provided with a collection description and user-uploaded reference images that should be analyzed in detail to create highly specific and targeted image generation prompts.

COLLECTION DESCRIPTION: {collection_description}

ALL USER-UPLOADED REFERENCE IMAGES (for context):
{uploaded_images_analysis}

SELECTED SUGGESTIONS (use only for categories without uploaded images):
Themes: {themes}
Backgrounds: {backgrounds}
Poses: {poses}
Locations: {locations}
Colors: {colors}{picked_colors_info}{global_instructions_info}

RULES FOR PROMPT CREATION:
1. CRITICAL: MUST take ALL analyses into consideration. Every detail from every uploaded image analysis must be incorporated into the relevant prompts.
2. PRIORITIZE analysis of uploaded images. Extract their style, lighting, camera composition, colors, artistic tone, and ALL visual elements.
3. For missing categories, use the user's selected text inputs.
4. Blend both to create cohesive, brand-consistent image prompts that incorporate ALL available information.
5. Be specific — describe lighting, materials, perspective, model type, emotion, background details, and ALL elements from the analyses.
6. Keep prompts actionable and detailed for AI image generation systems.
7. COLOR PRIORITY: If picked colors are provided, use them as the primary color scheme. If only selected suggestions are provided, use those instead.
8. MODEL ATTIRE: For MODEL_IMAGE and CAMPAIGN_IMAGE, the model's attire MUST be changed according to the theme analysis. Extract specific clothing details, fabric types, colors, patterns, and styling elements from theme analysis.
9. MODEL CONSISTENCY (CRITICAL): For MODEL_IMAGE and CAMPAIGN_IMAGE, the model MUST look EXACTLY the same across ALL generated images. Maintain EXACT same facial structure (jawline, cheekbones, chin, forehead, facial proportions), EXACT same eye structure (eye shape, size, spacing, eyelid, eyebrow), EXACT same nose structure, EXACT same mouth structure, EXACT same age appearance (do NOT change age - maintain exact same age look), EXACT same skin characteristics (skin texture, tone, undertones, complexion, facial maturity), EXACT same hair (color, texture, style, length, hairline), and EXACT same body proportions (height, build, body shape, muscle definition) across ALL images.
10. MODEL ACCURACY: For MODEL_IMAGE and CAMPAIGN_IMAGE, ensure the model is 100% accurate - realistic human features, accurate facial proportions, natural body proportions, authentic skin texture, and lifelike appearance. No distortions, no unrealistic features, no AI artifacts.
{global_instruction_rule}

IMPORTANT - USE SPECIFIC ANALYSIS FOR EACH PROMPT TYPE:

1. WHITE_BACKGROUND:
   - DO NOT use any uploaded image analysis
   - Create a clean, professional white background product photography prompt
   - Focus on product isolation, sharp focus, and studio lighting
   - Analysis to use: NONE (ignore all uploaded images for this prompt)

2. BACKGROUND_REPLACE:
   - USE ONLY theme and background image analysis
   - Incorporate visual elements, style, and aesthetic from theme and background images
   - Maintain product integrity while applying themed background
   - Analysis to use: {background_replace_analysis}

3. MODEL_IMAGE:
   - CRITICAL: MUST take ALL analyses into consideration (theme, background, pose, and color image analysis)
   - For colors: prioritize uploaded color images if available, otherwise use picked colors, otherwise use selected colors
   - Incorporate poses, expressions, styling, and color palettes from uploaded images
   - MANDATORY: Change the attire of the model according to the theme analysis. The model's clothing, style, and overall appearance MUST match the theme and background aesthetic from the uploaded images. Extract specific clothing details, fabric types, colors, and styling elements from the theme analysis.
   - MODEL CONSISTENCY REQUIREMENT (CRITICAL): The model must look EXACTLY the same across ALL generated images with:
     * EXACT same facial structure: jawline, cheekbones, chin, forehead, facial proportions, face width, face length
     * EXACT same eye structure: eye shape, eye size, eye spacing, eyelid shape, eyebrow shape and position
     * EXACT same nose structure: nose shape, nose size, nostril shape, bridge height
     * EXACT same mouth structure: lip shape, lip size, lip thickness, mouth width
     * EXACT same age appearance: maintain the exact same age look - do NOT make the model look younger or older
     * EXACT same skin characteristics: skin texture, skin tone, skin undertones, complexion, facial maturity
     * EXACT same hair: hair color, hair texture, hair style, hair length, hairline
     * EXACT same body proportions: height, build, body shape, muscle definition
   - MODEL ACCURACY REQUIREMENT: The model must be 100% accurate - realistic human features, accurate facial proportions, natural body proportions, authentic skin texture, and lifelike appearance. No distortions, no unrealistic features, no AI artifacts.
   - Analysis to use: {model_image_analysis}
   - Color priority: Uploaded color images > Picked colors ({picked_colors_for_model}) > Selected colors ({selected_colors_for_model})

4. CAMPAIGN_IMAGE:
   - CRITICAL: MUST take ALL category analyses into consideration (theme, background, pose, location, color)
   - Incorporate comprehensive visual elements from ALL uploaded reference images - every detail matters
   - MANDATORY: Change the attire of the model according to the theme analysis. The model's clothing, style, and overall appearance MUST match the theme aesthetic from the uploaded images. Extract specific clothing details, fabric types, colors, and styling elements from the theme analysis.
   - MODEL CONSISTENCY REQUIREMENT (CRITICAL): The model must look EXACTLY the same across ALL generated images with:
     * EXACT same facial structure: jawline, cheekbones, chin, forehead, facial proportions, face width, face length
     * EXACT same eye structure: eye shape, eye size, eye spacing, eyelid shape, eyebrow shape and position
     * EXACT same nose structure: nose shape, nose size, nostril shape, bridge height
     * EXACT same mouth structure: lip shape, lip size, lip thickness, mouth width
     * EXACT same age appearance: maintain the exact same age look - do NOT make the model look younger or older
     * EXACT same skin characteristics: skin texture, skin tone, skin undertones, complexion, facial maturity
     * EXACT same hair: hair color, hair texture, hair style, hair length, hairline
     * EXACT same body proportions: height, build, body shape, muscle definition
   - MODEL ACCURACY REQUIREMENT: The model must be 100% accurate - realistic human features, accurate facial proportions, natural body proportions, authentic skin texture, and lifelike appearance. No distortions, no unrealistic features, no AI artifacts.
   - Create a cohesive campaign shot that captures mood, composition, and style from all references
   - Analysis to use: {campaign_image_analysis}

Generate prompts for the following 4 types. Respond ONLY in valid JSON:
{{
    "white_background": "Detailed prompt for white background product photography (DO NOT use uploaded image analysis)",
    "background_replace": "Detailed prompt using ONLY theme and background analysis. Incorporate visual elements, style, and aesthetic from theme and background images.",
    "model_image": "Detailed prompt using ALL analyses (theme, background, pose, and color). MUST change model attire to match theme analysis exactly. CRITICAL: Model must look EXACTLY the same with EXACT same facial structure (jawline, cheekbones, chin, forehead, facial proportions), EXACT same eye structure (eye shape, size, spacing, eyelid, eyebrow), EXACT same nose structure, EXACT same mouth structure, EXACT same age appearance (do NOT change age), EXACT same skin characteristics, EXACT same hair, and EXACT same body proportions across ALL images. Model must be 100% accurate with realistic features, accurate facial proportions, natural body proportions, and lifelike appearance. Include specific clothing details, fabric types, colors, and styling from theme analysis.",
    "campaign_image": "Detailed prompt using ALL category analyses (theme, background, pose, location, color). MUST change model attire to match theme analysis exactly. CRITICAL: Model must look EXACTLY the same with EXACT same facial structure (jawline, cheekbones, chin, forehead, facial proportions), EXACT same eye structure (eye shape, size, spacing, eyelid, eyebrow), EXACT same nose structure, EXACT same mouth structure, EXACT same age appearance (do NOT change age), EXACT same skin characteristics, EXACT same hair, and EXACT same body proportions across ALL images. Model must be 100% accurate with realistic features, accurate facial proportions, natural body proportions, and lifelike appearance. Include specific clothing details, fabric types, colors, and styling from theme analysis. Create a cohesive campaign shot capturing mood, composition, and style from all references."
}}"""

            gemini_prompt = get_prompt_from_db(
                'generation_prompt_with_images',
                default_prompt,
                collection_description=collection_desc_text,
                uploaded_images_analysis=uploaded_images_analysis,
                background_replace_analysis=background_replace_analysis or 'None',
                model_image_analysis=model_image_analysis or 'None',
                campaign_image_analysis=campaign_image_analysis or 'None',
                picked_colors_for_model=picked_colors_for_model or 'None',
                selected_colors_for_model=selected_colors_for_model or 'None',
                themes=', '.join(final_themes) or 'None',
                backgrounds=', '.join(final_backgrounds) or 'None',
                poses=', '.join(final_poses) or 'None',
                locations=', '.join(final_locations) or 'None',
                colors=', '.join(final_colors) or 'None',
                picked_colors_info=picked_colors_info,
                global_instructions_info=global_instructions_info,
                global_instruction_rule=global_instruction_rule
            )
        else:
            default_prompt = """You are a professional creative AI assistant. Analyze the collection description and user selections carefully and generate structured image generation prompts.

Collection Description: {collection_description}
Selected Themes: {themes}
Selected Backgrounds: {backgrounds}
Selected Poses: {poses}
Selected Locations: {locations}
Selected Colors: {colors}{picked_colors_info}{global_instructions_info}

{instructions}

{rules}
{global_instruction_rule}

Generate prompts for the following 4 types. Respond ONLY in valid JSON:
{{
    "white_background": "Prompt for white background images of the product, sharp, clean, isolated.",
    "background_replace": "Prompt for images with themed backgrounds while keeping the product identical.",
    "model_image": "Prompt to generate realistic model wearing/holding the product. Model must be 100% accurate with realistic human features, accurate facial proportions, natural body proportions, authentic skin texture, and lifelike appearance. Match selected poses and expressions, photo should be focused mainly on the product.",
    "campaign_image": "Prompt for campaign/promotional shots with models and products in themed backgrounds, stylish composition. Model must be 100% accurate with realistic human features, accurate facial proportions, natural body proportions, authentic skin texture, and lifelike appearance."
}}"""

            # Use a more appropriate message when description is empty
            collection_desc_text = collection.description.strip() if collection.description and collection.description.strip(
            ) else "No description provided - relying on user selections for context"

            gemini_prompt = get_prompt_from_db(
                'generation_prompt_simple',
                default_prompt,
                collection_description=collection_desc_text,
                themes=', '.join(final_themes) or 'None',
                backgrounds=', '.join(final_backgrounds) or 'None',
                poses=', '.join(final_poses) or 'None',
                locations=', '.join(final_locations) or 'None',
                colors=', '.join(final_colors) or 'None',
                picked_colors_info=picked_colors_info,
                global_instructions_info=global_instructions_info,
                global_instruction_rule=global_instruction_rule
            )

        # Debug information
        print(
            f"DEBUG: Categories with uploaded images: {categories_with_uploads}")
        print(f"DEBUG: Has uploaded images: {has_uploaded_images}")
        print(
            f"DEBUG: Final selections - Themes: {final_themes}, Backgrounds: {final_backgrounds}, Poses: {final_poses}, Locations: {final_locations}, Colors: {final_colors}")

        # Call Gemini API
        print(f"DEBUG: Gemini prompt: {gemini_prompt}")
        ai_json_text = call_gemini_api(gemini_prompt)
        ai_response = parse_gemini_response(ai_json_text)

        # Fallback if parsing failed
        if not ai_response or "error" in ai_response or not isinstance(ai_response, dict):
            print("⚠️ Gemini API parsing failed, using fallback prompts")
            ai_response = {
                "white_background": "Professional product photography with clean white background, studio lighting, sharp focus on product details",
                "background_replace": "Same product with themed background replacement, maintaining product integrity and lighting",
                "model_image": "Realistic model wearing/holding the product, professional fashion photography, accurate facial features and body proportions, photo focused mainly on the product",
                "campaign_image": "Stylish campaign shot with model in themed setting, creative composition, promotional quality",
            }

        # Ensure all required keys exist
        required_keys = ["white_background",
                         "background_replace", "model_image", "campaign_image"]
        for key in required_keys:
            if key not in ai_response or not ai_response[key]:
                ai_response[key] = f"Generated prompt for {key.replace('_', ' ')} based on your collection theme"

        # Save prompts in item
        item.final_moodboard_prompt = gemini_prompt
        item.moodboard_explanation = ai_json_text
        item.generated_prompts = ai_response

        collection.save()

        print("✅ Prompts generated and saved successfully")
        print(f"Generated prompts: {ai_response}")

        return Response({
            'success': True,
            'selected': {
                'themes': item.selected_themes,
                'backgrounds': item.selected_backgrounds,
                'poses': item.selected_poses,
                'locations': item.selected_locations,
                'colors': item.selected_colors,
                'pickedColors': item.picked_colors,
                'colorInstructions': item.color_instructions,
                'globalInstructions': item.global_instructions,
            },
            'generated_prompts': ai_response,
            'message': 'Selections saved and prompts generated successfully'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)

# -------------------------
# Image Generation API Views (wrapper around existing views)
# -------------------------


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_generate_ai_images(request, collection_id):
    """API wrapper for generate AI images - now uses Celery"""
    from .tasks import generate_ai_images_task

    try:
        # Get user_id from request
        user_id = str(request.user.id) if hasattr(
            request, 'user') and request.user else None

        # Start Celery task
        task = generate_ai_images_task.delay(collection_id, user_id)

        return Response({
            "success": True,
            "message": "AI image generation started.",
            "task_id": task.id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@api_view(['POST'])
@csrf_exempt
@authenticate
def api_save_generated_images(request, collection_id):
    """API wrapper for save generated images"""
    return save_generated_images(request, collection_id)


@csrf_exempt
@api_view(['POST'])
@csrf_exempt
@authenticate
def api_upload_product_images(request, collection_id):
    """API wrapper for upload product images"""
    return upload_product_images_api(request, collection_id)


@csrf_exempt
@api_view(['POST'])
@csrf_exempt
@authenticate
def api_generate_all_product_model_images(request, collection_id):
    """
    API wrapper for generate all product model images.
    Now splits work into many single-image Celery tasks using a job_id so that
    results can be retrieved progressively.
    """
    from .tasks import generate_single_image_task
    from .models import Collection
    from celery import group
    import uuid

    try:
        user = getattr(request, "user", None)
        user_id = str(user.id) if user else None

        # Soft per-tenant concurrency limit (max 3 active jobs per user)
        if user_id:
            active_jobs = ImageGenerationJob.objects(
                user=user,
                status__in=["pending", "running"],
            ).count()
            if active_jobs >= 3:
                return Response(
                    {
                        "success": False,
                        "error": "Too many active image generation jobs. Please wait for existing jobs to finish.",
                    },
                    status=429,
                )

        collection = Collection.objects.get(id=collection_id)
        if not collection.items:
            return Response(
                {"success": False, "error": "No items found in collection."},
                status=400,
            )

        item = collection.items[0]

        # Cancel any other running jobs for this collection to prevent mixing batches
        # This ensures only the latest batch's images are shown
        other_running_jobs = ImageGenerationJob.objects(
            collection=collection,
            status__in=["pending", "running"],
        )
        for old_job in other_running_jobs:
            old_job.status = "failed"
            old_job.error = "Cancelled: New batch started"
            old_job.save()
            logger.info(f"Cancelled old job {old_job.job_id} for collection {collection_id}")

        # Clear existing generated images from all products before starting new batch
        # This ensures only images from the current batch are shown
        for product in item.product_images:
            if hasattr(product, 'generated_images'):
                product.generated_images = []
        
        # Save the collection to persist the cleared images
        collection.save()

        # Determine how many images will be generated (products x prompt keys)
        prompt_keys = list((item.generated_prompts or {}).keys())
        total_images = len(item.product_images) * len(prompt_keys)
        if total_images == 0:
            return Response(
                {"success": False, "error": "No products or prompts available for generation."},
                status=400,
            )

        job_id = uuid.uuid4().hex

        # Create job document for tracking
        job = ImageGenerationJob(
            job_id=job_id,
            user=user,
            project=collection.project,
            collection=collection,
            total_images=total_images,
            completed_images=0,
            status="running",
        )
        job.save()

        # Build a Celery group of single-image tasks
        task_sigs = []
        for idx in range(len(item.product_images)):
            for key in prompt_keys:
                task_sigs.append(
                    generate_single_image_task.s(
                        job_id,
                        str(collection_id),
                        user_id,
                        idx,
                        key,
                    )
                )

        result_group = group(task_sigs).apply_async()

        # Return job_id for progressive polling; include group id for backward compatibility
        return Response({
            "success": True,
            "message": "Image generation started.",
            "job_id": job_id,
            "task_id": result_group.id,
            "total_images": total_images,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@api_view(['GET'])
@authenticate
def get_task_status(request, task_id):
    """Get the status of a Celery task"""
    from celery.result import AsyncResult

    try:
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
                response_data["error"] = str(
                    result.result) if result.result else "Task failed"
                response_data["success"] = False
        else:
            # Task is still running
            response_data["success"] = None  # In progress

        return Response(response_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@api_view(['GET'])
@authenticate
def api_job_images(request, job_id):
    """
    Return the current state of a bulk generation job without blocking.
    This is used by the frontend to fetch images progressively as they finish.
    
    Also returns the latest collection data so frontend can display images immediately.
    """
    try:
        job = ImageGenerationJob.objects(job_id=job_id).first()
        if not job:
            return Response(
                {"success": False, "error": "Job not found."},
                status=404,
            )

        # Also fetch the latest collection data so frontend can display images
        collection_data = None
        try:
            collection = Collection.objects.get(id=job.collection.id)
            # Build collection data similar to api_collection_detail
            if collection.items:
                item = collection.items[0]
                collection_data = {
                    'id': str(collection.id),
                    'product_images': []
                }
                for product_img in item.product_images:
                    product_data = {
                        'uploaded_image_url': product_img.uploaded_image_url,
                        'uploaded_image_path': product_img.uploaded_image_path,
                        'generated_images': product_img.generated_images or []
                    }
                    collection_data['product_images'].append(product_data)
        except Exception as coll_error:
            print(f"Error fetching collection data for job {job_id}: {coll_error}")

        return Response(
            {
                "success": True,
                "job_id": job.job_id,
                "status": job.status,
                "total_images": job.total_images,
                "completed_images": job.completed_images,
                "images": job.images or [],
                "collection_data": collection_data,  # Include latest collection state
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@api_view(['GET'])
@authenticate
def api_collection_images_status(request, collection_id):
    """
    Quick endpoint to check if a collection has generated images.
    Useful for frontend polling to see when images are ready.
    """
    try:
        collection = Collection.objects.get(id=collection_id)
        if not collection.items:
            return Response({
                "success": True,
                "has_images": False,
                "total_products": 0,
                "total_generated_images": 0,
            })
        
        item = collection.items[0]
        total_products = len(item.product_images) if item.product_images else 0
        total_generated = sum(
            len(p.generated_images) if p.generated_images else 0
            for p in item.product_images
        )
        
        return Response({
            "success": True,
            "has_images": total_generated > 0,
            "total_products": total_products,
            "total_generated_images": total_generated,
            "products": [
                {
                    "index": idx,
                    "uploaded_image_url": p.uploaded_image_url,
                    "generated_count": len(p.generated_images) if p.generated_images else 0,
                    "generated_images": p.generated_images or []
                }
                for idx, p in enumerate(item.product_images)
            ]
        })
    except DoesNotExist:
        return Response({"success": False, "error": "Collection not found"}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@api_view(['POST'])
@csrf_exempt
@authenticate
def api_regenerate_product_model_image(request, collection_id):
    """API wrapper for regenerate product model image"""
    return regenerate_product_model_image(request, collection_id)


# -------------------------
# Model Management API Views
# -------------------------

@csrf_exempt
@api_view(['POST'])
@csrf_exempt
@authenticate
def api_upload_real_models(request, collection_id):
    """Upload real model images"""
    if request.method != "POST":
        return Response({"success": False, "error": "Invalid request method."})

    try:
        import cloudinary.uploader

        collection = Collection.objects.get(id=collection_id)
        if not collection.items:
            return Response({"success": False, "error": "No items found in collection."})

        item = collection.items[0]
        uploaded_files = request.FILES.getlist("images")

        if not uploaded_files:
            return Response({"success": False, "error": "No images uploaded."})

        local_dir = os.path.join(settings.MEDIA_ROOT, "model_images", "real")
        os.makedirs(local_dir, exist_ok=True)

        new_real_models = []

        for file in uploaded_files:
            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                file,
                folder="collection_real_models",
                overwrite=True
            )
            cloud_url = upload_result.get("secure_url")

            # Save locally
            local_path = os.path.join(local_dir, file.name)
            with open(local_path, "wb") as f:
                for chunk in file.chunks():
                    f.write(chunk)

            # Create entry
            entry = {"local": local_path,
                     "cloud": cloud_url, "name": file.name}
            new_real_models.append(entry)

        # Append to uploaded_model_images
        if not hasattr(item, "uploaded_model_images"):
            item.uploaded_model_images = []
        item.uploaded_model_images.extend(new_real_models)

        collection.save()

        return Response({
            "success": True,
            "count": len(new_real_models),
            "models": new_real_models
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)})


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_get_all_models(request, collection_id):
    """Get all models (AI generated and real uploaded)"""
    try:
        collection = Collection.objects.get(id=collection_id)
        if not collection.items:
            return Response({"success": False, "error": "No items found in collection."})

        item = collection.items[0]

        ai_models = item.generated_model_images or []
        real_models = item.uploaded_model_images or []
        selected_model = item.selected_model if hasattr(
            item, 'selected_model') else None

        return Response({
            "success": True,
            "ai_models": ai_models,
            "real_models": real_models,
            "selected_model": selected_model
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)})


@api_view(['POST'])
@csrf_exempt
def api_select_model(request, collection_id):
    """Select a single model (AI or Real)"""
    try:
        data = json.loads(request.body)
        model_type = data.get("type")  # 'ai' or 'real'
        # The model object with local/cloud paths
        model_data = data.get("model")

        if not model_type or not model_data:
            return Response({"success": False, "error": "Invalid model data"})

        collection = Collection.objects.get(id=collection_id)
        if not collection.items:
            return Response({"success": False, "error": "No items found in collection."})

        item = collection.items[0]

        # Save selected model
        item.selected_model = {
            "type": model_type,
            "local": model_data.get("local"),
            "cloud": model_data.get("cloud"),
            "name": model_data.get("name", "")
        }

        collection.save()

        return Response({
            "success": True,
            "selected_model": item.selected_model
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)})


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_invite_member(request, project_id):
    """Only project owner can invite existing users"""
    try:
        user = request.user
        data = json.loads(request.body)
        invitee_email = data.get("email")
        role = data.get("role", "viewer")

        # Find project
        project = Project.objects(id=project_id).first()
        if not project:
            return Response({"error": "Project not found"}, status=404)

        # Check if current user is an owner
        owner_member = next(
            (m for m in project.team_members if m.user.id == user.id and m.role == "owner"), None)
        if not owner_member:
            return Response({"error": "Only project owner can invite members"}, status=403)

        # Find invitee
        invitee = User.objects(email=invitee_email).first()
        if not invitee:
            return Response({"error": "User with this email not found"}, status=404)

        # Check if already a team member
        already_member = any(
            m.user.id == invitee.id for m in project.team_members)
        if already_member:
            return Response({"error": "User already part of the team"}, status=400)

        # Check if invite already sent
        existing_invite = ProjectInvite.objects(
            project=project, invitee=invitee, accepted=False).first()
        if existing_invite:
            return Response({"error": "Invite already pending"}, status=400)

        # Create invite
        invite = ProjectInvite(
            project=project, inviter=user, invitee=invitee, role=role)
        invite.save()

        return Response({
            "message": "Invitation sent successfully",
            "invite_id": str(invite.id),
            "invitee": invitee.email,
            "project": project.name,
            "role": role
        }, status=201)

    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_accept_invite(request, project_id):
    """Accept a pending project invite (legacy endpoint for specific project)"""
    try:
        user = request.user

        # Find pending invite
        invite = ProjectInvite.objects(
            project=project_id, invitee=user, accepted=False).first()
        if not invite:
            return Response({"error": "No pending invite found"}, status=404)

        # Add user to project team
        project = invite.project
        member = ProjectMember(user=user, role=invite.role)
        project.team_members.append(member)
        project.save()

        # Mark invite as accepted
        invite.accepted = True
        invite.save()

        # Also link project in user.projects list
        if project not in user.projects:
            user.projects.append(project)
            user.save()

        return Response({
            "message": "Invite accepted successfully",
            "project": project.name,
            "project_id": str(project.id),
            "role": invite.role
        }, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_accept_invite_by_id(request, invite_id):
    """Accept a pending project invite by invite ID"""
    try:
        user = request.user

        # Find pending invite by ID
        invite = ProjectInvite.objects(
            id=invite_id, invitee=user, accepted=False).first()
        if not invite:
            return Response({"error": "Invitation not found or already accepted"}, status=404)

        # Add user to project team
        project = invite.project
        member = ProjectMember(user=user, role=invite.role)
        project.team_members.append(member)
        project.save()

        # Mark invite as accepted
        invite.accepted = True
        invite.save()

        # Also link project in user.projects list
        if project not in user.projects:
            user.projects.append(project)
            user.save()

        return Response({
            "message": "Invitation accepted successfully",
            "project_name": project.name,
            "project_id": str(project.id),
            "role": invite.role
        }, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_reject_invite(request, invite_id):
    """Reject a pending project invite"""
    try:
        user = request.user

        # Find pending invite by ID
        invite = ProjectInvite.objects(
            id=invite_id, invitee=user, accepted=False).first()
        if not invite:
            return Response({"error": "Invitation not found or already processed"}, status=404)

        # Delete the invite
        invite.delete()

        return Response({
            "message": "Invitation rejected successfully"
        }, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_list_invites(request, project_id):
    """Get pending invitations for a specific project"""
    # Get all pending invites for this project (not just for the current user)
    invites = ProjectInvite.objects(
        project=project_id, accepted=False)
    data = [{
        "id": str(inv.id),
        "project": inv.project.name,
        "invitee": inv.invitee.email,
        "inviter": inv.inviter.full_name or inv.inviter.username,
        "role": inv.role,
        "created_at": inv.created_at.isoformat()
    } for inv in invites]
    return Response({"pending_invites": data})


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_list_all_invites(request):
    """Get ALL pending invitations for the current user (across all projects)"""
    invites = ProjectInvite.objects(invitee=request.user, accepted=False)
    data = [{
        "id": str(inv.id),
        "project_id": str(inv.project.id),
        "project_name": inv.project.name,
        "inviter_name": inv.inviter.full_name or inv.inviter.username,
        "inviter_email": inv.inviter.email,
        "role": inv.role,
        "created_at": inv.created_at.isoformat()
    } for inv in invites]
    return Response({"pending_invites": data})


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_available_users(request, project_id):
    """Get all users who are not yet members of this project"""
    try:
        project = Project.objects(id=project_id).first()
        if not project:
            return Response({"error": "Project not found"}, status=404)

        # Get IDs of users already in the project
        member_ids = [str(member.user.id) for member in project.team_members]

        # Get all users except those already in the project
        all_users = User.objects.all()
        available_users = []

        for user in all_users:
            if str(user.id) not in member_ids:
                available_users.append({
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name or user.username,
                    "username": user.username
                })

        return Response({"available_users": available_users})
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_update_member_role(request, project_id):
    """Update a team member's role - only project owner can perform this action"""
    try:
        user = request.user
        data = json.loads(request.body)
        member_user_id = data.get("user_id")
        new_role = data.get("role")

        if not member_user_id or not new_role:
            return Response({"error": "user_id and role are required"}, status=400)

        # Validate role
        if new_role not in ["owner", "editor", "viewer"]:
            return Response({"error": "Invalid role. Must be 'owner', 'editor', or 'viewer'"}, status=400)

        # Find project
        project = Project.objects(id=project_id).first()
        if not project:
            return Response({"error": "Project not found"}, status=404)

        # Check if current user is an owner
        owner_member = next(
            (m for m in project.team_members if str(m.user.id) == str(user.id) and m.role == "owner"), None)
        if not owner_member:
            return Response({"error": "Only project owner can update member roles"}, status=403)

        # Find the member to update
        member_to_update = next(
            (m for m in project.team_members if str(m.user.id) == str(member_user_id)), None)
        if not member_to_update:
            return Response({"error": "Member not found in project"}, status=404)

        # Prevent owner from changing their own role
        if str(member_to_update.user.id) == str(user.id):
            return Response({"error": "You cannot change your own role"}, status=400)

        # Prevent changing role of another owner
        if member_to_update.role == "owner":
            return Response({"error": "Cannot change the role of another owner"}, status=400)

        # Update the role
        member_to_update.role = new_role
        project.save()

        return Response({
            "message": "Member role updated successfully",
            "user_email": member_to_update.user.email,
            "new_role": new_role
        }, status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


# -------------------------
# Recent History API Views
# -------------------------

@api_view(['GET'])
@csrf_exempt
@authenticate
def api_recent_history(request):
    """Get recent image generation history for the authenticated user"""
    try:
        user = request.user
        user_id = str(user.id)

        # Get query parameters
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        days = int(request.GET.get('days', 30))  # Default to last 30 days

        # Calculate date range
        from datetime import datetime, timedelta, timezone
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Fetch recent history from both systems

        # 1. Get project-based image generation history
        # Filter to exclude individual image section activities and only include project-specific activities
        project_history = ImageGenerationHistory.objects(
            user_id=user_id,
            created_at__gte=start_date,
            created_at__lte=end_date,
            # Only include records that have a project or collection associated
            # AND exclude individual image section activities
            __raw__={
                "$and": [
                    {
                        "$or": [
                            {"project": {"$exists": True, "$ne": None}},
                            {"collection": {"$exists": True, "$ne": None}}
                        ]
                    },
                    {
                        # Exclude individual image section activities
                        "image_type": {
                            "$nin": [
                                # Individual image section activities
                                "white_background",
                                "background_change",
                                "model_with_ornament",
                                "real_model_with_ornament",
                                "campaign_shot_advanced",
                                # Individual image section regenerations
                                "white_background_regenerated",
                                "background_change_regenerated",
                                "model_with_ornament_regenerated",
                                "real_model_with_ornament_regenerated",
                                "campaign_shot_advanced_regenerated"
                            ]
                        }
                    }
                ]
            }
        ).order_by('-created_at')

        # 2. Get individual image generation history from imgbackendapp
        from imgbackendapp.mongo_models import OrnamentMongo
        individual_history = OrnamentMongo.objects(
            user_id=user_id,
            created_at__gte=start_date,
            created_at__lte=end_date
        ).order_by('-created_at')

        # Combine and format the results
        combined_history = []

        # Add project-based history
        for item in project_history:
            combined_history.append({
                'id': str(item.id),
                'type': 'project_image',
                'image_type': item.image_type,
                'image_url': item.image_url,
                'prompt': item.prompt,
                'original_prompt': item.original_prompt,
                'parent_image_id': item.parent_image_id,
                'created_at': item.created_at.isoformat(),
                'project': {
                    'id': str(item.project.id) if item.project else None,
                    'name': item.project.name if item.project else 'Unknown Project'
                },
                'collection': {
                    'id': str(item.collection.id) if item.collection else None
                },
                'metadata': item.metadata or {}
            })

        # Add individual image history
        for item in individual_history:
            combined_history.append({
                'id': str(item.id),
                'type': 'individual_image',
                'image_type': item.type,
                'image_url': item.generated_image_url,
                'prompt': item.prompt,
                'original_prompt': item.original_prompt,
                'parent_image_id': str(item.parent_image_id) if item.parent_image_id else None,
                'created_at': item.created_at.isoformat() if item.created_at else None,
                'project': None,
                'collection': None,
                'metadata': {
                    'uploaded_image_url': item.uploaded_image_url,
                    'model_image_url': getattr(item, 'model_image_url', None)
                }
            })

        # Sort by creation date (most recent first)
        combined_history.sort(key=lambda x: x['created_at'], reverse=True)

        # Apply pagination
        total_count = len(combined_history)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_history = combined_history[start_idx:end_idx]

        return Response({
            'success': True,
            'history': paginated_history,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total_count,
                'pages': (total_count + limit - 1) // limit
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_recent_projects(request):
    """Get recent project activity for the authenticated user"""
    try:
        user = request.user

        # Get query parameters
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 10))
        days = int(request.GET.get('days', 30))

        # Calculate date range
        from datetime import datetime, timedelta, timezone
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Get projects where user is a member
        user_projects = []
        all_projects = Project.objects.all()

        for project in all_projects:
            # Check if user is a team member
            user_member = None
            for member in project.team_members:
                if str(member.user.id) == str(user.id):
                    user_member = member
                    break

            if user_member:
                # Get recent activity for this project
                recent_activity = ImageGenerationHistory.objects(
                    project=project,
                    created_at__gte=start_date,
                    created_at__lte=end_date
                ).order_by('-created_at').limit(5)

                # Get collection info
                collection = Collection.objects(project=project).first()

                # Count total images in project
                total_images = 0
                if collection and collection.items:
                    for item in collection.items:
                        if item.product_images:
                            total_images += len(item.product_images)

                project_data = {
                    'id': str(project.id),
                    'name': project.name,
                    'about': project.about,
                    'created_at': project.created_at.isoformat(),
                    'updated_at': project.updated_at.isoformat(),
                    'status': project.status,
                    'user_role': user_member.role,
                    'total_images': total_images,
                    'collection_id': str(collection.id) if collection else None,
                    'recent_activity': []
                }

                # Add recent activity
                for activity in recent_activity:
                    project_data['recent_activity'].append({
                        'id': str(activity.id),
                        'image_type': activity.image_type,
                        'image_url': activity.image_url,
                        'created_at': activity.created_at.isoformat(),
                        'prompt': activity.prompt
                    })

                user_projects.append(project_data)

        # Sort by most recent activity
        user_projects.sort(key=lambda x: x['updated_at'], reverse=True)

        # Apply pagination
        total_count = len(user_projects)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_projects = user_projects[start_idx:end_idx]

        return Response({
            'success': True,
            'projects': paginated_projects,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total_count,
                'pages': (total_count + limit - 1) // limit
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_recent_images(request):
    """Get the 5 most recent images from ImageGenerationHistory for the authenticated user"""
    try:
        user = request.user
        user_id = str(user.id)

        # Get query parameters
        limit = int(request.GET.get('limit', 5))

        # Get the most recent images from ImageGenerationHistory
        recent_images = ImageGenerationHistory.objects(
            user_id=user_id
        ).order_by('-created_at').limit(limit)

        # Format the results
        images_list = []
        for item in recent_images:
            images_list.append({
                'id': str(item.id),
                'image_url': item.image_url,
                'image_type': item.image_type,
                'prompt': item.prompt or '',
                'created_at': item.created_at.isoformat() if item.created_at else None,
            })

        return Response({
            'success': True,
            'images': images_list,
            'count': len(images_list)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_recent_project_history(request):
    """Get recent image generation history for projects only (no individual images)"""
    try:
        user = request.user
        user_id = str(user.id)

        # Get query parameters
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        days = int(request.GET.get('days', 30))  # Default to last 30 days

        # Calculate date range
        from datetime import datetime, timedelta, timezone
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Get only project-based image generation history
        # Filter to exclude individual image section activities and only include project-specific activities
        project_history = ImageGenerationHistory.objects(
            user_id=user_id,
            created_at__gte=start_date,
            created_at__lte=end_date,
            # Only include records that have a project or collection associated
            # AND exclude individual image section activities
            __raw__={
                "$and": [
                    {
                        "$or": [
                            {"project": {"$exists": True, "$ne": None}},
                            {"collection": {"$exists": True, "$ne": None}}
                        ]
                    },
                    {
                        # Exclude individual image section activities
                        "image_type": {
                            "$nin": [
                                # Individual image section activities
                                "white_background",
                                "background_change",
                                "model_with_ornament",
                                "real_model_with_ornament",
                                "campaign_shot_advanced",
                                # Individual image section regenerations
                                "white_background_regenerated",
                                "background_change_regenerated",
                                "model_with_ornament_regenerated",
                                "real_model_with_ornament_regenerated",
                                "campaign_shot_advanced_regenerated"
                            ]
                        }
                    }
                ]
            }
        ).order_by('-created_at')

        # Format the results
        history_list = []
        for item in project_history:
            history_list.append({
                'id': str(item.id),
                'type': 'project_image',
                'image_type': item.image_type,
                'image_url': item.image_url,
                'prompt': item.prompt,
                'original_prompt': item.original_prompt,
                'parent_image_id': item.parent_image_id,
                'created_at': item.created_at.isoformat(),
                'project': {
                    'id': str(item.project.id) if item.project else None,
                    'name': item.project.name if item.project else 'Unknown Project'
                },
                'collection': {
                    'id': str(item.collection.id) if item.collection else None
                },
                'metadata': item.metadata or {}
            })

        # Apply pagination
        total_count = len(history_list)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_history = history_list[start_idx:end_idx]

        return Response({
            'success': True,
            'history': paginated_history,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total_count,
                'pages': (total_count + limit - 1) // limit
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_collection_history(request, collection_id):
    """Get image generation history for a specific collection, grouped by product images"""
    try:
        user = request.user
        user_id = str(user.id)

        # Get the collection
        try:
            collection = Collection.objects.get(id=collection_id)
        except Collection.DoesNotExist:
            return Response({'error': 'Collection not found'}, status=404)

        # Get the project associated with this collection
        project = collection.project if hasattr(
            collection, 'project') else None
        project_id = str(project.id) if project else None

        # Get all history for this collection AND project (double-check to ensure project match)
        collection_history = ImageGenerationHistory.objects(
            collection=collection,
            user_id=user_id
        ).order_by('-created_at')

        # Additional filter: ensure history belongs to the same project
        if project:
            filtered_history = []
            for item in collection_history:
                # Check if the history item's project matches the collection's project
                item_project_id = str(
                    item.project.id) if item.project else None
                item_collection_id = str(
                    item.collection.id) if item.collection else None

                # Include if project matches OR if no project but collection matches
                if item_project_id == project_id:
                    filtered_history.append(item)
                elif not item_project_id and item_collection_id == str(collection.id):
                    # If no project but has collection, include if collection matches
                    filtered_history.append(item)
            collection_history = filtered_history

        # Get product images from collection to match with history
        product_images_map = {}
        if collection.items:
            for item in collection.items:
                for product_img in item.product_images:
                    product_key = product_img.uploaded_image_path or product_img.uploaded_image_url
                    if product_key:
                        product_images_map[product_key] = {
                            'uploaded_image_url': product_img.uploaded_image_url,
                            'uploaded_image_path': product_img.uploaded_image_path
                        }

        # Group history by product image (using metadata.product_url or uploaded_image_path)
        history_by_product = {}

        for item in collection_history:
            # Try to get product image info from metadata
            product_url = None
            product_path = None

            if item.metadata:
                product_url = item.metadata.get('product_url')
                product_path = item.metadata.get('product_image_path')

            # Use product_path if available, otherwise product_url, otherwise local_path
            product_key = product_path or product_url or item.local_path

            if not product_key:
                # If no product key found, skip this item or use a default
                continue

            # Find matching product image
            product_image_info = None
            for key, info in product_images_map.items():
                if key == product_key or info.get('uploaded_image_url') == product_url or info.get('uploaded_image_path') == product_path:
                    product_image_info = info
                    product_key = key
                    break

            # If not found in map, try to create from metadata
            if not product_image_info and product_url:
                product_image_info = {
                    'uploaded_image_url': product_url,
                    'uploaded_image_path': product_path
                }
                product_images_map[product_key] = product_image_info

            # Initialize product group if not exists
            if product_key not in history_by_product:
                history_by_product[product_key] = {
                    'product_image': product_image_info or {
                        'uploaded_image_url': product_url or '',
                        'uploaded_image_path': product_path or ''
                    },
                    'history': []
                }

            # Add history item
            history_by_product[product_key]['history'].append({
                'id': str(item.id),
                'image_type': item.image_type,
                'image_url': item.image_url,
                'prompt': item.prompt,
                'original_prompt': item.original_prompt,
                'parent_image_id': item.parent_image_id,
                'created_at': item.created_at.isoformat(),
                'metadata': item.metadata or {}
            })

        # Convert to list format and sort by most recent history item
        result = []
        for product_key, data in history_by_product.items():
            # Sort history by created_at (most recent first)
            data['history'].sort(key=lambda x: x['created_at'], reverse=True)
            result.append({
                'product_key': product_key,
                'product_image': data['product_image'],
                'history': data['history'],
                'total_images': len(data['history']),
                'latest_generation': data['history'][0]['created_at'] if data['history'] else None
            })

        # Sort by latest generation date (most recent first)
        result.sort(key=lambda x: x['latest_generation'] or '', reverse=True)

        return Response({
            'success': True,
            'collection_id': str(collection.id),
            'project_id': project_id,
            'project_name': project.name if project else None,
            'history_by_product': result,
            'total_products': len(result),
            'total_images': sum(len(item['history']) for item in result)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


# views.py


@csrf_exempt
@api_view(['POST'])
@csrf_exempt
@authenticate
def api_image_enhance(request):
    """Auto-enhance a Cloudinary image and store it in projects section with proper tracking."""
    try:
        data = json.loads(request.body)
        image_url = data.get("image_url")
        collection_id = data.get("collection_id")
        product_image_path = data.get("product_image_path")
        generated_image_path = data.get("generated_image_path")

        if not image_url:
            return Response({"error": "image_url is required"}, status=400)

        if not collection_id:
            return Response({"error": "collection_id is required"}, status=400)

        if not product_image_path:
            return Response({"error": "product_image_path is required"}, status=400)

        if not generated_image_path:
            return Response({"error": "generated_image_path is required"}, status=400)

        user = request.user
        user_id = str(user.id)

        # ✅ Extract public_id correctly using regex
        match = re.search(
            r"/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z]{3,4})?$", image_url)

        if not match:
            return Response({"error": "Invalid Cloudinary URL"}, status=400)
        public_id = match.group(1)

        # Generate enhanced URL using Cloudinary transformations
        enhanced_url, _ = cloudinary_url(
            public_id,
            type="upload",              # ✅ required for nested folders
            secure=True,
            sign_url=False,             # ✅ avoids signature mismatch
            transformation=[
                {"width": "4096", "crop": "scale"},
                {"effect": "improve"},
                {"effect": "enhance:70"},
                {"effect": "auto_contrast"},
                {"effect": "sharpen:150"},
                {"quality": "auto:best"},
                {"fetch_format": "auto"},
            ]
        )

        # Get the collection and find the specific product image
        try:
            collection = Collection.objects.get(id=collection_id)
            if not collection.items:
                return Response({"error": "No collection items found"}, status=404)

            item = collection.items[0]
            product_image = None

            # Find the specific product image
            for product in item.product_images:
                if product.uploaded_image_path == product_image_path:
                    product_image = product
                    break

            if not product_image:
                return Response({"error": "Product image not found"}, status=404)

            # Find the specific generated image
            generated_image = None
            for img in product_image.generated_images:
                if img.get("local_path") == generated_image_path:
                    generated_image = img
                    break

            if not generated_image:
                return Response({"error": "Generated image not found"}, status=404)

            # Create enhanced image entry
            enhanced_image_entry = {
                "type": f"{generated_image.get('type', 'generated')}_enhanced",
                "prompt": f"{generated_image.get('prompt', '')} (Enhanced with AI)",
                "local_path": generated_image_path.replace('.png', '_enhanced.png'),
                "cloud_url": enhanced_url,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "model_used": generated_image.get("model_used", {}),
                "enhanced_from": {
                    "original_url": image_url,
                    "original_path": generated_image_path,
                    "enhancement_type": "cloudinary_auto_enhance"
                }
            }

            # Add enhanced image to the generated image's enhanced_images list
            if "enhanced_images" not in generated_image:
                generated_image["enhanced_images"] = []

            generated_image["enhanced_images"].append(enhanced_image_entry)

            # Save the collection
            collection.save()

            # Track enhancement in history
            from .history_utils import track_project_image_generation
            track_project_image_generation(
                user_id=user_id,
                collection_id=collection_id,
                image_type=f"{generated_image.get('type', 'generated')}_enhanced",
                image_url=enhanced_url,
                prompt=f"{generated_image.get('prompt', '')} (Enhanced with AI)",
                local_path=enhanced_image_entry["local_path"],
                metadata={
                    "enhanced_from": image_url,
                    "enhancement_type": "cloudinary_auto_enhance",
                    "product_image_path": product_image_path,
                    "generated_image_path": generated_image_path
                }
            )

            return Response({
                "success": True,
                "enhanced_url": enhanced_url,
                "enhanced_image": enhanced_image_entry,
                "message": "Image enhanced successfully and stored in project"
            })

        except Collection.DoesNotExist:
            return Response({"error": "Collection not found"}, status=404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


@api_view(['DELETE'])
@csrf_exempt
@authenticate
def api_remove_model(request, collection_id):
    """
    Remove a specific model (AI or Real) from the collection.
    Body:
    {
        "type": "ai" | "real",
        "model": {"cloud": "...", "local": "..."}
    }
    """
    try:
        data = json.loads(request.body)
        model_type = data.get("type")
        model = data.get("model")

        if not model_type or not model:
            return Response({"error": "Model type and model details are required"}, status=400)

        collection = Collection.objects(id=collection_id).first()
        if not collection:
            return Response({"error": "Collection not found"}, status=404)

        if not collection.items:
            return Response({"error": "No items found in this collection"}, status=404)

        # For simplicity, assuming only one item per collection
        item = collection.items[0]

        # Choose correct list based on type
        if model_type == "ai":
            models_list = item.generated_model_images
        elif model_type == "real":
            models_list = item.uploaded_model_images
        else:
            return Response({"error": "Invalid model type"}, status=400)

        # Filter out the model to delete
        model_cloud = model.get("cloud")
        model_local = model.get("local")
        new_list = [m for m in models_list if m.get(
            "cloud") != model_cloud and m.get("local") != model_local]

        # Update the list
        if model_type == "ai":
            item.generated_model_images = new_list
        else:
            item.uploaded_model_images = new_list

        # If deleted model was selected, clear it
        selected = item.selected_model or {}
        if selected.get("cloud") == model_cloud or selected.get("local") == model_local:
            item.selected_model = {}

        collection.save()
        return Response({"success": True, "message": "Model removed successfully"})

    except Exception as e:
        print("Error removing model:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['DELETE'])
@csrf_exempt
@authenticate
def api_remove_product_image(request, collection_id):
    """
    Remove a specific product image from the collection.
    Body:
    {
        "product_image_url": "..." or "product_image_path": "..."
    }
    """
    try:
        data = json.loads(request.body)
        product_image_url = data.get("product_image_url")
        product_image_path = data.get("product_image_path")

        if not product_image_url and not product_image_path:
            return Response({"error": "Product image URL or path is required"}, status=400)

        collection = Collection.objects(id=collection_id).first()
        if not collection:
            return Response({"error": "Collection not found"}, status=404)

        if not collection.items:
            return Response({"error": "No items found in this collection"}, status=404)

        # For simplicity, assuming only one item per collection
        item = collection.items[0]

        if not hasattr(item, "product_images") or not item.product_images:
            return Response({"error": "No product images found in this collection"}, status=404)

        # Filter out the product image to delete
        new_product_images = []
        for product_img in item.product_images:
            # Match by URL or path
            if product_image_url and product_img.uploaded_image_url == product_image_url:
                continue  # Skip this product image
            if product_image_path and product_img.uploaded_image_path == product_image_path:
                continue  # Skip this product image
            new_product_images.append(product_img)

        # Update the list
        item.product_images = new_product_images
        collection.save()

        return Response({"success": True, "message": "Product image removed successfully"})

    except Exception as e:
        print("Error removing product image:", str(e))
        return Response({"error": str(e)}, status=500)


# -----------------------------
# Prompt Master API Views
# -----------------------------

@api_view(['GET'])
@csrf_exempt
@authenticate
def api_prompt_master_list(request):
    """Get all prompts - returns prompts from all categories"""
    try:
        user = request.user
        # Get optional query parameters
        category_filter = request.GET.get('category', None)
        is_active_filter = request.GET.get('is_active', None)

        # Build query
        query = {}
        if category_filter:
            query['category'] = category_filter
        if is_active_filter is not None:
            query['is_active'] = is_active_filter.lower() == 'true'

        if query:
            prompts = PromptMaster.objects(
                **query).order_by('category', 'prompt_key')
        else:
            prompts = PromptMaster.objects.all().order_by('category', 'prompt_key')

        prompts_data = []
        for prompt in prompts:
            prompts_data.append({
                "id": str(prompt.id),
                "prompt_key": prompt.prompt_key,
                "title": prompt.title,
                "description": prompt.description,
                "prompt_content": prompt.prompt_content,
                "instructions": prompt.instructions or "",
                "rules": prompt.rules or "",
                "category": prompt.category,
                "prompt_type": prompt.prompt_type,
                "is_active": prompt.is_active,
                "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
                "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
                "created_by": str(prompt.created_by.id) if prompt.created_by else None,
                "updated_by": str(prompt.updated_by.id) if prompt.updated_by else None,
                "metadata": prompt.metadata or {}
            })

        # Also return unique categories for frontend convenience
        all_categories = list(
            set([p.category for p in PromptMaster.objects.all() if p.category]))
        all_categories.sort()

        return Response({
            "success": True,
            "prompts": prompts_data,
            "categories": all_categories  # Include all available categories
        })

    except Exception as e:
        print("Error fetching prompts:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_prompt_master_detail(request, prompt_id):
    """Get a specific prompt by ID"""
    try:
        user = request.user
        prompt = PromptMaster.objects.get(id=prompt_id)

        prompt_data = {
            "id": str(prompt.id),
            "prompt_key": prompt.prompt_key,
            "title": prompt.title,
            "description": prompt.description,
            "prompt_content": prompt.prompt_content,
            "instructions": prompt.instructions or "",
            "rules": prompt.rules or "",
            "category": prompt.category,
            "prompt_type": prompt.prompt_type,
            "is_active": prompt.is_active,
            "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
            "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
            "created_by": str(prompt.created_by.id) if prompt.created_by else None,
            "updated_by": str(prompt.updated_by.id) if prompt.updated_by else None,
            "metadata": prompt.metadata or {}
        }

        return Response({"success": True, "prompt": prompt_data})

    except PromptMaster.DoesNotExist:
        return Response({"error": "Prompt not found"}, status=404)
    except Exception as e:
        print("Error fetching prompt:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_prompt_master_create(request):
    """Create a new prompt"""
    try:
        user = request.user
        data = json.loads(request.body)

        # Check if prompt_key already exists
        if PromptMaster.objects(prompt_key=data.get('prompt_key')).first():
            return Response({"error": "Prompt key already exists"}, status=400)

        prompt = PromptMaster(
            prompt_key=data.get('prompt_key'),
            title=data.get('title'),
            description=data.get('description', ''),
            prompt_content=data.get('prompt_content'),
            instructions=data.get('instructions', ''),
            rules=data.get('rules', ''),
            category=data.get('category'),
            prompt_type=data.get('prompt_type'),
            is_active=data.get('is_active', True),
            created_by=user,
            updated_by=user,
            metadata=data.get('metadata', {})
        )
        prompt.save()

        prompt_data = {
            "id": str(prompt.id),
            "prompt_key": prompt.prompt_key,
            "title": prompt.title,
            "description": prompt.description,
            "prompt_content": prompt.prompt_content,
            "instructions": prompt.instructions or "",
            "rules": prompt.rules or "",
            "category": prompt.category,
            "prompt_type": prompt.prompt_type,
            "is_active": prompt.is_active,
            "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
            "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
            "created_by": str(prompt.created_by.id) if prompt.created_by else None,
            "updated_by": str(prompt.updated_by.id) if prompt.updated_by else None,
            "metadata": prompt.metadata or {}
        }

        return Response({"success": True, "prompt": prompt_data}, status=201)

    except Exception as e:
        print("Error creating prompt:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['PUT'])
@csrf_exempt
@authenticate
def api_prompt_master_update(request, prompt_id):
    """Update an existing prompt"""
    try:
        user = request.user
        data = json.loads(request.body)

        prompt = PromptMaster.objects.get(id=prompt_id)

        # Update fields
        if 'title' in data:
            prompt.title = data['title']
        if 'description' in data:
            prompt.description = data.get('description', '')
        if 'prompt_content' in data:
            prompt.prompt_content = data['prompt_content']
        if 'instructions' in data:
            prompt.instructions = data.get('instructions', '')
        if 'rules' in data:
            prompt.rules = data.get('rules', '')
        if 'category' in data:
            prompt.category = data['category']
        if 'prompt_type' in data:
            prompt.prompt_type = data.get('prompt_type')
        if 'is_active' in data:
            prompt.is_active = data['is_active']
        if 'metadata' in data:
            prompt.metadata = data.get('metadata', {})

        prompt.updated_by = user
        prompt.updated_at = datetime.now(timezone.utc)
        prompt.save()

        prompt_data = {
            "id": str(prompt.id),
            "prompt_key": prompt.prompt_key,
            "title": prompt.title,
            "description": prompt.description,
            "prompt_content": prompt.prompt_content,
            "instructions": prompt.instructions or "",
            "rules": prompt.rules or "",
            "category": prompt.category,
            "prompt_type": prompt.prompt_type,
            "is_active": prompt.is_active,
            "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
            "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
            "created_by": str(prompt.created_by.id) if prompt.created_by else None,
            "updated_by": str(prompt.updated_by.id) if prompt.updated_by else None,
            "metadata": prompt.metadata or {}
        }

        return Response({"success": True, "prompt": prompt_data})

    except PromptMaster.DoesNotExist:
        return Response({"error": "Prompt not found"}, status=404)
    except Exception as e:
        print("Error updating prompt:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['DELETE'])
@csrf_exempt
@authenticate
def api_prompt_master_delete(request, prompt_id):
    """Delete a prompt"""
    try:
        user = request.user
        prompt = PromptMaster.objects.get(id=prompt_id)
        prompt.delete()

        return Response({"success": True, "message": "Prompt deleted successfully"})

    except PromptMaster.DoesNotExist:
        return Response({"error": "Prompt not found"}, status=404)
    except Exception as e:
        print("Error deleting prompt:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def api_prompt_master_get_by_key(request, prompt_key):
    """Get a prompt by its key"""
    try:
        user = request.user
        prompt = PromptMaster.objects.get(
            prompt_key=prompt_key, is_active=True)

        prompt_data = {
            "id": str(prompt.id),
            "prompt_key": prompt.prompt_key,
            "title": prompt.title,
            "description": prompt.description,
            "prompt_content": prompt.prompt_content,
            "category": prompt.category,
            "prompt_type": prompt.prompt_type,
            "is_active": prompt.is_active,
            "metadata": prompt.metadata or {}
        }

        return Response({"success": True, "prompt": prompt_data})

    except PromptMaster.DoesNotExist:
        return Response({"error": "Prompt not found"}, status=404)
    except Exception as e:
        print("Error fetching prompt by key:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def api_prompt_master_initialize(request):
    """Initialize default prompts in the database"""
    try:
        from .prompt_initializer import initialize_default_prompts
        created_count, updated_count = initialize_default_prompts()

        return Response({
            "success": True,
            "message": "Prompts initialized successfully",
            "created": created_count,
            "already_existed": updated_count
        })

    except Exception as e:
        print("Error initializing prompts:", str(e))
        return Response({"error": str(e)}, status=500)
