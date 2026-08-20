"""Predefined aspect-ratio library for landing pages."""

DEFAULT_ASPECT_RATIOS = [
    {
        "ratio": "1:1",
        "name": "Square",
        "description": "Ecommerce",
        "use_case": "Product listings, catalogs and marketplaces",
    },
    {
        "ratio": "2:3",
        "name": "Portrait",
        "description": "Mobile First",
        "use_case": "Product photography, mobile-first layouts",
    },
    {
        "ratio": "3:2",
        "name": "Landscape",
        "description": "Web Gallery",
        "use_case": "Website product galleries and banners",
    },
    {
        "ratio": "3:4",
        "name": "Portrait",
        "description": "Social Ads",
        "use_case": "Instagram and Facebook ads",
    },
    {
        "ratio": "4:3",
        "name": "Standard",
        "description": "Web",
        "use_case": "Web, presentations and legacy platforms",
    },
    {
        "ratio": "4:5",
        "name": "Portrait",
        "description": "Social Feed",
        "use_case": "Instagram feed and marketplace galleries",
    },
    {
        "ratio": "5:4",
        "name": "Landscape",
        "description": "Catalog",
        "use_case": "Lookbooks and catalog spreads",
    },
    {
        "ratio": "9:16",
        "name": "Vertical",
        "description": "Social",
        "use_case": "Reels, Stories and Shorts",
    },
    {
        "ratio": "16:9",
        "name": "Widescreen",
        "description": "Web / Video",
        "use_case": "Website banners and video",
    },
    {
        "ratio": "21:9",
        "name": "Ultra-wide",
        "description": "Cinematic",
        "use_case": "Hero banners and cinematic brand visuals",
    },
]


def ensure_aspect_ratios():
    """Idempotently seed the global aspect-ratio library."""
    from .landing_models import AspectRatio
    from .models import IdCounter

    existing = {r.ratio: r for r in AspectRatio.objects}
    created = 0
    for index, item in enumerate(DEFAULT_ASPECT_RATIOS):
        row = existing.get(item["ratio"])
        if row:
            changed = False
            if row.name != item["name"]:
                row.name = item["name"]
                changed = True
            if not row.description:
                row.description = item["description"]
                changed = True
            if not row.use_case:
                row.use_case = item["use_case"]
                changed = True
            if row.sort_order != index:
                row.sort_order = index
                changed = True
            if changed:
                row.save()
            continue
        AspectRatio(
            ratio_id=IdCounter.next_id("landing_aspect_ratio"),
            ratio=item["ratio"],
            name=item["name"],
            description=item["description"],
            use_case=item["use_case"],
            sort_order=index,
            is_active=True,
        ).save()
        created += 1
    return created
