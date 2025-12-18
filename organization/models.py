from mongoengine import Document, StringField, DateTimeField, ReferenceField, ListField, DictField
from datetime import datetime


class Organization(Document):
    name = StringField(required=True, unique=True)
    owner = ReferenceField("User", required=True)
    plan = ReferenceField("Plan")
    metadata = DictField()
    members = ListField(ReferenceField("User"))
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {"collection": "organizations"}
