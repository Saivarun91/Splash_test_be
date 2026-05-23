from mongoengine import Document, StringField, DateTimeField
from datetime import datetime


class LegalCompliance(Document):
    """
    Legal compliance documents model
    Stores terms and conditions, privacy policy, and GDPR compliance content
    """
    content_type = StringField(required=True, choices=['terms', 'privacy', 'gdpr'], unique=True)
    title = StringField(required=True)
    content = StringField(required=True)  # HTML content
    version = StringField(default='1.0')
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "legal_compliance",
        "indexes": ["content_type"],
        "strict": False,
        "allow_inheritance": False
    }
    
    def save(self, *args, **kwargs):
        """Override save to update updated_at timestamp"""
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.content_type} - {self.title}"
