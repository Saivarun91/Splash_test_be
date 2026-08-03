"""
Admin blog APIs aligned with /admin/blog/* contract.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

import cloudinary.uploader
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view

from common.middleware import authenticate
from users.models import Role

from .models import Blog, BlogFAQ, IdCounter

PAGE_SIZE = 10


def is_admin(user):
    return user.role == Role.ADMIN


def _fail(message, status=400):
    return JsonResponse({"status": False, "message": message}, status=status)


def _ok(data=None, message=None, status=200):
    payload = {"status": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return JsonResponse(payload, status=status)


def _clear_legacy_blog_posts():
    """Drop leftover documents from the old blog_posts collection once."""
    try:
        from mongoengine.connection import get_db

        db = get_db()
        if "blog_posts" in db.list_collection_names():
            db["blog_posts"].drop()
    except Exception:
        pass


def _serialize_listing_item(blog: Blog):
    return {
        "id": blog.blog_id,
        "title": blog.title or "",
        "picture": blog.picture or "",
        "author": blog.author or "",
        "slug": blog.slug or "",
        "status": blog.status or "",
    }


def _serialize_blog(blog: Blog):
    faqs = []
    for f in blog.faqs or []:
        faqs.append({
            "id": f.id,
            "question": f.question or "",
            "answer": f.answer or "",
        })
    return {
        "id": blog.blog_id,
        "title": blog.title or "",
        "slug": blog.slug or "",
        "author": blog.author or "",
        "short_content": blog.short_content or "",
        "full_content": blog.full_content or "",
        "picture": blog.picture or "",
        "status": blog.status or "Published",
        "is_trending": bool(blog.is_trending),
        "mete_title": blog.mete_title or "",
        "meta_description": blog.meta_description or "",
        "meta_keyword": blog.meta_keyword or "",
        "faqs": faqs,
        "created_at": blog.created_at.isoformat() if blog.created_at else None,
        "updated_at": blog.updated_at.isoformat() if blog.updated_at else None,
    }


def _slugify(value: str) -> str:
    value = (value or "").strip().lower().replace(" ", "-")
    value = re.sub(r"[^a-z0-9-]", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or f"post-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"


def _upload_file(file_obj, folder="homepage/blogs"):
    result = cloudinary.uploader.upload(file_obj, folder=folder, overwrite=True)
    return result.get("secure_url") or ""


def _replace_cid_images(html: str, request) -> str:
    """Replace cid:xxx placeholders with Cloudinary URLs from images[xxx] files."""
    if not html:
        return html or ""
    content = html
    for key in list(request.FILES.keys()):
        match = re.match(r"^images\[(.+)\]$", key)
        if not match:
            continue
        cid = match.group(1)
        file_obj = request.FILES.get(key)
        if not file_obj:
            continue
        url = _upload_file(file_obj, folder="homepage/blogs/inline")
        content = content.replace(f"cid:{cid}", url)
    return content


def _parse_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_faqs_from_request(request):
    faq_map = {}
    for key in request.POST.keys():
        match = re.match(r"^faqs\[(\d+)\]\[(question|answer|id)\]$", key)
        if not match:
            continue
        idx = int(match.group(1))
        field = match.group(2)
        faq_map.setdefault(idx, {})[field] = request.POST.get(key, "")

    faqs = []
    for idx in sorted(faq_map.keys()):
        row = faq_map[idx]
        question = (row.get("question") or "").strip()
        answer = (row.get("answer") or "").strip()
        if not question and not answer:
            continue
        if not question or not answer:
            raise ValueError("Each FAQ row needs both question and answer")
        faq = BlogFAQ(question=question, answer=answer)
        faq_id = _parse_int(row.get("id"))
        if faq_id is not None:
            faq.id = faq_id
        else:
            faq.id = IdCounter.next_id("blog_faq")
        faqs.append(faq)
    return faqs


def _get_post_value(request, key, default=""):
    if key in request.POST:
        return request.POST.get(key, default)
    return default


def _is_html_empty(html: str) -> bool:
    text = re.sub(r"<[^>]+>", "", html or "")
    text = text.replace("&nbsp;", " ").strip()
    return text == ""


# =====================
# Blog listing
# =====================
@api_view(["GET"])
@csrf_exempt
@authenticate
def blog_listing(request):
    if not is_admin(request.user):
        return _fail("Only admin can access this endpoint", 403)
    try:
        _clear_legacy_blog_posts()

        page = max(1, _parse_int(request.GET.get("page"), 1) or 1)
        query = (request.GET.get("query") or "").strip()

        qs = Blog.objects
        if query:
            pattern = re.escape(query)
            qs = qs.filter(
                __raw__={
                    "$or": [
                        {"title": {"$regex": pattern, "$options": "i"}},
                        {"slug": {"$regex": pattern, "$options": "i"}},
                        {"author": {"$regex": pattern, "$options": "i"}},
                        {"short_content": {"$regex": pattern, "$options": "i"}},
                        {"status": {"$regex": pattern, "$options": "i"}},
                    ]
                }
            )

        total = qs.count()
        last_page = max(1, math.ceil(total / PAGE_SIZE) if total else 1)
        if page > last_page:
            page = last_page

        skip = (page - 1) * PAGE_SIZE
        blogs = list(qs.order_by("-created_at").skip(skip).limit(PAGE_SIZE))
        rows = [_serialize_listing_item(b) for b in blogs]

        return _ok({"data": rows, "last_page": last_page, "current_page": page, "total": total})
    except Exception as e:
        return _fail(str(e), 500)


# =====================
# Blog details
# =====================
@api_view(["GET"])
@csrf_exempt
@authenticate
def blog_details(request, blog_id):
    if not is_admin(request.user):
        return _fail("Only admin can access this endpoint", 403)
    try:
        blog = Blog.objects(blog_id=int(blog_id)).first()
        if not blog:
            return _fail("Blog not found", 404)
        return _ok({"blog": _serialize_blog(blog)})
    except Exception as e:
        return _fail(str(e), 500)


# =====================
# Blog add
# =====================
@api_view(["POST"])
@csrf_exempt
@authenticate
def blog_add(request):
    if not is_admin(request.user):
        return _fail("Only admin can create blogs", 403)
    try:
        title = (_get_post_value(request, "title") or "").strip()
        slug_raw = (_get_post_value(request, "slug") or "").strip()
        slug = _slugify(slug_raw or title)
        author = (_get_post_value(request, "author") or "").strip()
        short_content = (_get_post_value(request, "short_content") or "").strip()
        full_content = _get_post_value(request, "full_content") or ""
        status = (_get_post_value(request, "status") or "Published").strip() or "Published"
        mete_title = (_get_post_value(request, "mete_title") or "").strip()
        meta_description = (_get_post_value(request, "meta_description") or "").strip()
        meta_keyword = (_get_post_value(request, "meta_keyword") or "").strip()
        is_trending_raw = _get_post_value(request, "is_trending", "0")
        is_trending = str(is_trending_raw) in ("1", "true", "True", "yes", "on")

        missing = []
        if not mete_title:
            missing.append("mete_title")
        if not meta_description:
            missing.append("meta_description")
        if not meta_keyword:
            missing.append("meta_keyword")
        if not title:
            missing.append("title")
        if not short_content:
            missing.append("short_content")
        if _is_html_empty(full_content):
            missing.append("full_content")
        if not status:
            missing.append("status")

        picture_file = request.FILES.get("picture")
        if not picture_file:
            missing.append("picture")

        if missing:
            return _fail(f"Missing required fields: {', '.join(missing)}")

        if Blog.objects(slug=slug).first():
            return _fail("A blog with this slug already exists")

        faqs = _parse_faqs_from_request(request)
        picture_url = _upload_file(picture_file, folder="homepage/blogs")
        full_content = _replace_cid_images(full_content, request)

        blog = Blog(
            blog_id=IdCounter.next_id("blog"),
            title=title,
            slug=slug,
            author=author,
            short_content=short_content,
            full_content=full_content,
            picture=picture_url,
            status=status,
            is_trending=is_trending,
            mete_title=mete_title,
            meta_description=meta_description,
            meta_keyword=meta_keyword,
            faqs=faqs,
        )
        blog.save()
        return _ok({"blog": _serialize_blog(blog)}, message="Blog created successfully")
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        return _fail(str(e), 500)


# =====================
# Blog update
# =====================
@api_view(["POST", "PUT"])
@csrf_exempt
@authenticate
def blog_update(request, blog_id):
    if not is_admin(request.user):
        return _fail("Only admin can update blogs", 403)
    try:
        blog = Blog.objects(blog_id=int(blog_id)).first()
        if not blog:
            return _fail("Blog not found", 404)

        title = (_get_post_value(request, "title") or blog.title or "").strip()
        slug_in = (_get_post_value(request, "slug") or "").strip() or (blog.slug or "")
        slug = _slugify(slug_in or title)
        author = _get_post_value(request, "author")
        if author is None:
            author = blog.author or ""
        else:
            author = author.strip()
        short_content = (_get_post_value(request, "short_content") or "").strip()
        full_content = _get_post_value(request, "full_content")
        if full_content is None or full_content == "":
            full_content = blog.full_content or ""
        status = (_get_post_value(request, "status") or blog.status or "Published").strip()
        mete_title = (_get_post_value(request, "mete_title") or "").strip()
        meta_description = (_get_post_value(request, "meta_description") or "").strip()
        meta_keyword = (_get_post_value(request, "meta_keyword") or "").strip()

        is_trending_raw = _get_post_value(request, "is_trending", None)
        if is_trending_raw is None or is_trending_raw == "":
            is_trending = bool(blog.is_trending)
        else:
            is_trending = str(is_trending_raw) in ("1", "true", "True", "yes", "on")

        missing = []
        if not mete_title:
            missing.append("mete_title")
        if not meta_description:
            missing.append("meta_description")
        if not meta_keyword:
            missing.append("meta_keyword")
        if not title:
            missing.append("title")
        if not short_content:
            missing.append("short_content")
        if _is_html_empty(full_content):
            missing.append("full_content")
        if not status:
            missing.append("status")
        if missing:
            return _fail(f"Missing required fields: {', '.join(missing)}")

        existing = Blog.objects(slug=slug).first()
        if existing and existing.blog_id != blog.blog_id:
            return _fail("A blog with this slug already exists")

        faqs = _parse_faqs_from_request(request)
        picture_file = request.FILES.get("picture")
        picture_url = blog.picture or ""
        if picture_file:
            picture_url = _upload_file(picture_file, folder="homepage/blogs")
        if not picture_url:
            return _fail("Cover image is required")

        full_content = _replace_cid_images(full_content, request)

        blog.title = title
        blog.slug = slug
        blog.author = author
        blog.short_content = short_content
        blog.full_content = full_content
        blog.picture = picture_url
        blog.status = status
        blog.is_trending = is_trending
        blog.mete_title = mete_title
        blog.meta_description = meta_description
        blog.meta_keyword = meta_keyword
        blog.faqs = faqs
        blog.save()

        return _ok({"blog": _serialize_blog(blog)}, message="Blog updated successfully")
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        return _fail(str(e), 500)


# =====================
# Blog delete
# =====================
@api_view(["DELETE"])
@csrf_exempt
@authenticate
def blog_delete(request, blog_id):
    if not is_admin(request.user):
        return _fail("Only admin can delete blogs", 403)
    try:
        blog = Blog.objects(blog_id=int(blog_id)).first()
        if not blog:
            return _fail("Blog not found", 404)
        blog.delete()
        return _ok(message="Blog deleted successfully")
    except Exception as e:
        return _fail(str(e), 500)


def _format_public_date(dt):
    if not dt:
        return ""
    try:
        return dt.strftime("%B %d, %Y")
    except Exception:
        return ""


def _estimate_read_time(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    words = len([w for w in text.split() if w])
    minutes = max(1, round(words / 200)) if words else 1
    return f"{minutes} min read"


def _serialize_public_list_item(blog: Blog):
    return {
        "id": blog.blog_id,
        "slug": blog.slug or "",
        "title": blog.title or "",
        "excerpt": blog.short_content or "",
        "author": blog.author or "Splash Team",
        "date": _format_public_date(blog.created_at),
        "image": blog.picture or "",
        "image_url": blog.picture or "",
        "is_trending": bool(blog.is_trending),
        "read_time": _estimate_read_time(blog.full_content or ""),
        "meta_title": blog.mete_title or "",
        "meta_description": blog.meta_description or "",
    }


def _serialize_public_post(blog: Blog):
    faqs = []
    for f in blog.faqs or []:
        faqs.append({
            "id": f.id,
            "question": f.question or "",
            "answer": f.answer or "",
        })
    return {
        **_serialize_public_list_item(blog),
        "body": blog.full_content or "",
        "content": blog.full_content or "",
        "short_content": blog.short_content or "",
        "faqs": faqs,
        "meta_keyword": blog.meta_keyword or "",
        "updated_at": blog.updated_at.isoformat() if blog.updated_at else None,
        "created_at": blog.created_at.isoformat() if blog.created_at else None,
    }


# =====================
# Public blog listing (Published only)
# =====================
@api_view(["GET"])
@csrf_exempt
def public_blog_list(request):
    try:
        _clear_legacy_blog_posts()
        page = max(1, _parse_int(request.GET.get("page"), 1) or 1)
        page_size = min(50, max(1, _parse_int(request.GET.get("page_size"), 12) or 12))

        qs = Blog.objects(status="Published")
        total = qs.count()
        last_page = max(1, math.ceil(total / page_size) if total else 1)
        if page > last_page:
            page = last_page

        skip = (page - 1) * page_size
        blogs = list(qs.order_by("-created_at").skip(skip).limit(page_size))
        posts = [_serialize_public_list_item(b) for b in blogs]

        return JsonResponse(
            {
                "status": True,
                "posts": posts,
                "data": {
                    "posts": posts,
                    "last_page": last_page,
                    "current_page": page,
                    "total": total,
                },
            },
            status=200,
        )
    except Exception as e:
        return _fail(str(e), 500)


# =====================
# Public blog detail by slug (Published only)
# =====================
@api_view(["GET"])
@csrf_exempt
def public_blog_detail(request, slug):
    try:
        slug = (slug or "").strip()
        if not slug:
            return _fail("Slug is required", 400)
        blog = Blog.objects(slug=slug, status="Published").first()
        if not blog:
            return _fail("Blog not found", 404)
        post = _serialize_public_post(blog)
        return JsonResponse({"status": True, "post": post, "data": {"post": post}}, status=200)
    except Exception as e:
        return _fail(str(e), 500)


# =====================
# Admin download blog as HTML
# =====================
@api_view(["GET"])
@csrf_exempt
@authenticate
def blog_download(request, blog_id):
    if not is_admin(request.user):
        return _fail("Only admin can download blogs", 403)
    try:
        from django.http import HttpResponse

        blog = Blog.objects(blog_id=int(blog_id)).first()
        if not blog:
            return _fail("Blog not found", 404)

        faqs_html = ""
        for f in blog.faqs or []:
            q = (f.question or "").replace("<", "&lt;").replace(">", "&gt;")
            a = f.answer or ""
            faqs_html += f"<section class='faq'><h3>{q}</h3><div>{a}</div></section>"

        title = blog.title or "Blog"
        author = blog.author or ""
        picture = blog.picture or ""
        cover = (
            f'<img class="cover" src="{picture}" alt="" />'
            if picture
            else ""
        )
        date_str = _format_public_date(blog.created_at)
        body = blog.full_content or ""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 24px 16px 48px;
      background: #f3f4f6;
      color: #111827;
    }}
    .sheet {{
      max-width: 896px;
      margin: 0 auto;
      background: #fff;
      border: 1px solid #e5e7eb;
      padding: 1.75rem 2rem;
      box-sizing: border-box;
    }}
    .sheet > h1 {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 1.875rem;
      margin: 0 0 0.35rem;
    }}
    .meta {{ color: #6b7280; font-size: 0.95rem; margin-bottom: 1.25rem; }}
    .cover {{ max-width: 100%; height: auto; max-height: 420px; object-fit: cover; width: 100%; margin: 0 0 1.25rem; border-radius: 0; }}
    .blog-rendered-content {{
      box-sizing: border-box;
      color: #111827;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      font-size: 16px;
      line-height: 1.65;
      word-wrap: break-word;
    }}
    .blog-rendered-content p {{ margin: 0.5em 0; line-height: 1.65; }}
    .blog-rendered-content h1, .blog-rendered-content h2, .blog-rendered-content h3, .blog-rendered-content h4 {{
      font-weight: 600; margin: 0.75em 0 0.4em; line-height: 1.3;
    }}
    .blog-rendered-content h1 {{ font-size: 1.75rem; }}
    .blog-rendered-content h2 {{ font-size: 1.4rem; }}
    .blog-rendered-content h3 {{ font-size: 1.2rem; }}
    .blog-rendered-content ul, .blog-rendered-content ol {{ padding-left: 1.4rem; margin: 0.5em 0; }}
    .blog-rendered-content a {{ color: #2563eb; text-decoration: underline; }}
    .blog-rendered-content img, .blog-rendered-content img.blog-img {{
      height: auto !important; max-width: 100%; border-radius: 0.375rem; display: inline-block; vertical-align: middle;
    }}
    .blog-rendered-content img.blog-img-top {{ display: block; float: none; clear: both; }}
    .blog-rendered-content img.blog-img-left,
    .blog-rendered-content img.blog-img-wrap {{ float: left; margin: 0 1rem 0.85rem 0; }}
    .blog-rendered-content img.blog-img-right {{ float: right; margin: 0 0 0.85rem 1rem; }}
    .blog-rendered-content .blog-image-row,
    .blog-rendered-content div[data-image-row] {{
      display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; margin: 0.85rem 0; clear: both; width: 100%;
    }}
    .blog-rendered-content .blog-image-row img,
    .blog-rendered-content div[data-image-row] img {{ float: none !important; margin: 0 !important; clear: none !important; }}
    .blog-rendered-content table {{ border-collapse: collapse; table-layout: fixed; width: 100%; margin: 0.75rem 0; }}
    .blog-rendered-content td, .blog-rendered-content th {{
      border: 1px solid #d1d5db; padding: 0.45rem 0.6rem; vertical-align: top; word-break: break-word;
    }}
    .blog-rendered-content th {{ background: #f3f4f6; font-weight: 600; }}
    .blog-rendered-content::after {{ content: ""; display: table; clear: both; }}
    .faq {{ margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid #e5e5e5; }}
  </style>
</head>
<body>
  <article class="sheet">
    <h1>{title}</h1>
    <p class="meta">{author}{' · ' if author and date_str else ''}{date_str} · Status: {blog.status or ''}</p>
    {cover}
    <div class="blog-rendered-content">{body}</div>
    {('<h2>FAQs</h2>' + faqs_html) if faqs_html else ''}
  </article>
</body>
</html>"""

        filename = f"{blog.slug or f'blog-{blog.blog_id}'}.html"
        response = HttpResponse(html, content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        return _fail(str(e), 500)
