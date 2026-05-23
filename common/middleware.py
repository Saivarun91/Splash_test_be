import jwt
from django.conf import settings
from django.http import JsonResponse
from functools import wraps
from users.models import User


from django.http import HttpResponse, JsonResponse

def authenticate(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):

        # Detect request object (FBV / CBV support)
        if hasattr(args[0], 'request'):  # Class-based view
            request = args[1]
        elif hasattr(args[0], 'META'):   # Function-based view
            request = args[0]
        else:
            raise Exception("Cannot find request object")

        # ---- CRITICAL: Stop OPTIONS immediately ----
        if request.method == "OPTIONS":
            return HttpResponse("", status=200, content_type="text/plain")

        # ---- JWT Authentication for other methods ----
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'message': 'Authorization denied'}, status=401)

        try:
            token = auth_header.split(' ')[1]
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

            user = User.objects(id=payload.get('id')).first()
            if not user:
                return JsonResponse({'message': 'User not found'}, status=404)

            request.user = user

        except jwt.ExpiredSignatureError:
            return JsonResponse({'message': 'Token expired'}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({'message': 'Invalid token'}, status=401)

        return view_func(*args, **kwargs)

    return wrapper



def restrict(roles=[]):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = getattr(request, 'user', None)

            if not user:
                return JsonResponse({'message': "User not authenticated"}, status=401)

            role = user.get('role')

            if role not in roles:
                return JsonResponse({'message': "You're not authorized"}, status=403)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

# common/middleware.py
import traceback
from .tasks import notify_admin_error


def _get_user_details(request):
    """Build a JSON-serializable dict of user details (for MongoEngine User or anonymous)."""
    user = getattr(request, "user", None)
    if user is None:
        return {"authenticated": False, "label": "anonymous"}
    try:
        return {
            "authenticated": True,
            "id": str(user.id) if hasattr(user, "id") and user.id else None,
            "email": getattr(user, "email", None),
            "full_name": getattr(user, "full_name", None),
            "username": getattr(user, "username", None),
            "role": str(getattr(user, "role", None)) if getattr(user, "role", None) else None,
        }
    except Exception:
        return {"authenticated": True, "label": "unknown", "raw_id": str(getattr(user, "id", None))}


def _get_location_details(request):
    """Build where the error occurred: path, method, view name if available. Safe for non-Django request objects."""
    path = getattr(request, "path", "")
    get_full_path = getattr(request, "get_full_path", None)
    if callable(get_full_path):
        try:
            full_path = get_full_path()
        except Exception:
            full_path = path
    else:
        full_path = path
    location = {
        "path": path,
        "full_path": full_path,
        "method": getattr(request, "method", ""),
    }
    try:
        resolver = getattr(request, "resolver_match", None)
        if resolver:
            location["view_name"] = getattr(resolver, "view_name", None) or getattr(resolver, "url_name", None)
            location["view_func"] = getattr(getattr(resolver, "func", None), "__name__", None)
    except Exception:
        pass
    return location


class ErrorNotificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as exc:
            payload = {
                "user": _get_user_details(request),
                "location": _get_location_details(request),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            try:
                notify_admin_error.delay(payload)
            except Exception:
                pass  # do not mask original exception
            raise
