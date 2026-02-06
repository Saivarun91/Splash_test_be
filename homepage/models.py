from mongoengine import Document, StringField, DateTimeField, URLField, IntField
from datetime import datetime


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
    """
    name = StringField(required=True)
    mobile = StringField(required=True)
    email = StringField(required=True)
    reason = StringField(required=True)
    created_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "contact_submissions",
        "indexes": ["-created_at"],
        "ordering": ["-created_at"],
        "strict": False
    }
    
    def __str__(self):
        return f"Contact from {self.name} ({self.email})"
