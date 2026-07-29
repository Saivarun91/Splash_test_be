"""Helpers for public pricing cards (Free / Starter / Growth / Custom)."""

from datetime import datetime

from .models import Plan

DEFAULT_PRICING_PLANS = [
    {
        "slug": "free",
        "name": "Free",
        "description": "Try Splash with complimentary credits — no card required.",
        "price": 0.0,
        "price_display": "Free",
        "currency": "INR",
        "billing_cycle": "monthly",
        "credits_per_month": 10,
        "images_note": "Create up to 5 new images.",
        "features": [
            "Premium AI image generation",
            "High-resolution downloads",
        ],
        "is_active": True,
        "is_popular": False,
        "icon": "sparkles",
        "cta_text": "Start Free",
        "cta_variant": "outline",
        "cta_href": "/signup",
        "sort_order": 0,
        "razorpay_enabled": False,
    },
    {
        "slug": "starter",
        "name": "Starter",
        "description": "Perfect for small jewelry brands & startups.",
        "price": 4999.0,
        "price_usd": 59.0,
        "currency": "INR",
        "billing_cycle": "monthly",
        "credits_per_month": 100,
        "images_note": "Create up to 50 new images.",
        "features": [
            "Premium AI image generation",
            "High-resolution downloads",
            "Email support",
        ],
        "is_active": True,
        "is_popular": False,
        "icon": "diamond",
        "cta_text": "Get Started",
        "cta_variant": "outline",
        "sort_order": 1,
        "razorpay_enabled": True,
    },
    {
        "slug": "growth",
        "name": "Growth",
        "description": "Ideal for growing jewelry brands.",
        "price": 13999.0,
        "price_usd": 169.0,
        "currency": "INR",
        "billing_cycle": "monthly",
        "credits_per_month": 300,
        "images_note": "Create up to 150 new images.",
        "features": [
            "Premium AI image generation",
            "High-resolution downloads",
            "Better value per credit",
            "Priority email support",
        ],
        "is_active": True,
        "is_popular": True,
        "badge_text": "MOST POPULAR",
        "icon": "trending-up",
        "cta_text": "Get Started",
        "cta_variant": "solid",
        "sort_order": 2,
        "razorpay_enabled": True,
    },
    {
        "slug": "custom",
        "name": "Custom",
        "description": "Built for high-volume jewelry brands & agencies.",
        "price": 0.0,
        "currency": "INR",
        "billing_cycle": "monthly",
        "credits_per_month": 400,
        "credits_label": "400+",
        "images_note": "Custom credit allocation designed for high-volume image generation and agencies.",
        "features": [
            "Premium AI image generation",
            "High-resolution downloads",
            "Lowest cost per credit",
            "Dedicated priority support",
        ],
        "is_active": True,
        "is_popular": False,
        "icon": "crown",
        "cta_text": "Contact Sales",
        "cta_variant": "outline",
        "cta_href": "/contact",
        "sort_order": 3,
        "razorpay_enabled": False,
    },
]

DEFAULT_FOOTER_NOTE = "Secure payments. Cancel or change plans anytime."

PRICING_SIGNUP_CREDITS = 10
DEFAULT_FREE_SIGNUP_CREDITS = 10

DEFAULT_PRICE_USD_BY_SLUG = {
    "starter": 59.0,
    "growth": 169.0,
}


def _plan_slug(plan):
    return str(
        getattr(plan, "slug", None) or (plan.custom_settings or {}).get("slug") or ""
    ).lower()


def _parse_plan_credits(value):
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = value.replace("+", "").strip()
        if digits.isdigit():
            return int(digits)
    return None


def get_free_plan_signup_credits(default=DEFAULT_FREE_SIGNUP_CREDITS):
    """Credits granted on direct signup (no pricing-page flow)."""
    for plan in get_pricing_plans_queryset(active_only=True):
        if _plan_slug(plan) != "free":
            continue
        credits = _parse_plan_credits(getattr(plan, "credits_per_month", None))
        if credits is None:
            credits = _parse_plan_credits(
                getattr(plan, "credits_label", None)
                or (plan.custom_settings or {}).get("credits_label")
            )
        if credits is not None:
            return credits
    return default


def resolve_signup_credits(signup_source=None):
    if str(signup_source or "").lower() == "pricing":
        return PRICING_SIGNUP_CREDITS
    return get_free_plan_signup_credits()


def is_pricing_plan(plan):
    plan_type = getattr(plan, "plan_type", None) or (plan.custom_settings or {}).get("plan_type")
    if plan_type == "pricing":
        return True
    slug = getattr(plan, "slug", None) or (plan.custom_settings or {}).get("slug")
    return bool(slug)


def serialize_pricing_plan(plan):
    cs = plan.custom_settings or {}
    slug = getattr(plan, "slug", None) or cs.get("slug") or str(plan.id)
    billing_cycle = plan.billing_cycle or "monthly"
    cycle_short = "month" if billing_cycle == "monthly" else billing_cycle.replace("ly", "")

    credits = plan.credits_per_month
    credits_label = getattr(plan, "credits_label", None) or cs.get("credits_label")
    if credits_label:
        credits_display = credits_label
    else:
        credits_display = credits

    price_display = getattr(plan, "price_display", None) or cs.get("price_display")
    cta_href = getattr(plan, "cta_href", None) or cs.get("cta_href")

    icon = getattr(plan, "icon", None) or cs.get("icon") or "diamond"
    if _plan_slug(plan) == "free" and icon in (None, "", "diamond"):
        icon = "sparkles"

    return {
        "id": slug,
        "slug": slug,
        "db_id": str(plan.id),
        "name": plan.name,
        "description": plan.description or "",
        "price": plan.price if plan.price else None,
        "priceUsd": getattr(plan, "price_usd", None),
        "priceDisplay": price_display,
        "currency": getattr(plan, "currency", "INR") or "INR",
        "billingCycle": cycle_short,
        "credits": credits_display,
        "creditsNumeric": credits,
        "creditsLabel": getattr(plan, "credits_label", None) or cs.get("credits_label") or "Credits",
        "imagesNote": getattr(plan, "images_note", None) or cs.get("images_note") or "",
        "features": plan.features or [],
        "featured": bool(plan.is_popular),
        "badge": getattr(plan, "badge_text", None) or cs.get("badge_text"),
        "icon": icon,
        "cta": getattr(plan, "cta_text", None) or cs.get("cta_text") or "Get Started",
        "ctaVariant": getattr(plan, "cta_variant", None) or cs.get("cta_variant") or "outline",
        "ctaHref": cta_href,
        "is_active": plan.is_active,
        "sort_order": getattr(plan, "sort_order", None) or cs.get("sort_order") or 0,
        "razorpay_enabled": getattr(plan, "razorpay_enabled", True)
        if getattr(plan, "razorpay_enabled", None) is not None
        else cs.get("razorpay_enabled", True),
    }


def get_pricing_plans_queryset(active_only=True):
    plans = list(Plan.objects())
    pricing = [p for p in plans if is_pricing_plan(p)]
    if active_only:
        pricing = [p for p in pricing if p.is_active]
    pricing.sort(key=lambda p: getattr(p, "sort_order", None) or (p.custom_settings or {}).get("sort_order") or 0)
    return pricing


def _create_pricing_plan_from_defaults(data):
    slug = data["slug"]
    plan = Plan(
        name=data["name"],
        description=data.get("description", ""),
        price=float(data.get("price", 0)),
        price_usd=float(data["price_usd"]) if data.get("price_usd") not in (None, "") else None,
        currency=data.get("currency", "INR"),
        billing_cycle=data.get("billing_cycle", "monthly"),
        credits_per_month=int(data.get("credits_per_month", 0)),
        features=data.get("features", []),
        is_active=data.get("is_active", True),
        is_popular=data.get("is_popular", False),
        plan_type="pricing",
        slug=slug,
        price_display=data.get("price_display"),
        images_note=data.get("images_note"),
        icon=data.get("icon", "diamond"),
        badge_text=data.get("badge_text"),
        cta_text=data.get("cta_text", "Get Started"),
        cta_variant=data.get("cta_variant", "outline"),
        cta_href=data.get("cta_href"),
        sort_order=data.get("sort_order", 0),
        razorpay_enabled=data.get("razorpay_enabled", True),
        credits_label=data.get("credits_label"),
        custom_settings={"plan_type": "pricing", "slug": slug},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    plan.save()
    return plan


def ensure_pricing_plans():
    """Create default pricing cards when DB is empty or missing standard slugs."""
    existing = get_pricing_plans_queryset(active_only=False)
    if not existing:
        return [_create_pricing_plan_from_defaults(data) for data in DEFAULT_PRICING_PLANS]

    existing_slugs = {_plan_slug(p) for p in existing}
    created = []
    for data in DEFAULT_PRICING_PLANS:
        if data["slug"] not in existing_slugs:
            created.append(_create_pricing_plan_from_defaults(data))

    for plan in get_pricing_plans_queryset(active_only=False):
        slug = _plan_slug(plan)
        changed = False
        if slug == "free":
            current_icon = getattr(plan, "icon", None) or (plan.custom_settings or {}).get("icon")
            if current_icon in (None, "", "diamond"):
                plan.icon = "sparkles"
                changed = True
        default_usd = DEFAULT_PRICE_USD_BY_SLUG.get(slug)
        if default_usd is not None and getattr(plan, "price_usd", None) in (None,):
            plan.price_usd = float(default_usd)
            changed = True
        if changed:
            plan.updated_at = datetime.utcnow()
            plan.save()

    return created


def seed_pricing_plans_if_empty():
    return ensure_pricing_plans()


def apply_pricing_payload(plan, data, user=None):
    if "name" in data:
        plan.name = data["name"]
    if "description" in data:
        plan.description = data["description"]
    if "price" in data:
        plan.price = float(data["price"] or 0)
    if "price_usd" in data:
        raw_usd = data["price_usd"]
        plan.price_usd = float(raw_usd) if raw_usd not in (None, "") else None
    if "price_display" in data:
        plan.price_display = data["price_display"] or None
    if "currency" in data:
        plan.currency = data["currency"]
    if "billing_cycle" in data:
        plan.billing_cycle = data["billing_cycle"]
    if "credits_per_month" in data:
        plan.credits_per_month = int(data["credits_per_month"] or 0)
    if "credits_label" in data:
        plan.credits_label = data["credits_label"] or None
    if "images_note" in data:
        plan.images_note = data["images_note"] or ""
    if "features" in data:
        plan.features = [f for f in data["features"] if f and str(f).strip()]
    if "is_active" in data:
        plan.is_active = bool(data["is_active"])
    if "is_popular" in data:
        plan.is_popular = bool(data["is_popular"])
    if "badge_text" in data:
        plan.badge_text = data["badge_text"] or None
    if "icon" in data:
        plan.icon = data["icon"] or "diamond"
    if "cta_text" in data:
        plan.cta_text = data["cta_text"] or "Get Started"
    if "cta_variant" in data:
        plan.cta_variant = data["cta_variant"] or "outline"
    if "cta_href" in data:
        plan.cta_href = data["cta_href"] or None
    if "sort_order" in data:
        plan.sort_order = int(data["sort_order"] or 0)
    if "razorpay_enabled" in data:
        plan.razorpay_enabled = bool(data["razorpay_enabled"])
    if "slug" in data and data["slug"]:
        plan.slug = data["slug"]
    plan.plan_type = "pricing"
    cs = plan.custom_settings or {}
    cs["plan_type"] = "pricing"
    cs["slug"] = plan.slug
    plan.custom_settings = cs
    if user:
        plan.updated_by = user
    plan.updated_at = datetime.utcnow()
    return plan
