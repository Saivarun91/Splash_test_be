from mongoengine import Document, StringField, IntField, BooleanField, DictField, ReferenceField, DateTimeField
from datetime import datetime


class Plan(Document):
    name = StringField(required=True, unique=True)
    description = StringField()
    credits_per_month = IntField(default=1000)
    max_projects = IntField(default=10)
    ai_features_enabled = BooleanField(default=True)
    custom_settings = DictField()
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {"collection": "plans"}
