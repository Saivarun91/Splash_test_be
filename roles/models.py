from mongoengine import Document, StringField, ReferenceField, EnumField, DateTimeField
from datetime import datetime
import enum


class OrgRoleType(enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class OrgRole(Document):
    user = ReferenceField("User", required=True)
    organization = ReferenceField("Organization", required=True)
    role = EnumField(OrgRoleType, required=True)
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {"collection": "org_roles"}
