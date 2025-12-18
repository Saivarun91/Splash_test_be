from mongoengine import Document, ReferenceField, DateTimeField, IntField
from datetime import datetime


class OrgUsageSnapshotDaily(Document):
    organization = ReferenceField("Organization", required=True)
    date = DateTimeField(required=True)
    images_generated = IntField(default=0)
    credits_used = IntField(default=0)
    active_users = IntField(default=0)
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {"collection": "org_usage_snapshot_daily"}
