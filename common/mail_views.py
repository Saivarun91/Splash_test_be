"""
Mail template API – admin only.
List, get, and update email templates.
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from common.middleware import authenticate
from users.models import User, Role
from .mail_models import MailTemplate, ensure_default_templates, MAIL_TEMPLATE_SLUGS


def is_admin(user):
    if not user or not hasattr(user, "role"):
        return False
    r = user.role
    if hasattr(r, "value"):
        return r.value == "admin"
    return getattr(r, "value", str(r)) == "admin" or str(r).lower() == "admin"


@api_view(["GET"])
@csrf_exempt
@authenticate
def mail_template_list(request):
    """List all mail templates – admin only."""
    if not is_admin(request.user):
        return JsonResponse({"error": "Only admin can manage mail templates"}, status=403)
    ensure_default_templates()
    templates = list(MailTemplate.objects.all().order_by("slug"))
    return JsonResponse({
        "success": True,
        "templates": [
            {
                "slug": t.slug,
                "name": t.name,
                "description": t.description or "",
                "subject": t.subject,
                "body_plain": t.body_plain,
                "body_html": getattr(t, "body_html", None) or "",
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in templates
        ],
    })


def _template_to_dict(t):
    return {
        "slug": t.slug,
        "name": t.name,
        "description": t.description or "",
        "subject": t.subject,
        "body_plain": t.body_plain,
        "body_html": getattr(t, "body_html", None) or "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@api_view(["GET", "PUT", "PATCH"])
@csrf_exempt
@authenticate
def mail_template_detail(request, slug):
    """Get or update one mail template by slug – admin only."""
    if not is_admin(request.user):
        return JsonResponse({"error": "Only admin can manage mail templates"}, status=403)
    ensure_default_templates()
    t = MailTemplate.objects(slug=slug).first()
    if not t:
        return JsonResponse({"error": "Template not found"}, status=404)

    if request.method == "GET":
        return JsonResponse({"success": True, "template": _template_to_dict(t)})

    import json
    from datetime import datetime
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if "name" in data:
        t.name = data["name"]
    if "description" in data:
        t.description = data.get("description", "")
    if "subject" in data:
        t.subject = data["subject"]
    if "body_plain" in data:
        t.body_plain = data["body_plain"]
    if "body_html" in data:
        t.body_html = data.get("body_html") or ""
    t.updated_at = datetime.utcnow()
    t.save()
    return JsonResponse({"success": True, "template": _template_to_dict(t)})
