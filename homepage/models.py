from mongoengine import Document, StringField, DateTimeField, URLField, IntField, ReferenceField, DictField, ListField
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


class BlogPost(Document):
    """Blog post for /blog listing and detail pages."""
    slug = StringField(required=True, unique=True)
    title = StringField(required=True)
    excerpt = StringField()
    body = StringField()  # HTML or markdown content for post detail
    date = StringField()  # e.g. "October 16, 2025"
    author = StringField(default="Splash Team")
    category = StringField()
    read_time = StringField(default="5 min read")
    image_url = URLField()
    order = IntField(default=0)
    is_published = StringField(default='true')  # 'true' / 'false'
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "blog_posts",
        "indexes": ["slug", "is_published", "order"],
        "ordering": ["order", "-created_at"],
        "strict": False,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


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
