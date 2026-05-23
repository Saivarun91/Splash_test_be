import json

from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt

from common.middleware import authenticate
from users.models import Role
from .models import InvoiceConfig


def _is_admin(user) -> bool:
    """Return True if the current user is an admin."""
    return getattr(user, "role", None) == Role.ADMIN


def _get_active_config() -> InvoiceConfig:
    """
    Fetch the active InvoiceConfig document.
    If none exists, create one with defaults.
    """
    config = InvoiceConfig.objects.first()
    if not config:
        config = InvoiceConfig()
        config.save()
    return config


@api_view(["GET", "PUT"])
@csrf_exempt
@authenticate
def invoice_config(request):
    """
    GET  -> return current invoice configuration.
    PUT  -> update global invoice configuration (admin only).
    """
    if request.method == "GET":
        config = _get_active_config()
        data = {
            "company_name": config.company_name,
            "invoice_prefix": config.invoice_prefix,
            "tax_rate": config.tax_rate,
            "bank_name": config.bank_name,
            "account_name": config.account_name,
            "account_number": config.account_number,
            "pay_by_date": config.pay_by_date,
            "terms_and_conditions": config.terms_and_conditions,
        }
        return JsonResponse(data, status=200)

    # PUT
    if not _is_admin(request.user):
        return JsonResponse(
            {"error": "Only admin can update invoice configuration"}, status=403
        )

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    config = _get_active_config()

    # Update allowed fields only
    for field in [
        "company_name",
        "invoice_prefix",
        "tax_rate",
        "bank_name",
        "account_name",
        "account_number",
        "pay_by_date",
        "terms_and_conditions",
    ]:
        if field in payload:
            setattr(config, field, payload[field])

    config.save()

    return JsonResponse({"success": True}, status=200)


