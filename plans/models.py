from mongoengine import Document, StringField, IntField, BooleanField, DictField, ReferenceField, DateTimeField, FloatField, ListField
from datetime import datetime


class Plan(Document):
    name = StringField(required=True, unique=True)
    description = StringField()
    price = FloatField(required=True, default=0.0)
    original_price = FloatField(default=None)  # For discounted plans
    currency = StringField(choices=['USD', 'INR'], default='USD')  # Currency for the plan
    billing_cycle = StringField(choices=['monthly', 'yearly'], default='monthly')
    credits_per_month = IntField(default=1000)
    max_projects = IntField(default=10)
    ai_features_enabled = BooleanField(default=True)
    features = ListField(StringField(), default=list)  # List of feature strings
    is_active = BooleanField(default=True)  # Whether plan is active/available
    is_popular = BooleanField(default=False)  # Whether to highlight as popular
    custom_settings = DictField()
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "plans",
        "strict": False,  # Allow extra fields for backward compatibility
        "allow_inheritance": False
    }
    
    def __str__(self):
        return self.name
