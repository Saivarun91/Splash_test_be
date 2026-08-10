"""
Admin blog APIs aligned with /admin/blog/* contract.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view

from common.middleware import authenticate
from imgbackendapp.file_utils import save_uploaded_file, to_media_db_path
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
        "robots": BLOG_ROBOTS_DEFAULT,
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
    """Save cover image under MEDIA_ROOT and return a root-relative ``/media/...`` path."""
    parts = [p for p in str(folder or "homepage/blogs").replace("\\", "/").split("/") if p]
    base_dir = os.path.join(str(settings.MEDIA_ROOT), *parts)
    absolute_path = save_uploaded_file(file_obj, base_dir)
    return to_media_db_path(absolute_path)


def _save_inline_blog_image(file_obj, cid: str) -> str:
    """Save an inline blog image under MEDIA_ROOT and return ``/media/...`` URL."""
    base_dir = os.path.join(str(settings.MEDIA_ROOT), "homepage", "blogs", "inline")
    os.makedirs(base_dir, exist_ok=True)

    safe_cid = re.sub(r"[^a-zA-Z0-9_-]", "", cid) or "inline"
    ext = os.path.splitext(getattr(file_obj, "name", "") or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".webp"

    dest_path = os.path.join(base_dir, f"{safe_cid}{ext}")
    with open(dest_path, "wb+") as dest:
        for chunk in file_obj.chunks():
            dest.write(chunk)
    return to_media_db_path(dest_path)


def _replace_cid_images(html: str, request) -> str:
    """Replace cid:xxx placeholders with local media URLs from images[xxx] files."""
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
        url = _save_inline_blog_image(file_obj, cid)
        content = content.replace(f"cid:{cid}", url)
    return content


def _parse_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


BLOG_ROBOTS_DEFAULT = "index,follow"


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
        is_trending_raw = (_get_post_value(request, "is_trending", "0"))
        is_trending = str(is_trending_raw) in ("1", "true", "True", "yes", "on")
        robots = BLOG_ROBOTS_DEFAULT

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
            robots=robots,
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

        robots = BLOG_ROBOTS_DEFAULT

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
        blog.robots = robots
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
        "meta_keyword": getattr(blog, "meta_keyword", "") or "",
        "robots": BLOG_ROBOTS_DEFAULT,
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
        "robots": BLOG_ROBOTS_DEFAULT,
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
# Admin download blog as PDF
# =====================
@api_view(["GET"])
@csrf_exempt
@authenticate
def blog_download(request, blog_id):
    if not is_admin(request.user):
        return _fail("Only admin can download blogs", 403)
    try:
        from django.http import HttpResponse
        from io import BytesIO
        from xhtml2pdf import pisa

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
        cover_src = picture
        if picture.startswith("/media/"):
            from imgbackendapp.file_utils import resolve_media_path

            fs_path = resolve_media_path(picture)
            if os.path.isfile(fs_path):
                cover_src = fs_path.replace("\\", "/")
            elif request:
                cover_src = request.build_absolute_uri(picture)
        cover = (
            f'<img class="cover" src="{cover_src}" alt="" />'
            if picture
            else ""
        )
        date_str = _format_public_date(blog.created_at)
        body = blog.full_content or ""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    @page {{ margin: 1.5cm; }}
    body {{
      margin: 0;
      padding: 0;
      color: #111827;
      font-family: Helvetica, Arial, sans-serif;
      font-size: 12pt;
      line-height: 1.55;
    }}
    h1 {{
      font-size: 22pt;
      margin: 0 0 8pt;
    }}
    .meta {{ color: #6b7280; font-size: 10pt; margin-bottom: 14pt; }}
    .cover {{ max-width: 100%; height: auto; max-height: 320px; margin: 0 0 14pt; }}
    .blog-rendered-content {{ word-wrap: break-word; }}
    .blog-rendered-content p {{ margin: 0.45em 0; }}
    .blog-rendered-content h1, .blog-rendered-content h2, .blog-rendered-content h3, .blog-rendered-content h4 {{
      font-weight: bold; margin: 0.65em 0 0.35em;
    }}
    .blog-rendered-content h1 {{ font-size: 18pt; }}
    .blog-rendered-content h2 {{ font-size: 15pt; }}
    .blog-rendered-content h3 {{ font-size: 13pt; }}
    .blog-rendered-content ul, .blog-rendered-content ol {{ padding-left: 1.2em; margin: 0.45em 0; }}
    .blog-rendered-content a {{ color: #2563eb; text-decoration: underline; }}
    .blog-rendered-content img, .blog-rendered-content img.blog-img {{
      height: auto; max-width: 100%; display: inline-block; vertical-align: middle;
    }}
    .blog-rendered-content img.blog-img-left,
    .blog-rendered-content img.blog-img-wrap {{ float: left; margin: 0 10pt 10pt 0; }}
    .blog-rendered-content img.blog-img-right {{ float: right; margin: 0 0 10pt 10pt; }}
    .blog-rendered-content .blog-image-row,
    .blog-rendered-content div[data-image-row] {{
      display: block; clear: both; margin: 10pt 0;
    }}
    .blog-rendered-content .blog-image-row img,
    .blog-rendered-content div[data-image-row] img {{
      display: inline-block; margin: 0 8pt 8pt 0; max-width: 45%;
    }}
    .blog-rendered-content table {{ border-collapse: collapse; width: 100%; margin: 10pt 0; }}
    .blog-rendered-content td, .blog-rendered-content th {{
      border: 1px solid #d1d5db; padding: 6pt 8pt; vertical-align: top; word-break: break-word;
    }}
    .blog-rendered-content th {{ background: #f3f4f6; font-weight: bold; }}
    .faq {{ margin-top: 14pt; padding-top: 10pt; border-top: 1px solid #e5e5e5; page-break-inside: avoid; }}
  </style>
</head>
<body>
  <article>
    <h1>{title}</h1>
    <p class="meta">{author}{' · ' if author and date_str else ''}{date_str} · Status: {blog.status or ''}</p>
    {cover}
    <div class="blog-rendered-content">{body}</div>
    {('<h2>FAQs</h2>' + faqs_html) if faqs_html else ''}
  </article>
</body>
</html>"""

        pdf_buffer = BytesIO()
        pdf_status = pisa.CreatePDF(html, dest=pdf_buffer, encoding="utf-8")
        if pdf_status.err:
            return _fail("Failed to generate PDF", 500)

        filename = f"{blog.slug or f'blog-{blog.blog_id}'}.pdf"
        response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        return _fail(str(e), 500)
