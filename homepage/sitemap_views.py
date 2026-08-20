"""
Paginated sitemap JSON APIs for the Next.js sitemap system.

Contract:
  GET /api/sitemap/blog?page=1&limit=1000
  → {
      urls: [{ loc, lastmod }],
      current_page,
      last_page,
      total
    }
"""
from __future__ import annotations

import math
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view

from .landing_models import PAGE_TYPE_PATHS, LandingPage
from .models import Blog

DEFAULT_LIMIT = 1000
MAX_LIMIT = 1000


def _parse_positive_int(value, default):
    try:
        n = int(value)
        if n < 1:
            return default
        return n
    except (TypeError, ValueError):
        return default


def _site_origin():
    origin = (
        getattr(settings, "FRONTEND_URL", None)
        or getattr(settings, "SITE_URL", None)
        or "http://localhost:3000"
    )
    return str(origin).rstrip("/")


def _iso(dt):
    if not dt:
        return datetime.utcnow().isoformat() + "Z"
    if isinstance(dt, datetime):
        # Always emit UTC-ish ISO; append Z if naive
        text = dt.isoformat()
        if dt.tzinfo is None and not text.endswith("Z"):
            return text + "Z"
        return text
    return str(dt)


@api_view(["GET"])
@csrf_exempt
def sitemap_blog(request):
    """Published blog posts as sitemap url entries (1000 per page)."""
    try:
        page = _parse_positive_int(request.GET.get("page"), 1)
        limit = min(
            MAX_LIMIT,
            _parse_positive_int(request.GET.get("limit"), DEFAULT_LIMIT),
        )

        qs = Blog.objects(status="Published")
        total = qs.count()
        last_page = max(1, math.ceil(total / limit) if total else 1)
        if page > last_page:
            page = last_page

        skip = (page - 1) * limit
        blogs = list(qs.order_by("-updated_at").skip(skip).limit(limit))
        origin = _site_origin()

        urls = []
        for blog in blogs:
            slug = (blog.slug or "").strip()
            if not slug:
                continue
            lastmod_source = blog.updated_at or blog.created_at
            urls.append(
                {
                    "loc": f"{origin}/blog/{slug}",
                    "lastmod": _iso(lastmod_source),
                }
            )

        return JsonResponse(
            {
                "urls": urls,
                "current_page": page,
                "last_page": last_page,
                "total": total,
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "urls": [],
                "current_page": 1,
                "last_page": 1,
                "total": 0,
                "error": str(e),
            },
            status=500,
        )


@api_view(["GET"])
@csrf_exempt
def sitemap_landing_pages(request):
    """Published landing pages as sitemap url entries (1000 per page)."""
    try:
        page = _parse_positive_int(request.GET.get("page"), 1)
        limit = min(
            MAX_LIMIT,
            _parse_positive_int(request.GET.get("limit"), DEFAULT_LIMIT),
        )

        qs = LandingPage.objects(status="Published")
        total = qs.count()
        last_page = max(1, math.ceil(total / limit) if total else 1)
        if page > last_page:
            page = last_page

        skip = (page - 1) * limit
        pages = list(qs.order_by("-updated_at").skip(skip).limit(limit))
        origin = _site_origin()

        urls = []
        listed_types = set()
        for item in pages:
            slug = (item.slug or "").strip()
            prefix = PAGE_TYPE_PATHS.get(item.type)
            if not slug or not prefix:
                continue
            lastmod_source = item.updated_at or item.published_at or item.created_at
            urls.append(
                {
                    "loc": f"{origin}/{prefix}/{slug}",
                    "lastmod": _iso(lastmod_source),
                }
            )
            listed_types.add(prefix)

        if page == 1:
            for prefix in listed_types:
                urls.insert(
                    0,
                    {
                        "loc": f"{origin}/{prefix}",
                        "lastmod": _iso(datetime.utcnow()),
                    },
                )

        return JsonResponse(
            {
                "urls": urls,
                "current_page": page,
                "last_page": last_page,
                "total": total,
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "urls": [],
                "current_page": 1,
                "last_page": 1,
                "total": 0,
                "error": str(e),
            },
            status=500,
        )
