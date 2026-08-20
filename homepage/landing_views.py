"""
Admin + public APIs for the SEO landing-page CMS.
"""
from __future__ import annotations

import html as html_lib
import math
import re
import secrets
from datetime import datetime
from html.parser import HTMLParser

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view

from common.middleware import authenticate
from users.models import Role

from .landing_models import (
    MAX_ECOMMERCE_CARDS,
    MAX_GENERATE_CARDS,
    PAGE_TYPE_LABELS,
    PAGE_TYPE_PATHS,
    PAGE_TYPES,
    AspectRatio,
    EcommerceUseCase,
    GenerateCard,
    LandingPage,
    LandingPageCardRef,
    LandingPageFAQ,
    LandingPageRatioRef,
    LandingPageUseCaseRef,
    LandingPageVisual,
    LandingPageWhyBlock,
)
from .landing_seed import ensure_aspect_ratios
from .models import IdCounter

PAGE_SIZE = 10
ICON_NAME_RE = re.compile(r"^[A-Z][a-zA-Z0-9]{0,79}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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


def _parse_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _body(request):
    data = getattr(request, "data", None)
    if isinstance(data, dict):
        return data
    return {}


def _slugify(value: str) -> str:
    value = (value or "").strip().lower().replace(" ", "-")
    value = re.sub(r"[^a-z0-9-]", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def _iso(dt):
    if not dt:
        return None
    if isinstance(dt, datetime):
        text = dt.isoformat()
        if dt.tzinfo is None and not text.endswith("Z"):
            return text + "Z"
        return text
    return str(dt)


class _HtmlSanitizer(HTMLParser):
    ALLOWED = {
        "p", "br", "strong", "b", "em", "i", "u", "s", "mark",
        "ul", "ol", "li", "a", "h2", "h3", "h4", "blockquote",
        "img", "figure", "figcaption", "span", "div",
        "table", "thead", "tbody", "tr", "th", "td",
    }
    VOID = {"br", "img"}
    SAFE_ATTRS = {"class", "id", "alt", "width", "height", "colspan", "rowspan", "align"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def _attrs(self, tag, attrs):
        parts = []
        for key, val in attrs:
            if not key or key.lower().startswith("on"):
                continue
            key = key.lower()
            val = val or ""
            if key == "href" and tag == "a":
                if val.startswith("http://") or val.startswith("https://") or val.startswith("/"):
                    parts.append(f'href="{html_lib.escape(val, quote=True)}"')
                    parts.append('rel="noopener noreferrer"')
                continue
            if key == "src" and tag == "img":
                if val.startswith("http://") or val.startswith("https://") or val.startswith("/"):
                    parts.append(f'src="{html_lib.escape(val, quote=True)}"')
                continue
            if key == "style":
                safe = re.sub(r"(expression|javascript:|url\s*\()", "", val, flags=re.I)
                parts.append(f'style="{html_lib.escape(safe, quote=True)}"')
                continue
            if key in self.SAFE_ATTRS:
                parts.append(f'{key}="{html_lib.escape(val, quote=True)}"')
        return (" " + " ".join(parts)) if parts else ""

    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED:
            return
        html = f"<{tag}{self._attrs(tag, attrs)}"
        html += " />" if tag in self.VOID else ">"
        self.out.append(html)

    def handle_endtag(self, tag):
        if tag in self.ALLOWED and tag not in self.VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(html_lib.escape(data))


def _sanitize_html(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "<" not in raw:
        return html_lib.escape(raw)
    parser = _HtmlSanitizer()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return html_lib.escape(re.sub(r"<[^>]+>", "", raw))
    return "".join(parser.out).strip()


def _clean_icon(value: str, fallback="Sparkles") -> str:
    name = (value or "").strip()
    if ICON_NAME_RE.match(name):
        return name
    return fallback


def _normalize_type(value: str):
    raw = (value or "").strip().upper()
    aliases = {
        "FEATURE": "FEATURE",
        "FEATURES": "FEATURE",
        "PRODUCT": "PRODUCT",
        "PRODUCTS": "PRODUCT",
        "INDUSTRY": "INDUSTRY",
        "INDUSTRIES": "INDUSTRY",
    }
    return aliases.get(raw)


def _public_path(page_type, slug):
    return f"/{PAGE_TYPE_PATHS.get(page_type, 'pages')}/{slug}"


def _serialize_generate_card(card: GenerateCard):
    return {
        "id": card.card_id,
        "icon": card.icon or "Sparkles",
        "title": card.title or "",
        "tagline": card.tagline or "",
        "created_at": _iso(card.created_at),
        "updated_at": _iso(card.updated_at),
    }


def _serialize_ecommerce(card: EcommerceUseCase):
    return {
        "id": card.use_case_id,
        "icon": card.icon or "ShoppingBag",
        "title": card.title or "",
        "description": card.description or "",
        "created_at": _iso(card.created_at),
        "updated_at": _iso(card.updated_at),
    }


def _serialize_ratio(row: AspectRatio):
    return {
        "id": row.ratio_id,
        "ratio": row.ratio,
        "name": row.name or "",
        "description": row.description or "",
        "use_case": row.use_case or "",
        "sort_order": row.sort_order or 0,
    }


def _serialize_listing(page: LandingPage):
    return {
        "id": page.page_id,
        "type": page.type,
        "type_label": PAGE_TYPE_LABELS.get(page.type, page.type),
        "name": page.name or "",
        "slug": page.slug or "",
        "primary_keyword": page.primary_keyword or "",
        "status": page.status or "Draft",
        "path": _public_path(page.type, page.slug),
        "updated_at": _iso(page.updated_at),
        "published_at": _iso(page.published_at),
        "hero_image": page.hero_image or "",
    }


def _serialize_page(page: LandingPage, *, public=False):
    generate_ids = [ref.card_id for ref in (page.generate_cards or [])]
    generate_map = {}
    if generate_ids:
        for card in GenerateCard.objects(card_id__in=generate_ids):
            generate_map[card.card_id] = card

    ecommerce_ids = [ref.use_case_id for ref in (page.ecommerce_use_cases or [])]
    ecommerce_map = {}
    if ecommerce_ids:
        for card in EcommerceUseCase.objects(use_case_id__in=ecommerce_ids):
            ecommerce_map[card.use_case_id] = card

    ratio_ids = [ref.ratio_id for ref in (page.aspect_ratios or [])]
    ratio_map = {}
    if ratio_ids:
        for row in AspectRatio.objects(ratio_id__in=ratio_ids):
            ratio_map[row.ratio_id] = row

    generate_cards = []
    for ref in sorted(page.generate_cards or [], key=lambda r: r.sort_order or 0):
        card = generate_map.get(ref.card_id)
        if not card:
            continue
        item = _serialize_generate_card(card)
        item["sort_order"] = ref.sort_order or 0
        generate_cards.append(item)

    ecommerce = []
    for ref in sorted(page.ecommerce_use_cases or [], key=lambda r: r.sort_order or 0):
        card = ecommerce_map.get(ref.use_case_id)
        if not card:
            continue
        item = _serialize_ecommerce(card)
        item["sort_order"] = ref.sort_order or 0
        ecommerce.append(item)

    ratios = []
    for ref in sorted(page.aspect_ratios or [], key=lambda r: r.sort_order or 0):
        row = ratio_map.get(ref.ratio_id)
        if not row:
            continue
        item = _serialize_ratio(row)
        item["sort_order"] = ref.sort_order or 0
        ratios.append(item)

    payload = {
        "id": page.page_id,
        "type": page.type,
        "type_label": PAGE_TYPE_LABELS.get(page.type, page.type),
        "name": page.name or "",
        "slug": page.slug or "",
        "primary_keyword": page.primary_keyword or "",
        "seo_description": page.seo_description or "",
        "status": page.status or "Draft",
        "path": _public_path(page.type, page.slug),
        "hero": {
            "title": page.hero_title or "",
            "tagline": page.hero_tagline or "",
            "image": page.hero_image or "",
        },
        "why": {
            "eyebrow": page.why_eyebrow or "",
            "title": page.why_title or "",
            "intro": page.why_intro or "",
            "body": page.why_body or "",
            "blocks": [
                {
                    "id": b.block_id,
                    "heading": b.heading or "",
                    "description": b.description or "",
                    "bullets": list(b.bullets or []),
                    "sort_order": b.sort_order or 0,
                }
                for b in sorted(page.why_blocks or [], key=lambda x: x.sort_order or 0)
            ],
        },
        "generate_title": page.generate_title or "",
        "generate_subtitle": page.generate_subtitle or "",
        "visuals_title": page.visuals_title or "",
        "visuals_subtitle": page.visuals_subtitle or "",
        "ecommerce_title": page.ecommerce_title or "",
        "ecommerce_subtitle": page.ecommerce_subtitle or "",
        "faq_title": page.faq_title or "",
        "article": {
            "title": page.article_title or "",
            "body": page.article_body or "",
        },
        "generate_cards": generate_cards,
        "visuals": [
            {
                "id": v.visual_id,
                "name": v.name or "",
                "image": v.image_url or "",
                "sort_order": v.sort_order or 0,
            }
            for v in sorted(page.visuals or [], key=lambda x: x.sort_order or 0)
            if (v.image_url or "").strip()
        ],
        "aspect_ratios": ratios,
        "ecommerce_use_cases": ecommerce,
        "faqs": [
            {
                "id": f.faq_id,
                "question": f.question or "",
                "answer": f.answer or "",
                "sort_order": f.sort_order or 0,
            }
            for f in sorted(page.faqs or [], key=lambda x: x.sort_order or 0)
            if (f.question or "").strip()
        ],
        "cta": {
            "title": page.cta_title or "",
            "tagline": page.cta_tagline or "",
        },
        "created_at": _iso(page.created_at),
        "updated_at": _iso(page.updated_at),
        "published_at": _iso(page.published_at),
    }
    if not public:
        payload["preview_token"] = page.preview_token or ""
        payload["generate_card_ids"] = [
            {"id": ref.card_id, "sort_order": ref.sort_order or 0}
            for ref in sorted(page.generate_cards or [], key=lambda r: r.sort_order or 0)
        ]
        payload["ecommerce_use_case_ids"] = [
            {"id": ref.use_case_id, "sort_order": ref.sort_order or 0}
            for ref in sorted(page.ecommerce_use_cases or [], key=lambda r: r.sort_order or 0)
        ]
        payload["aspect_ratio_ids"] = [
            {"id": ref.ratio_id, "sort_order": ref.sort_order or 0}
            for ref in sorted(page.aspect_ratios or [], key=lambda r: r.sort_order or 0)
        ]
    return payload


def _publish_errors(page: LandingPage):
    missing = []
    if not page.type:
        missing.append("Page Type")
    if not (page.name or "").strip():
        missing.append("Page Name")
    if not (page.slug or "").strip():
        missing.append("Slug")
    if not (page.primary_keyword or "").strip():
        missing.append("Primary Keyword")
    if not (page.hero_title or "").strip():
        missing.append("Hero Title")
    if not (page.hero_tagline or "").strip():
        missing.append("Hero Tagline")
    if not (page.hero_image or "").strip():
        missing.append("Hero Image")
    return missing


def _apply_page_fields(page: LandingPage, data: dict, *, is_create=False):
    page_type = _normalize_type(data.get("type") or page.type)
    if not page_type:
        raise ValueError("Page Type is required")
    name = (data.get("name") if "name" in data else page.name) or ""
    name = str(name).strip()
    if not name:
        raise ValueError("Page Name is required")

    slug_raw = data.get("slug") if "slug" in data else page.slug
    slug = _slugify(str(slug_raw or ""))
    if not slug:
        raise ValueError("Slug is required")
    if not SLUG_RE.match(slug):
        raise ValueError("Slug must be lowercase, URL-safe, and contain no spaces")

    keyword = data.get("primary_keyword") if "primary_keyword" in data else page.primary_keyword
    keyword = str(keyword or "").strip()
    if not keyword:
        raise ValueError("Primary Keyword is required")

    existing = LandingPage.objects(type=page_type, slug=slug).first()
    if existing and (is_create or existing.page_id != page.page_id):
        raise ValueError("A page with this type and slug already exists")

    page.type = page_type
    page.name = name
    page.slug = slug
    page.primary_keyword = keyword
    if "seo_description" in data:
        page.seo_description = str(data.get("seo_description") or "").strip()

    hero = data.get("hero") if isinstance(data.get("hero"), dict) else {}
    if "title" in hero:
        page.hero_title = str(hero.get("title") or "").strip()
    if "tagline" in hero:
        page.hero_tagline = str(hero.get("tagline") or "").strip()
    if "image" in hero:
        image = str(hero.get("image") or "").strip()
        if image.startswith("data:"):
            raise ValueError("Hero image must be an uploaded file, not base64 data")
        page.hero_image = image

    why = data.get("why") if isinstance(data.get("why"), dict) else {}
    if "eyebrow" in why:
        page.why_eyebrow = str(why.get("eyebrow") or "").strip()
    if "title" in why:
        page.why_title = str(why.get("title") or "").strip()
    if "intro" in why:
        page.why_intro = str(why.get("intro") or "").strip()
    if "body" in why:
        page.why_body = _sanitize_html(str(why.get("body") or ""))
    if "blocks" in why:
        blocks = []
        for index, row in enumerate(why.get("blocks") or []):
            if not isinstance(row, dict):
                continue
            heading = str(row.get("heading") or "").strip()
            description = str(row.get("description") or "").strip()
            bullets = [
                str(b).strip()
                for b in (row.get("bullets") or [])
                if str(b).strip()
            ]
            if not heading and not description and not bullets:
                continue
            block_id = _parse_int(row.get("id")) or IdCounter.next_id("landing_why_block")
            blocks.append(
                LandingPageWhyBlock(
                    block_id=block_id,
                    heading=heading,
                    description=description,
                    bullets=bullets,
                    sort_order=_parse_int(row.get("sort_order"), index) or index,
                )
            )
        page.why_blocks = blocks

    if "generate_card_ids" in data:
        refs = []
        seen = set()
        for index, row in enumerate(data.get("generate_card_ids") or []):
            card_id = _parse_int(row.get("id") if isinstance(row, dict) else row)
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            refs.append(
                LandingPageCardRef(
                    card_id=card_id,
                    sort_order=_parse_int(row.get("sort_order") if isinstance(row, dict) else None, index)
                    or index,
                )
            )
        if len(refs) > MAX_GENERATE_CARDS:
            raise ValueError("You can select a maximum of 6 cards for this section.")
        page.generate_cards = refs

    if "visuals" in data:
        visuals = []
        for index, row in enumerate(data.get("visuals") or []):
            if not isinstance(row, dict):
                continue
            image = str(row.get("image") or row.get("image_url") or "").strip()
            if image.startswith("data:"):
                raise ValueError("Visual images must be uploaded files, not base64 data")
            name = str(row.get("name") or "").strip()
            if not image and not name:
                continue
            visual_id = _parse_int(row.get("id")) or IdCounter.next_id("landing_visual")
            visuals.append(
                LandingPageVisual(
                    visual_id=visual_id,
                    name=name,
                    image_url=image,
                    sort_order=_parse_int(row.get("sort_order"), index) or index,
                    updated_at=datetime.utcnow(),
                )
            )
        page.visuals = visuals

    if "aspect_ratio_ids" in data:
        ensure_aspect_ratios()
        valid_ids = {r.ratio_id for r in AspectRatio.objects}
        refs = []
        seen = set()
        for index, row in enumerate(data.get("aspect_ratio_ids") or []):
            ratio_id = _parse_int(row.get("id") if isinstance(row, dict) else row)
            if not ratio_id or ratio_id in seen or ratio_id not in valid_ids:
                continue
            seen.add(ratio_id)
            refs.append(
                LandingPageRatioRef(
                    ratio_id=ratio_id,
                    sort_order=_parse_int(row.get("sort_order") if isinstance(row, dict) else None, index)
                    or index,
                )
            )
        page.aspect_ratios = refs

    if "ecommerce_use_case_ids" in data:
        refs = []
        seen = set()
        for index, row in enumerate(data.get("ecommerce_use_case_ids") or []):
            use_case_id = _parse_int(row.get("id") if isinstance(row, dict) else row)
            if not use_case_id or use_case_id in seen:
                continue
            seen.add(use_case_id)
            refs.append(
                LandingPageUseCaseRef(
                    use_case_id=use_case_id,
                    sort_order=_parse_int(row.get("sort_order") if isinstance(row, dict) else None, index)
                    or index,
                )
            )
        if len(refs) > MAX_ECOMMERCE_CARDS:
            raise ValueError("You can select a maximum of 6 cards for this section.")
        page.ecommerce_use_cases = refs

    if "faqs" in data:
        faqs = []
        for index, row in enumerate(data.get("faqs") or []):
            if not isinstance(row, dict):
                continue
            question = str(row.get("question") or "").strip()
            answer = _sanitize_html(str(row.get("answer") or "").strip())
            if not question and not answer:
                continue
            if not question or not answer:
                raise ValueError("Each FAQ needs both a question and an answer")
            faq_id = _parse_int(row.get("id")) or IdCounter.next_id("landing_faq")
            faqs.append(
                LandingPageFAQ(
                    faq_id=faq_id,
                    question=question,
                    answer=answer,
                    sort_order=_parse_int(row.get("sort_order"), index) or index,
                    updated_at=datetime.utcnow(),
                )
            )
        page.faqs = faqs

    cta = data.get("cta") if isinstance(data.get("cta"), dict) else {}
    if "title" in cta:
        page.cta_title = str(cta.get("title") or "").strip()
    if "tagline" in cta:
        page.cta_tagline = str(cta.get("tagline") or "").strip()

    for key in (
        "generate_title",
        "generate_subtitle",
        "visuals_title",
        "visuals_subtitle",
        "ecommerce_title",
        "ecommerce_subtitle",
        "faq_title",
    ):
        if key in data:
            setattr(page, key, str(data.get(key) or "").strip())

    article = data.get("article") if isinstance(data.get("article"), dict) else {}
    if "title" in article:
        page.article_title = str(article.get("title") or "").strip()
    if "body" in article:
        page.article_body = _sanitize_html(str(article.get("body") or ""))

    status = data.get("status")
    if status:
        status = str(status).strip().title()
        if status not in ("Draft", "Published"):
            raise ValueError("Status must be Draft or Published")
        if status == "Published":
            missing = _publish_errors(page)
            if missing:
                raise ValueError(f"Cannot publish until these fields are filled: {', '.join(missing)}")
            page.status = "Published"
            if not page.published_at:
                page.published_at = datetime.utcnow()
        else:
            page.status = "Draft"
    elif is_create:
        page.status = "Draft"

    if not page.preview_token:
        page.preview_token = secrets.token_urlsafe(24)
    return page


# ---------------------------------------------------------------------------
# Admin listing / CRUD
# ---------------------------------------------------------------------------
@api_view(["GET"])
@csrf_exempt
@authenticate
def landing_page_listing(request):
    if not is_admin(request.user):
        return _fail("Only admin can access this endpoint", 403)
    try:
        ensure_aspect_ratios()
        page = max(1, _parse_int(request.GET.get("page"), 1) or 1)
        query = (request.GET.get("query") or "").strip()
        page_type = _normalize_type(request.GET.get("type") or "")
        status = (request.GET.get("status") or "").strip().title()

        qs = LandingPage.objects
        if page_type:
            qs = qs.filter(type=page_type)
        if status in ("Draft", "Published"):
            qs = qs.filter(status=status)
        if query:
            pattern = re.escape(query)
            qs = qs.filter(
                __raw__={
                    "$or": [
                        {"name": {"$regex": pattern, "$options": "i"}},
                        {"slug": {"$regex": pattern, "$options": "i"}},
                        {"primary_keyword": {"$regex": pattern, "$options": "i"}},
                    ]
                }
            )

        total = qs.count()
        last_page = max(1, math.ceil(total / PAGE_SIZE) if total else 1)
        if page > last_page:
            page = last_page
        skip = (page - 1) * PAGE_SIZE
        rows = [_serialize_listing(p) for p in qs.order_by("-updated_at").skip(skip).limit(PAGE_SIZE)]
        return _ok(
            {
                "data": rows,
                "last_page": last_page,
                "current_page": page,
                "total": total,
            }
        )
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["GET"])
@csrf_exempt
@authenticate
def landing_page_details(request, page_id):
    if not is_admin(request.user):
        return _fail("Only admin can access this endpoint", 403)
    try:
        ensure_aspect_ratios()
        page = LandingPage.objects(page_id=int(page_id)).first()
        if not page:
            return _fail("Landing page not found", 404)
        return _ok({"page": _serialize_page(page, public=False)})
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["POST"])
@csrf_exempt
@authenticate
def landing_page_add(request):
    if not is_admin(request.user):
        return _fail("Only admin can create landing pages", 403)
    try:
        data = _body(request)
        page = LandingPage(page_id=IdCounter.next_id("landing_page"))
        _apply_page_fields(page, data, is_create=True)
        page.save()
        return _ok({"page": _serialize_page(page)}, message="Landing page created")
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["POST", "PUT"])
@csrf_exempt
@authenticate
def landing_page_update(request, page_id):
    if not is_admin(request.user):
        return _fail("Only admin can update landing pages", 403)
    try:
        page = LandingPage.objects(page_id=int(page_id)).first()
        if not page:
            return _fail("Landing page not found", 404)
        _apply_page_fields(page, _body(request), is_create=False)
        page.save()
        return _ok({"page": _serialize_page(page)}, message="Landing page saved")
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["DELETE"])
@csrf_exempt
@authenticate
def landing_page_delete(request, page_id):
    if not is_admin(request.user):
        return _fail("Only admin can delete landing pages", 403)
    try:
        page = LandingPage.objects(page_id=int(page_id)).first()
        if not page:
            return _fail("Landing page not found", 404)
        page.delete()
        return _ok(message="Landing page deleted")
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["POST"])
@csrf_exempt
@authenticate
def landing_page_publish(request, page_id):
    if not is_admin(request.user):
        return _fail("Only admin can publish landing pages", 403)
    try:
        page = LandingPage.objects(page_id=int(page_id)).first()
        if not page:
            return _fail("Landing page not found", 404)
        missing = _publish_errors(page)
        if missing:
            return _fail(f"Cannot publish until these fields are filled: {', '.join(missing)}")
        page.status = "Published"
        if not page.published_at:
            page.published_at = datetime.utcnow()
        page.save()
        return _ok({"page": _serialize_page(page)}, message="Landing page published")
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["POST"])
@csrf_exempt
@authenticate
def landing_page_unpublish(request, page_id):
    if not is_admin(request.user):
        return _fail("Only admin can unpublish landing pages", 403)
    try:
        page = LandingPage.objects(page_id=int(page_id)).first()
        if not page:
            return _fail("Landing page not found", 404)
        page.status = "Draft"
        page.save()
        return _ok({"page": _serialize_page(page)}, message="Landing page unpublished")
    except Exception as e:
        return _fail(str(e), 500)


# ---------------------------------------------------------------------------
# Global libraries
# ---------------------------------------------------------------------------
@api_view(["GET", "POST"])
@csrf_exempt
@authenticate
def generate_cards_collection(request):
    if not is_admin(request.user):
        return _fail("Only admin can manage generate cards", 403)
    try:
        if request.method == "GET":
            cards = [_serialize_generate_card(c) for c in GenerateCard.objects.order_by("title")]
            return _ok({"cards": cards})
        data = _body(request)
        title = str(data.get("title") or "").strip()
        tagline = str(data.get("tagline") or "").strip()
        if not title or not tagline:
            return _fail("Title and tagline are required")
        card = GenerateCard(
            card_id=IdCounter.next_id("landing_generate_card"),
            icon=_clean_icon(data.get("icon")),
            title=title,
            tagline=tagline,
        )
        card.save()
        return _ok({"card": _serialize_generate_card(card)}, message="Card created")
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["PUT", "POST", "DELETE"])
@csrf_exempt
@authenticate
def generate_card_item(request, card_id):
    if not is_admin(request.user):
        return _fail("Only admin can manage generate cards", 403)
    try:
        card = GenerateCard.objects(card_id=int(card_id)).first()
        if not card:
            return _fail("Card not found", 404)
        if request.method == "DELETE":
            for page in LandingPage.objects:
                before = len(page.generate_cards or [])
                page.generate_cards = [
                    ref for ref in (page.generate_cards or []) if ref.card_id != card.card_id
                ]
                if len(page.generate_cards) != before:
                    page.save()
            card.delete()
            return _ok(message="Card deleted")
        data = _body(request)
        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title:
                return _fail("Title is required")
            card.title = title
        if "tagline" in data:
            tagline = str(data.get("tagline") or "").strip()
            if not tagline:
                return _fail("Tagline is required")
            card.tagline = tagline
        if "icon" in data:
            card.icon = _clean_icon(data.get("icon"), card.icon or "Sparkles")
        card.save()
        return _ok({"card": _serialize_generate_card(card)}, message="Card updated")
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["GET", "POST"])
@csrf_exempt
@authenticate
def ecommerce_cards_collection(request):
    if not is_admin(request.user):
        return _fail("Only admin can manage ecommerce cards", 403)
    try:
        if request.method == "GET":
            cards = [_serialize_ecommerce(c) for c in EcommerceUseCase.objects.order_by("title")]
            return _ok({"cards": cards})
        data = _body(request)
        title = str(data.get("title") or "").strip()
        description = str(data.get("description") or "").strip()
        if not title or not description:
            return _fail("Title and description are required")
        card = EcommerceUseCase(
            use_case_id=IdCounter.next_id("landing_ecommerce_use_case"),
            icon=_clean_icon(data.get("icon"), "ShoppingBag"),
            title=title,
            description=description,
        )
        card.save()
        return _ok({"card": _serialize_ecommerce(card)}, message="Card created")
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["PUT", "POST", "DELETE"])
@csrf_exempt
@authenticate
def ecommerce_card_item(request, use_case_id):
    if not is_admin(request.user):
        return _fail("Only admin can manage ecommerce cards", 403)
    try:
        card = EcommerceUseCase.objects(use_case_id=int(use_case_id)).first()
        if not card:
            return _fail("Card not found", 404)
        if request.method == "DELETE":
            for page in LandingPage.objects:
                before = len(page.ecommerce_use_cases or [])
                page.ecommerce_use_cases = [
                    ref
                    for ref in (page.ecommerce_use_cases or [])
                    if ref.use_case_id != card.use_case_id
                ]
                if len(page.ecommerce_use_cases) != before:
                    page.save()
            card.delete()
            return _ok(message="Card deleted")
        data = _body(request)
        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title:
                return _fail("Title is required")
            card.title = title
        if "description" in data:
            description = str(data.get("description") or "").strip()
            if not description:
                return _fail("Description is required")
            card.description = description
        if "icon" in data:
            card.icon = _clean_icon(data.get("icon"), card.icon or "ShoppingBag")
        card.save()
        return _ok({"card": _serialize_ecommerce(card)}, message="Card updated")
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["GET"])
@csrf_exempt
@authenticate
def aspect_ratios_list(request):
    if not is_admin(request.user):
        return _fail("Only admin can access this endpoint", 403)
    try:
        ensure_aspect_ratios()
        rows = [_serialize_ratio(r) for r in AspectRatio.objects.order_by("sort_order", "ratio_id")]
        return _ok({"ratios": rows})
    except Exception as e:
        return _fail(str(e), 500)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
def _type_from_path(segment: str):
    mapping = {v: k for k, v in PAGE_TYPE_PATHS.items()}
    return mapping.get((segment or "").strip().lower())


@api_view(["GET"])
@csrf_exempt
def public_landing_nav(request):
    """Published pages grouped for the marketing navbar."""
    try:
        grouped = {"FEATURE": [], "PRODUCT": [], "INDUSTRY": []}
        pages = LandingPage.objects(status="Published").order_by("name")
        for page in pages:
            grouped.setdefault(page.type, []).append(
                {
                    "id": page.page_id,
                    "name": page.name,
                    "slug": page.slug,
                    "path": _public_path(page.type, page.slug),
                }
            )
        return JsonResponse(
            {
                "status": True,
                "features": grouped.get("FEATURE") or [],
                "products": grouped.get("PRODUCT") or [],
                "industries": grouped.get("INDUSTRY") or [],
            }
        )
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["GET"])
@csrf_exempt
def public_landing_list(request, page_type):
    try:
        resolved = _type_from_path(page_type) or _normalize_type(page_type)
        if not resolved:
            return _fail("Invalid page type", 404)
        pages = LandingPage.objects(type=resolved, status="Published").order_by("name")
        items = []
        for page in pages:
            items.append(
                {
                    "id": page.page_id,
                    "name": page.name,
                    "slug": page.slug,
                    "primary_keyword": page.primary_keyword,
                    "seo_description": page.seo_description or page.hero_tagline or "",
                    "hero_image": page.hero_image or "",
                    "path": _public_path(page.type, page.slug),
                    "updated_at": _iso(page.updated_at),
                }
            )
        return JsonResponse(
            {
                "status": True,
                "type": resolved,
                "type_label": PAGE_TYPE_LABELS.get(resolved),
                "pages": items,
            }
        )
    except Exception as e:
        return _fail(str(e), 500)


@api_view(["GET"])
@csrf_exempt
def public_landing_detail(request, page_type, slug):
    try:
        resolved = _type_from_path(page_type) or _normalize_type(page_type)
        slug = _slugify(slug or "")
        if not resolved or not slug:
            return _fail("Page not found", 404)
        page = LandingPage.objects(type=resolved, slug=slug).first()
        if not page:
            return _fail("Page not found", 404)

        preview = (request.GET.get("preview") or "").strip()
        is_preview = False
        if preview and page.preview_token:
            try:
                is_preview = secrets.compare_digest(str(preview), str(page.preview_token))
            except Exception:
                is_preview = False
        if page.status != "Published" and not is_preview:
            return _fail("Page not found", 404)

        payload = _serialize_page(page, public=True)
        payload["is_preview"] = is_preview and page.status != "Published"
        payload["indexable"] = page.status == "Published"
        return JsonResponse({"status": True, "page": payload})
    except Exception as e:
        return _fail(str(e), 500)
