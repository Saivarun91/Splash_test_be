"""
MongoEngine models for the SEO landing-page CMS.

N database pages + 1 reusable frontend template.
Global libraries (What We Generate, Ecommerce Use Cases, Aspect Ratios)
are reused across pages via ID references — card content is not duplicated.
"""
from datetime import datetime

from mongoengine import (
    BooleanField,
    DateTimeField,
    Document,
    EmbeddedDocument,
    EmbeddedDocumentField,
    IntField,
    ListField,
    StringField,
)


PAGE_TYPES = ("FEATURE", "PRODUCT", "INDUSTRY")
PAGE_TYPE_LABELS = {
    "FEATURE": "Feature Page",
    "PRODUCT": "Product Page",
    "INDUSTRY": "Industry Page",
}
PAGE_TYPE_PATHS = {
    "FEATURE": "features",
    "PRODUCT": "products",
    "INDUSTRY": "industries",
}
PAGE_STATUSES = ("Draft", "Published")
MAX_GENERATE_CARDS = 6
MAX_ECOMMERCE_CARDS = 6


class GenerateCard(Document):
    """Global 'What We Generate' library card."""

    card_id = IntField(required=True, unique=True)
    icon = StringField(required=True, default="Sparkles")
    title = StringField(required=True)
    tagline = StringField(required=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "landing_generate_cards",
        "indexes": ["card_id", "title"],
        "ordering": ["title"],
        "strict": False,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)


class EcommerceUseCase(Document):
    """Global Ecommerce Use Case library card."""

    use_case_id = IntField(required=True, unique=True)
    icon = StringField(required=True, default="ShoppingBag")
    title = StringField(required=True)
    description = StringField(required=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "landing_ecommerce_use_cases",
        "indexes": ["use_case_id", "title"],
        "ordering": ["title"],
        "strict": False,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)


class AspectRatio(Document):
    """Predefined global aspect-ratio library. Admins cannot create arbitrary ratios."""

    ratio_id = IntField(required=True, unique=True)
    ratio = StringField(required=True, unique=True)
    name = StringField(required=True)
    description = StringField(default="")
    use_case = StringField(default="")
    sort_order = IntField(default=0)
    is_active = BooleanField(default=True)

    meta = {
        "collection": "landing_aspect_ratios",
        "indexes": ["ratio_id", "ratio", "sort_order"],
        "ordering": ["sort_order", "ratio_id"],
        "strict": False,
    }


class LandingPageWhyBlock(EmbeddedDocument):
    block_id = IntField()
    heading = StringField(default="")
    description = StringField(default="")
    bullets = ListField(StringField(), default=list)
    sort_order = IntField(default=0)


class LandingPageVisual(EmbeddedDocument):
    visual_id = IntField()
    name = StringField(default="")
    image_url = StringField(default="")
    sort_order = IntField(default=0)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)


class LandingPageFAQ(EmbeddedDocument):
    faq_id = IntField()
    question = StringField(default="")
    answer = StringField(default="")
    sort_order = IntField(default=0)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)


class LandingPageCardRef(EmbeddedDocument):
    card_id = IntField(required=True)
    sort_order = IntField(default=0)


class LandingPageUseCaseRef(EmbeddedDocument):
    use_case_id = IntField(required=True)
    sort_order = IntField(default=0)


class LandingPageRatioRef(EmbeddedDocument):
    ratio_id = IntField(required=True)
    sort_order = IntField(default=0)


class LandingPage(Document):
    page_id = IntField(required=True, unique=True)
    type = StringField(required=True, choices=PAGE_TYPES)
    name = StringField(required=True)
    slug = StringField(required=True)
    primary_keyword = StringField(required=True)
    seo_description = StringField(default="")
    status = StringField(default="Draft", choices=PAGE_STATUSES)
    preview_token = StringField(default="")

    hero_title = StringField(default="")
    hero_tagline = StringField(default="")
    hero_image = StringField(default="")

    why_eyebrow = StringField(default="")
    why_title = StringField(default="")
    why_intro = StringField(default="")
    why_body = StringField(default="")
    why_blocks = ListField(EmbeddedDocumentField(LandingPageWhyBlock), default=list)

    generate_title = StringField(default="")
    generate_subtitle = StringField(default="")
    visuals_title = StringField(default="")
    visuals_subtitle = StringField(default="")
    ecommerce_title = StringField(default="")
    ecommerce_subtitle = StringField(default="")
    faq_title = StringField(default="")

    article_title = StringField(default="")
    article_body = StringField(default="")

    generate_cards = ListField(EmbeddedDocumentField(LandingPageCardRef), default=list)
    visuals = ListField(EmbeddedDocumentField(LandingPageVisual), default=list)
    aspect_ratios = ListField(EmbeddedDocumentField(LandingPageRatioRef), default=list)
    ecommerce_use_cases = ListField(
        EmbeddedDocumentField(LandingPageUseCaseRef), default=list
    )
    faqs = ListField(EmbeddedDocumentField(LandingPageFAQ), default=list)

    cta_title = StringField(default="")
    cta_tagline = StringField(default="")

    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    published_at = DateTimeField()

    meta = {
        "collection": "landing_pages",
        "indexes": [
            "page_id",
            "slug",
            "type",
            "status",
            {"fields": ["type", "slug"], "unique": True},
            "preview_token",
        ],
        "ordering": ["-updated_at"],
        "strict": False,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    def public_path(self):
        prefix = PAGE_TYPE_PATHS.get(self.type, "pages")
        return f"/{prefix}/{self.slug}"
