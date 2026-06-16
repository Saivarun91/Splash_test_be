"""
Admin API views for individual users (users without an organization)
"""
import json
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from mongoengine import Q
from mongoengine.errors import DoesNotExist
from rest_framework.decorators import api_view

from common.middleware import authenticate
from CREDITS.models import CreditLedger
from CREDITS.utils import add_user_credits, remove_user_credits
from imgbackendapp.mongo_models import OrnamentMongo
from probackendapp.models import Project, ImageGenerationHistory
from users.models import User, Role


def is_admin(user):
    return user.role == Role.ADMIN


def _individual_user_query():
    return Q(organization=None) | Q(organization__exists=False)


def _get_individual_user(user_id):
    user = User.objects(id=user_id).first()
    if not user:
        return None
    if user.organization:
        return None
    return user


def _serialize_project(project):
    try:
        project_images_count = ImageGenerationHistory.objects(project=project).count()
        return {
            'id': str(project.id),
            'slug': project.slug if hasattr(project, 'slug') and project.slug else None,
            'name': project.name,
            'about': project.about,
            'status': project.status,
            'created_at': project.created_at.isoformat() if project.created_at else None,
            'updated_at': project.updated_at.isoformat() if project.updated_at else None,
            'totalImages': project_images_count,
            'total_images': project_images_count,
        }
    except (DoesNotExist, AttributeError, TypeError):
        return None


def _get_user_projects(user):
    no_org = Q(organization=None) | Q(organization__exists=False)
    created_projects = Project.objects(Q(created_by=user) & no_org)
    team_projects = Project.objects(Q(team_members__user=user) & no_org)

    all_projects = {}
    for project in created_projects:
        all_projects[str(project.id)] = project
    for project in team_projects:
        all_projects[str(project.id)] = project

    projects_list = []
    for project in all_projects.values():
        serialized = _serialize_project(project)
        if serialized:
            projects_list.append(serialized)
    return projects_list


@api_view(['GET'])
@csrf_exempt
@authenticate
def list_individual_users(request):
    """List all users without an organization - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can list individual users'}, status=403)

    try:
        users = User.objects(_individual_user_query(), role=Role.USER).order_by('-created_at')
        users_list = []
        for user in users:
            projects_count = len(_get_user_projects(user))
            individual_images_count = OrnamentMongo.objects(
                Q(user_id=str(user.id)) | Q(created_by=user)
            ).count()
            users_list.append({
                'id': str(user.id),
                'email': user.email,
                'full_name': user.full_name or '',
                'username': user.username or '',
                'slug': user.slug or '',
                'credit_balance': user.credit_balance or 0,
                'projects_count': projects_count,
                'images_count': individual_images_count,
                'created_at': user.created_at.isoformat() if user.created_at else None,
            })

        return JsonResponse({'success': True, 'users': users_list}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def get_individual_user(request, user_id):
    """Get individual user details - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view individual user details'}, status=403)

    try:
        user = _get_individual_user(user_id)
        if not user:
            return JsonResponse({'error': 'Individual user not found'}, status=404)

        projects = _get_user_projects(user)
        project_images_count = sum(p.get('totalImages', 0) for p in projects)
        individual_images_count = OrnamentMongo.objects(
            Q(user_id=str(user.id)) | Q(created_by=user)
        ).count()

        return JsonResponse({
            'id': str(user.id),
            'email': user.email,
            'full_name': user.full_name or '',
            'username': user.username or '',
            'slug': user.slug or '',
            'credit_balance': user.credit_balance or 0,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'updated_at': user.updated_at.isoformat() if user.updated_at else None,
            'projects': projects,
            'totalProjects': len(projects),
            'activeProjects': len([p for p in projects if p.get('status') in ('active', 'in_progress', 'progress')]),
            'completedProjects': len([p for p in projects if p.get('status') == 'completed']),
            'draftProjects': len([p for p in projects if p.get('status') == 'draft']),
            'totalImages': project_images_count + individual_images_count,
            'project_images_count': project_images_count,
            'individual_images_count': individual_images_count,
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def get_individual_user_images(request, user_id):
    """Get all images generated by an individual user - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view user images'}, status=403)

    try:
        user = _get_individual_user(user_id)
        if not user:
            return JsonResponse({'error': 'Individual user not found'}, status=404)

        image_type = request.GET.get('image_type')
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))

        user_projects = _get_user_projects(user)
        project_ids = [p['id'] for p in user_projects]
        organization_projects = Project.objects(id__in=project_ids) if project_ids else []

        project_query = Q(user_id=str(user.id))
        if organization_projects:
            project_query &= Q(project__in=list(organization_projects))
        if image_type:
            project_query &= Q(image_type=image_type)

        project_images = ImageGenerationHistory.objects(project_query).order_by('-created_at')
        project_total = ImageGenerationHistory.objects(project_query).count()

        individual_query = Q(user_id=str(user.id)) | Q(created_by=user)
        if image_type:
            type_mapping = {
                'white_background': 'white_background',
                'background_change': 'background_change',
                'model_with_ornament': 'model_with_ornament',
                'real_model_with_ornament': 'real_model_with_ornament',
                'campaign_shot_advanced': 'campaign_shot_advanced',
            }
            if image_type in type_mapping:
                individual_query &= Q(type=type_mapping[image_type])

        individual_images = OrnamentMongo.objects(individual_query).order_by('-created_at')
        individual_total = OrnamentMongo.objects(individual_query).count()

        images_list = []
        for img in project_images:
            images_list.append({
                'id': str(img.id),
                'image_url': img.image_url,
                'image_type': img.image_type,
                'prompt': img.prompt,
                'original_prompt': img.original_prompt,
                'user_id': img.user_id,
                'project_id': str(img.project.id) if img.project else None,
                'collection_id': str(img.collection.id) if img.collection else None,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'metadata': img.metadata or {},
                'source': 'project',
            })

        for img in individual_images:
            images_list.append({
                'id': str(img.id),
                'image_url': img.generated_image_url,
                'image_type': img.type,
                'prompt': img.prompt,
                'original_prompt': img.original_prompt,
                'user_id': img.user_id or str(user.id),
                'project_id': None,
                'collection_id': None,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'metadata': {
                    'uploaded_image_url': img.uploaded_image_url,
                    'model_image_url': img.model_image_url,
                    'parent_image_id': str(img.parent_image_id) if img.parent_image_id else None,
                },
                'source': 'individual',
            })

        images_list.sort(key=lambda x: x['created_at'] or '', reverse=True)
        total_count = project_total + individual_total
        paginated_images = images_list[offset:offset + limit]

        return JsonResponse({
            'user_id': str(user.id),
            'user_email': user.email,
            'total_count': total_count,
            'project_images_count': project_total,
            'individual_images_count': individual_total,
            'images': paginated_images,
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def add_individual_user_credits(request, user_id):
    """Add credits to an individual user - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can add credits'}, status=403)

    try:
        data = json.loads(request.body)
        amount = data.get('amount')
        reason = data.get('reason', 'Credit top-up by admin')

        if not amount or amount <= 0:
            return JsonResponse({'error': 'Valid amount is required'}, status=400)

        user = _get_individual_user(user_id)
        if not user:
            return JsonResponse({'error': 'Individual user not found'}, status=404)

        result = add_user_credits(user, request.user, amount, reason=reason)
        if result['success']:
            return JsonResponse({
                'success': True,
                'message': result['message'],
                'balance_after': result['balance_after'],
            }, status=200)
        return JsonResponse({'error': result['message']}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def remove_individual_user_credits(request, user_id):
    """Remove credits from an individual user - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can remove credits'}, status=403)

    try:
        data = json.loads(request.body)
        amount = data.get('amount')
        reason = data.get('reason', 'Credit deduction by admin')

        if not amount or amount <= 0:
            return JsonResponse({'error': 'Valid amount is required'}, status=400)

        user = _get_individual_user(user_id)
        if not user:
            return JsonResponse({'error': 'Individual user not found'}, status=404)

        result = remove_user_credits(user, request.user, amount, reason=reason)
        if result['success']:
            return JsonResponse({
                'success': True,
                'message': result['message'],
                'balance_after': result['balance_after'],
            }, status=200)
        return JsonResponse({'error': result['message']}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
