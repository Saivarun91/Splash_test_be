from mongoengine import Document, ReferenceField, IntField, StringField, DateTimeField, DictField, FloatField
from datetime import datetime


class CreditSettings(Document):
    """Global credit deduction settings - singleton pattern"""
    credits_per_image_generation = IntField(default=2, required=True)
    credits_per_regeneration = IntField(default=1, required=True)
    updated_by = ReferenceField("User")
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "credit_settings",
        "strict": False,
    }
    
    def __str__(self):
        return f"Image: {self.credits_per_image_generation}, Regeneration: {self.credits_per_regeneration}"
    
    @classmethod
    def get_settings(cls):
        """Get or create default credit settings (singleton)"""
        settings = cls.objects.first()
        if not settings:
            settings = cls(
                credits_per_image_generation=2,
                credits_per_regeneration=1
            )
            settings.save()
        return settings


class CreditLedger(Document):
    user = ReferenceField("User", required=True)
    organization = ReferenceField("Organization", required=True)
    project = ReferenceField("Project", required=False)
    change_type = StringField(choices=["debit", "credit"], required=True)
    credits_changed = IntField(required=True)
    balance_after = IntField(required=True)
    reason = StringField()
    metadata = DictField()
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "credit_ledger",
        "strict": False,  # Allow extra fields for backward compatibility
        "allow_inheritance": False
    }
    
    def __str__(self):
        return f"{self.organization.name} - {self.change_type} - {self.credits_changed}"
