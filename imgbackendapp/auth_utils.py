# imgbackendapp/auth_utils.py
import jwt
from django.conf import settings
from django.http import JsonResponse
from functools import wraps


def get_user_from_token(request):
    """
    Extract user ID from Bearer token in Authorization header.
    Returns user_id if valid, None otherwise.
    """
    auth_header = request.headers.get('Authorization', '')

    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header.replace('Bearer ', '')

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload.get('id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_auth(view_func):
    """
    Decorator to require authentication for a view.
    Adds user_id to request object.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_id = get_user_from_token(request)
        if not user_id:
            return JsonResponse({"error": "Authentication required"}, status=401)

        request.user_id = user_id
        return view_func(request, *args, **kwargs)

    return wrapper


def optional_auth(view_func):
    """
    Decorator that extracts user_id if present but doesn't require it.
    Adds user_id to request object (can be None).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_id = get_user_from_token(request)
        request.user_id = user_id
        return view_func(request, *args, **kwargs)

    return wrapper
