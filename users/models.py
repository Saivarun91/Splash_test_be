from mongoengine import (
    Document,
    StringField,
    EmailField,
    BooleanField,
    DateTimeField,
    EnumField,
    ListField,
    ReferenceField,
    IntField,
)
import datetime
import enum


class Role(enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(Document):
    email = EmailField(required=True, unique=True)
    password = StringField(required=True)  # store hashed passwords!
    full_name = StringField()
    username = StringField(unique=True)
    role = EnumField(Role, default=Role.USER)
    organization = ReferenceField("Organization", required=False)
    organization_role = StringField(required=False)  # owner, editor, chief_editor, etc.
    profile_completed = BooleanField(default=False)  # Track if user has completed profile setup
    preferred_language = StringField(default='en')  # User's preferred language (en, es, etc.)
    reset_password_token = StringField(required=False)  # Token for password reset
    reset_password_token_expiry = DateTimeField(required=False)  # Expiry for reset token

    # Use string reference to avoid circular import
    projects = ListField(ReferenceField("Project"), default=list)

    # Credit balance for single users (not in an organization)
    credit_balance = IntField(default=0)

    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "users",
        "strict": False,  # Allow extra fields for backward compatibility
        "allow_inheritance": False
    }

    def __str__(self):
        return self.email


# from mongoengine import Document, StringField, EmailField, BooleanField, DateTimeField, EnumField, ListField, ReferenceField
# from datetime import datetime
# import enum


# class UserRole(enum.Enum):
#     ADMIN = "admin"
#     MEMBER = "member"


# class User(Document):
#     email = EmailField(required=True, unique=True)
#     username = StringField(unique=True, required=True)
#     full_name = StringField()
#     password = StringField(required=True)  # Hashed password
#     role = EnumField(UserRole, default=UserRole.MEMBER)
#     organization = ReferenceField("Organization", required=False)
#     projects = ListField(ReferenceField("Project"), default=list)
#     is_active = BooleanField(default=True)
#     created_at = DateTimeField(default=datetime.utcnow)
#     updated_at = DateTimeField(default=datetime.utcnow)

#     meta = {"collection": "USER", "indexes": ["email", "username"]}

#     def __str__(self):
#         return self.email
