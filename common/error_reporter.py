import traceback
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from common.tasks import notify_admin_error


def _user_to_payload(user):
    """Convert user (MongoEngine document or dict) to a JSON-serializable dict for email."""
    if user is None:
        return {"authenticated": False, "label": "anonymous"}
    if isinstance(user, dict):
        return user
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
        return {"authenticated": True, "label": "unknown"}


def report_exception(
    *,
    error: Exception,
    source: str,
    context: dict | None = None,
    severity: str = "error",
):
    """
    Use this for handled / background exceptions (e.g. Celery tasks).
    Sends an email to ADMIN_EMAIL with user details and where the error occurred.
    """
    if not getattr(settings, "ADMIN_EMAIL", None):
        return

    user = context.get("user") if context else None
    if user is None and context:
        user = "system"

    payload = {
        "user": _user_to_payload(user) if user not in ("system", None) else {"authenticated": False, "label": user or "system"},
        "location": {
            "path": source,
            "full_path": source,
            "method": "CELERY",
            "view_name": context.get("task_name") if context else None,
        },
        "error": str(error),
        "traceback": traceback.format_exc(),
        "severity": severity,
    }
    if context:
        payload["context"] = {k: v for k, v in context.items() if k != "user" and not callable(v)}

    notify_admin_error.delay(payload)


def _is_django_request(request):
    """True if request looks like a Django HttpRequest (has META). Celery task self.request is not."""
    return request is not None and getattr(request, "META", None) is not None


def _task_context_from_celery_request(celery_request):
    """Build location context from Celery task request (Context), not Django request."""
    if celery_request is None:
        return {"path": "celery_task", "full_path": "celery_task", "method": "CELERY"}
    task_name = getattr(celery_request, "task", None) or getattr(celery_request, "name", None)
    path = (task_name or "celery_task").split(".")[-1] if task_name else "celery_task"
    return {
        "path": path,
        "full_path": task_name or path,
        "method": "CELERY",
        "task_name": task_name,
    }


def report_handled_exception(exc, request=None, context=None):
    """
    Call this inside an except block to send an email to ADMIN_EMAIL for handled exceptions.
    Use when you catch an exception but still want the admin to be notified.

    Usage in a view (Django request):
        except Exception as e:
            report_handled_exception(e, request=request)

    Usage in a Celery task (pass request=self.request for task name; context can include user_id):
        except Exception as e:
            report_handled_exception(e, request=self.request, context={"user_id": user_id})
    """
    if not getattr(settings, "ADMIN_EMAIL", None):
        return

    context = context or {}

    if request is not None and _is_django_request(request):
        from common.middleware import _get_user_details, _get_location_details
        payload = {
            "user": _get_user_details(request),
            "location": _get_location_details(request),
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "handled": True,
        }
    else:
        # Celery task or no request: build from context and optionally Celery request
        celery_request = request  # might be Celery's self.request when used from a task
        if celery_request is not None and not _is_django_request(celery_request):
            location = _task_context_from_celery_request(celery_request)
        else:
            location = {
                "path": context.get("path", context.get("task_name", "unknown")),
                "full_path": context.get("full_path", context.get("task_name", "unknown")),
                "method": context.get("method", "CELERY"),
            }
            if context.get("task_name"):
                location["task_name"] = context["task_name"]

        user = context.get("user")
        if user is None and context.get("user_id"):
            user = {"authenticated": True, "id": str(context["user_id"]), "label": f"user_id={context['user_id']}"}

        payload = {
            "user": _user_to_payload(user) if user is not None else {"authenticated": False, "label": "system"},
            "location": location,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "handled": True,
        }

    extra = {k: v for k, v in context.items() if k not in ("user", "path", "full_path", "method", "task_name", "user_id") and not callable(v)}
    if extra:
        payload["context"] = extra

    try:
        notify_admin_error.delay(payload)
    except Exception:
        pass


def report_all_exceptions(view_func):
    """
    View decorator: catch any exception, report it to ADMIN_EMAIL, and return JSON 500.
    Use on views where you want every exception (handled or not) to trigger an email.

    Order: put this decorator above @authenticate so it wraps the authenticated view.
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        request = None
        if args and hasattr(args[0], "META"):
            request = args[0]
        elif len(args) > 1 and hasattr(args[1], "META"):
            request = args[1]
        try:
            return view_func(*args, **kwargs)
        except Exception as exc:
            report_handled_exception(exc, request=request)
            return JsonResponse(
                {"error": "An error occurred.", "detail": str(exc)},
                status=500,
            )
    return wrapper
