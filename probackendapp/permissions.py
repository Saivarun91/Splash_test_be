"""
Role-based permission decorators for project access control.

Roles:
- owner: Full access (generate images, upload models, manage themes)
- editor: Can upload models and select themes (no generate)  
- viewer: Read-only access (can only view data)
"""

from functools import wraps
from django.http import JsonResponse
from mongoengine.errors import DoesNotExist
from .models import Project


def get_user_role_in_project(user, project):
    """
    Get user's role in a project.
    Returns: role string ('owner', 'editor', 'viewer') or None if not a member
    """
    if not project or not user:
        return None

    for member in project.team_members:
        if str(member.user.id) == str(user.id):
            return member.role

    return None


def require_project_role(allowed_roles):
    """
    Decorator to require specific roles for a view.

    Usage:
        @require_project_role(['owner', 'editor'])
        def my_view(request, project_id):
            ...

    Args:
        allowed_roles: List of role strings that are allowed to access this view
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, project_id=None, *args, **kwargs):
            # If no project_id, try to get it from URL or request body
            if not project_id:
                import json
                if request.method in ['POST', 'PUT', 'PATCH']:
                    try:
                        data = json.loads(request.body)
                        project_id = data.get('project_id')
                    except:
                        pass

            # Check if user is authenticated
            if not hasattr(request, 'user') or not request.user:
                return JsonResponse({
                    'error': 'Authentication required'
                }, status=401)

            # Get project
            try:
                project = Project.objects.get(id=project_id)
            except DoesNotExist:
                return JsonResponse({
                    'error': 'Project not found'
                }, status=404)

            # Get user role
            user_role = get_user_role_in_project(request.user, project)

            if not user_role:
                return JsonResponse({
                    'error': 'You are not a member of this project'
                }, status=403)

            if user_role not in allowed_roles:
                return JsonResponse({
                    'error': f'Access denied. Required roles: {", ".join(allowed_roles)}. Your role: {user_role}'
                }, status=403)

            # Add role to request for use in view
            request.user_role = user_role
            request.project = project

            return view_func(request, project_id, *args, **kwargs)

        return wrapped_view
    return decorator


def require_collection_role(allowed_roles):
    """
    Decorator to require specific roles for collection-based views.
    Extracts project from collection.

    Usage:
        @require_collection_role(['owner', 'editor'])
        def my_view(request, collection_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, collection_id, *args, **kwargs):
            from .models import Collection

            # Check if user is authenticated
            if not hasattr(request, 'user') or not request.user:
                return JsonResponse({
                    'error': 'Authentication required'
                }, status=401)

            # Get collection
            try:
                collection = Collection.objects.get(id=collection_id)
            except DoesNotExist:
                return JsonResponse({
                    'error': 'Collection not found'
                }, status=404)

            project = collection.project

            # Get user role
            user_role = get_user_role_in_project(request.user, project)

            if not user_role:
                return JsonResponse({
                    'error': 'You are not a member of this project'
                }, status=403)

            if user_role not in allowed_roles:
                return JsonResponse({
                    'error': f'Access denied. Required roles: {", ".join(allowed_roles)}. Your role: {user_role}'
                }, status=403)

            # Add role to request for use in view
            request.user_role = user_role
            request.project = project

            return view_func(request, collection_id, *args, **kwargs)

        return wrapped_view
    return decorator


# Role check helpers
def can_generate_images(user_role):
    """Only owners can generate images"""
    return user_role == 'owner'


def can_upload_models(user_role):
    """Editors and owners can upload models"""
    return user_role in ['owner', 'editor']


def can_select_themes(user_role):
    """Editors and owners can select themes"""
    return user_role in ['owner', 'editor']


def can_view_project(user_role):
    """All members can view"""
    return user_role in ['owner', 'editor', 'viewer']


def can_manage_members(user_role):
    """Only owners can manage members"""
    return user_role == 'owner'
