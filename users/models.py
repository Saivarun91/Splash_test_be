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
import re
import unicodedata


def generate_slug(text):
    """Generate a URL-friendly slug from text"""
    if not text:
        return ""
    # Normalize unicode characters (e.g., convert é to e)
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('ascii')
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)
    # Remove all non-word characters except hyphens
    text = re.sub(r'[^\w\-]', '', text)
    # Replace multiple hyphens with a single hyphen
    text = re.sub(r'-+', '-', text)
    # Remove leading and trailing hyphens
    text = text.strip('-')
    return text


class Role(enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(Document):
    email = EmailField(required=True, unique=True)
    password = StringField(required=True)  # store hashed passwords!
    full_name = StringField()
    username = StringField(unique=True)
    slug = StringField(max_length=200, unique=True, sparse=True)  # sparse=True allows multiple None values
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

    def save(self, *args, **kwargs):
        # Auto-generate slug if not provided
        if not self.slug:
            # Prefer username, fallback to email (without domain), then full_name
            base_text = None
            if self.username:
                base_text = self.username
            elif self.email:
                # Use email username part (before @)
                base_text = self.email.split('@')[0]
            elif self.full_name:
                base_text = self.full_name
            else:
                # Fallback to email if nothing else available
                base_text = self.email.split('@')[0] if self.email else "user"
            
            base_slug = generate_slug(base_text)
            slug = base_slug
            counter = 1
            # Ensure uniqueness by appending a number if needed
            while User.objects(slug=slug).count() > 0:
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        # Update updated_at timestamp
        self.updated_at = datetime.datetime.utcnow()
        return super().save(*args, **kwargs)

    meta = {
        "collection": "users",
        "indexes": ["slug"],  # Add index for efficient slug lookups
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
