"""Global AI image generation kill switch (admin-controlled)."""

from django.http import JsonResponse

from .models import CreditSettings

AI_GENERATION_DISABLED_MESSAGE = (
    "The AI server is down. Please wait for some time or contact the support team."
)


def is_ai_generation_disabled():
    settings = CreditSettings.get_settings()
    return bool(getattr(settings, "ai_generation_disabled", False))


def ai_generation_disabled_json_response():
    return JsonResponse(
        {
            "success": False,
            "error": AI_GENERATION_DISABLED_MESSAGE,
            "ai_generation_disabled": True,
        },
        status=503,
    )


def ai_generation_disabled_drf_response():
    from rest_framework.response import Response

    return Response(
        {
            "success": False,
            "error": AI_GENERATION_DISABLED_MESSAGE,
            "ai_generation_disabled": True,
        },
        status=503,
    )


def block_if_ai_generation_disabled():
    if is_ai_generation_disabled():
        return ai_generation_disabled_json_response()
    return None


def block_if_ai_generation_disabled_drf():
    if is_ai_generation_disabled():
        return ai_generation_disabled_drf_response()
    return None
