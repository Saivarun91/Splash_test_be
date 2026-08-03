from mongoengine import (
    Document,
    EmbeddedDocument,
    StringField,
    DateTimeField,
    URLField,
    IntField,
    ReferenceField,
    DictField,
    ListField,
    BooleanField,
    EmbeddedDocumentField,
)
from datetime import datetime


class PageContent(Document):
    """
    Flexible CMS-style content for public pages (home, about, vision_mission, tutorials, security).
    One document per page_slug; content is a dict matching frontend structure.
    """
    page_slug = StringField(required=True, unique=True)  # home, about, vision_mission, tutorials, security
    content = DictField(default=dict)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "page_content",
        "indexes": ["page_slug"],
        "strict": False,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"PageContent({self.page_slug})"


class IdCounter(Document):
    """Auto-increment counters for numeric public IDs (blog, faq)."""
    name = StringField(required=True, unique=True)
    seq = IntField(default=0)

    meta = {
        "collection": "id_counters",
        "indexes": ["name"],
        "strict": False,
    }

    @classmethod
    def next_id(cls, name: str) -> int:
        counter = cls.objects(name=name).modify(
            upsert=True,
            new=True,
            set_on_insert__name=name,
            inc__seq=1,
        )
        return int(counter.seq)


class BlogFAQ(EmbeddedDocument):
    id = IntField()
    question = StringField(default="")
    answer = StringField(default="")


class Blog(Document):
    """
    Admin-managed blog post.
    Public site lists posts with status="Published" via /api/homepage/blog/.
    """
    blog_id = IntField(required=True, unique=True)
    title = StringField(required=True)
    slug = StringField(required=True, unique=True)
    author = StringField(default="")
    short_content = StringField(default="")
    full_content = StringField(default="")  # HTML (Description)
    picture = StringField(default="")
    status = StringField(default="Published")  # Published / Draft / Unpublished
    is_trending = BooleanField(default=False)
    mete_title = StringField(default="")  # legacy spelling — keep for API parity
    meta_description = StringField(default="")
    meta_keyword = StringField(default="")
    faqs = ListField(EmbeddedDocumentField(BlogFAQ), default=list)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "blogs",
        "indexes": ["blog_id", "slug", "status", "title", "author"],
        "ordering": ["-created_at"],
        "strict": False,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# Backward-compatible alias so any leftover imports of BlogPost resolve to Blog.
BlogPost = Blog


class PublicGalleryImage(Document):
    """
    Public marketing gallery images for /gallery and optional homepage showcase.
    """
    image_url = StringField(required=True)
    image_type = StringField(required=True)  # lifestyle, campaign, product, model, multi_piece, background_change
    label = StringField()
    alt_text = StringField()
    homepage_layout = StringField()  # product, campaign, lifestyle, model, multipiece
    order = IntField(default=0)
    is_active = StringField(default='true')
    show_on_homepage = StringField(default='false')
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "public_gallery_images",
        "indexes": ["order", "is_active", "show_on_homepage", "image_type"],
        "ordering": ["order", "-created_at"],
        "strict": False,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"PublicGalleryImage({self.image_type}, order={self.order})"


class BeforeAfterImage(Document):
    """
    Model for storing before/after images for the home page
    Each image pair consists of a before image and an after image
    """
    before_image_url = URLField(required=True)
    after_image_url = URLField(required=True)
    before_image_path = StringField()  # Local path if stored locally
    after_image_path = StringField()  # Local path if stored locally
    order = IntField(default=0)  # For ordering images in carousel
    is_active = StringField(default='true')  # 'true' or 'false' as string
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "before_after_images",
        "indexes": ["order", "is_active"],
        "ordering": ["order", "-created_at"],
        "strict": False,
        "allow_inheritance": False
    }
    
    def save(self, *args, **kwargs):
        """Override save to update updated_at timestamp"""
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)
    
    def __str__(self):
        return f"BeforeAfter Image #{self.order}"


class ContactSubmission(Document):
    """
    Model for storing contact form submissions from the footer
    and help center requests (support)
    """
    name = StringField(required=True)
    mobile = StringField(required=True)
    email = StringField(required=True)
    reason = StringField(required=True)
    
    # New fields for Help Center / Support
    user = ReferenceField('User', required=False)  # Link to User model if authenticated
    type = StringField(default='contact', choices=['contact', 'support'])  # discriminate source
    
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "contact_submissions",
        "indexes": ["-created_at", "type", "user"],
        "ordering": ["-created_at"],
        "strict": False
    }
    
    def __str__(self):
        return f"{self.type.title()} from {self.name} ({self.email})"
