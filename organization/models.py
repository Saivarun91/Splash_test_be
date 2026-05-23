from mongoengine import Document, StringField, DateTimeField, ReferenceField, ListField, DictField, IntField
from datetime import datetime


class Organization(Document):
    name = StringField(required=True, unique=True)
    owner = ReferenceField("User", required=True)
    plan = ReferenceField("Plan")
    metadata = DictField()
    members = ListField(ReferenceField("User"))
    projects = ListField(ReferenceField("Project"))
    credit_balance = IntField(default=0)
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "organizations",
        "strict": False,  # Allow extra fields for backward compatibility
        "allow_inheritance": False
    }
    
    def __str__(self):
        return self.name
