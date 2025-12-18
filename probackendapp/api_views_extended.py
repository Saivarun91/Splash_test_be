"""
Extended API views for advanced features:
- Model usage statistics
- Role-based access control endpoints
"""

from django.http import JsonResponse
from rest_framework.decorators import api_view
from mongoengine.errors import DoesNotExist
from .models import Collection
from .permissions import require_collection_role, get_user_role_in_project
from common.middleware import authenticate


@api_view(['GET'])
@authenticate
def api_get_model_usage_stats(request, collection_id):
    """
    Get model usage statistics for a collection.
    Returns count of models used and their types.
    """
    try:
        collection = Collection.objects.get(id=collection_id)

        if not collection.items:
            return JsonResponse({
                "success": True,
                "total_models_used": 0,
                "models_breakdown": [],
                "total_generations": 0
            })

        item = collection.items[0]
        products = item.product_images or []

        # Track model usage
        model_usage = {}  # key: model identifier, value: count
        total_generations = 0

        for product in products:
            for gen_img in product.generated_images:
                # Count initial generation
                model_info = gen_img.get("model_used", {})
                if model_info:
                    model_key = f"{model_info.get('type', 'unknown')}:{model_info.get('name', 'unnamed')}"
                    model_usage[model_key] = model_usage.get(model_key, 0) + 1
                    total_generations += 1

                # Count regenerations
                for regen in gen_img.get("regenerated_images", []):
                    regen_model = regen.get("model_used", {})
                    if regen_model:
                        regen_key = f"{regen_model.get('type', 'unknown')}:{regen_model.get('name', 'unnamed')}"
                        model_usage[regen_key] = model_usage.get(
                            regen_key, 0) + 1
                        total_generations += 1

        # Format breakdown
        models_breakdown = []
        for model_key, count in model_usage.items():
            model_type, model_name = model_key.split(":", 1)
            models_breakdown.append({
                "type": model_type,
                "name": model_name,
                "usage_count": count
            })

        return JsonResponse({
            "success": True,
            "total_models_used": len(model_usage),
            "models_breakdown": models_breakdown,
            "total_generations": total_generations
        })

    except DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Collection not found"
        }, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@api_view(['GET'])
@authenticate
def api_get_user_role(request, project_id):
    """
    Get the current user's role in a project.
    """
    try:
        from .models import Project

        project = Project.objects.get(id=project_id)
        user_role = get_user_role_in_project(request.user, project)

        if not user_role:
            return JsonResponse({
                "success": False,
                "error": "You are not a member of this project"
            }, status=403)

        return JsonResponse({
            "success": True,
            "role": user_role,
            "permissions": {
                "can_generate_images": user_role == "owner",
                "can_upload_models": user_role in ["owner", "editor"],
                "can_select_themes": user_role in ["owner", "editor"],
                "can_view_project": True,
                "can_manage_members": user_role == "owner"
            }
        })

    except DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Project not found"
        }, status=404)
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)
