from mongoengine import Document, StringField, DateTimeField, ListField, ReferenceField, ImageField, URLField, EmbeddedDocument, EmbeddedDocumentField, DictField, BooleanField, IntField
from datetime import datetime
from users.models import User
import enum
from datetime import timezone
import re
import unicodedata
# -----------------------------
# Project Model
# -----------------------------


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


class ProjectRole(enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

# Embedded document for a project member with role


class ProjectMember(EmbeddedDocument):
    user = ReferenceField("User", required=True)
    role = StringField(
        choices=[r.value for r in ProjectRole], default=ProjectRole.VIEWER.value)
    joined_at = DateTimeField(default=datetime.now(timezone.utc))

# Project model


class Project(Document):
    name = StringField(max_length=200, required=True)
    slug = StringField(max_length=200, unique=True, sparse=True)  # sparse=True allows multiple None values
    about = StringField()
    organization = ReferenceField("Organization", required=False)  # Optional: projects can belong to an organization
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.now(timezone.utc))
    updated_at = DateTimeField(default=datetime.now(timezone.utc))
    status = StringField(default="progress")
    team_members = ListField(EmbeddedDocumentField(ProjectMember))

    def save(self, *args, **kwargs):
        # Auto-generate slug if not provided
        if not self.slug and self.name:
            base_slug = generate_slug(self.name)
            slug = base_slug
            counter = 1
            # Ensure uniqueness by appending a number if needed
            while Project.objects(slug=slug).count() > 0:
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        # Update updated_at timestamp
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    meta = {
        'collection': 'projectsUpdated',
        'ordering': ['-created_at'],
        'indexes': ['slug'],  # Add index for efficient slug lookups
        'strict': False,  # Allow extra fields for backward compatibility
        'allow_inheritance': False
    }


# class Project(Document):
#     name = StringField(required=True)
#     about = StringField()
#     organization = ReferenceField("Organization", required=True)
#     created_by = ReferenceField("User", required=True)
#     team_members = ListField(EmbeddedDocumentField(ProjectMember))
#     status = StringField(default="active")
#     created_at = DateTimeField(default=datetime.utcnow)
#     updated_at = DateTimeField(default=datetime.utcnow)

#     meta = {"collection": "projects", "indexes": ["organization", "created_by"]}
# -----------------------------
# Embedded document for collection items
# -----------------------------


class ProductImage(EmbeddedDocument):
    uploaded_image_url = URLField(required=True)
    uploaded_image_path = StringField()
    # For each product, store multiple generated versions as a list of dicts
    generated_images = ListField(DictField())
    # Track when this product image was uploaded
    uploaded_at = DateTimeField(default=datetime.now(timezone.utc))
    # Store the type of ornament (e.g., "short_necklace", "long_necklace", "stud_earrings", etc.)
    ornament_type = StringField()
    generation_selections = DictField(default=lambda: {"plainBg": False, "bgReplace": False, "model": False, "campaign": False})
    meta = {
        'strict': False,  # Allow unknown fields to prevent errors with legacy data
        'allow_inheritance': False
    }

    
class UploadedImage(EmbeddedDocument):
    """Embedded document for uploaded images with both local and cloud storage"""
    local_path = StringField(required=True)
    cloud_url = URLField(required=True)
    original_filename = StringField(required=True)
    uploaded_by = StringField(required=True)  # User ID who uploaded
    uploaded_at = DateTimeField(default=datetime.now(timezone.utc))
    file_size = IntField()
    # 'theme', 'background', 'pose', 'location', 'color'
    category = StringField(required=True)
    analysis = StringField(default="")   # ✅ Clean descriptive paragraph
    # For theme images: store ornament type and angle shot separately
    # Type of ornament (e.g., "long_necklace", "stud_earrings")
    ornament_type = StringField(default="")
    # Overall angle shot description (e.g., "overhead 90-degree angle", "flat-lay top-down view")
    angle_shot = StringField(default="")
    # Theme description without ornament type and angle shot
    theme_description = StringField(default="")

    meta = {
        'strict': False,
        'allow_inheritance': False
    }


class CollectionItem(EmbeddedDocument):
    suggested_themes = ListField(StringField(), default=list)
    suggested_backgrounds = ListField(StringField(), default=list)
    suggested_poses = ListField(StringField(), default=list)
    suggested_locations = ListField(StringField(), default=list)
    suggested_colors = ListField(StringField(), default=list)

    selected_themes = ListField(StringField(), default=list)
    selected_backgrounds = ListField(StringField(), default=list)
    selected_poses = ListField(StringField(), default=list)
    selected_locations = ListField(StringField(), default=list)
    selected_colors = ListField(StringField(), default=list)

    # New fields for color picker functionality
    # Store hex color codes
    picked_colors = ListField(StringField(), default=list)
    # Store user instructions for color usage
    color_instructions = StringField(default="")
    # Store global instructions for all uploaded content
    global_instructions = StringField(default="")

    # New structure for uploaded images with both local and cloud storage
    uploaded_theme_images = ListField(
        EmbeddedDocumentField(UploadedImage), default=list)
    uploaded_background_images = ListField(
        EmbeddedDocumentField(UploadedImage), default=list)
    uploaded_pose_images = ListField(
        EmbeddedDocumentField(UploadedImage), default=list)
    uploaded_location_images = ListField(
        EmbeddedDocumentField(UploadedImage), default=list)
    uploaded_color_images = ListField(
        EmbeddedDocumentField(UploadedImage), default=list)

    final_moodboard_prompt = StringField()
    moodboard_explanation = StringField()
    generated_prompts = DictField()
    generated_model_images = ListField(DictField())
    uploaded_model_images = ListField(DictField())
    # Stores the single selected model (type: 'ai' or 'real', local, cloud)
    selected_model = DictField()
    product_images = ListField(EmbeddedDocumentField(ProductImage))
    # Store master analyses for each category (theme, background, pose, location, color)
    master_analyses = DictField(default=dict)

    meta = {
        'strict': False,  # Allow unknown fields to prevent errors with legacy data
        'allow_inheritance': False
    }

# -----------------------------
# Collection Model
# -----------------------------


class Collection(Document):
    project = ReferenceField(Project, required=True,
                             reverse_delete_rule=2)  # CASCADE
    description = StringField()
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.now(timezone.utc))
    updated_at = DateTimeField(default=datetime.now(timezone.utc))
    target_audience = StringField()
    campaign_season = StringField()
    items = ListField(EmbeddedDocumentField(CollectionItem))

    def __str__(self):
        return f"{self.project.name} Collection"

    meta = {
        'collection': 'collections',
        'ordering': ['-created_at'],
        'strict': False,  # Allow extra fields for backward compatibility
        'allow_inheritance': False
    }

# -----------------------------
# Generated Images Model
# -----------------------------


class GeneratedImage(Document):
    collection = ReferenceField(
        Collection, required=True, reverse_delete_rule=2)
    image_path = StringField(required=True)  # store local path or URL
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.now(timezone.utc))
    updated_at = DateTimeField(default=datetime.now(timezone.utc))

    def __str__(self):
        return f"Image for {self.collection.project.name} Collection"

    meta = {
        'collection': 'generated_images',
        'ordering': ['-created_at'],
        'strict': False,  # Allow extra fields for backward compatibility
        'allow_inheritance': False
    }


# New model for tracking all image generation activities
class ImageGenerationHistory(Document):
    """Track all image generation activities across the system"""
    # Reference to the project (if applicable)
    project = ReferenceField(Project, reverse_delete_rule=2)
    # Reference to the collection (if applicable)
    collection = ReferenceField(Collection, reverse_delete_rule=2)

    # Image details
    # 'white_background', 'model_with_ornament', 'regenerated', etc.
    image_type = StringField(required=True)
    image_url = URLField(required=True)
    local_path = StringField()

    # Generation details
    prompt = StringField()
    original_prompt = StringField()  # For regenerated images
    parent_image_id = StringField()  # For regenerated images

    # User who generated the image
    user_id = StringField(required=True)

    # User references
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")

    # Timestamps
    created_at = DateTimeField(default=datetime.now(timezone.utc))
    updated_at = DateTimeField(default=datetime.now(timezone.utc))

    # Additional metadata
    # Store any additional info like model type, settings, etc.
    metadata = DictField()

    def __str__(self):
        return f"{self.image_type} image for {self.project.name if self.project else 'Unknown Project'}"

    meta = {
        'collection': 'image_generation_history',
        'ordering': ['-created_at'],
        'strict': False,  # Allow extra fields for backward compatibility
        'allow_inheritance': False,
        # Note: Unique compound index is created via ensure_unique_index() method
        # This ensures only ONE worker can process the same image generation task
        # The index is created automatically on app startup or via management command
    }
    
    @classmethod
    def ensure_unique_index(cls):
        """
        Ensure the unique compound index exists. Call this after model definition
        or during application startup to create the index if it doesn't exist.
        This prevents duplicate image generation when using multiple Celery workers.
        """
        from mongoengine import connection
        try:
            db = connection.get_db()
            collection_name = cls._get_collection_name()
            collection = db[collection_name]
            
            # Check if index already exists
            existing_indexes = collection.index_information()
            index_name = 'unique_job_product_prompt'
            
            if index_name in existing_indexes:
                # Index already exists, verify it's unique
                index_info = existing_indexes[index_name]
                if index_info.get('unique'):
                    return  # Index is correct, no need to recreate
            
            # Create unique compound index
            collection.create_index(
                [
                    ('metadata.job_id', 1),
                    ('metadata.product_index', 1),
                    ('metadata.prompt_key', 1)
                ],
                unique=True,
                sparse=True,  # Only index documents that have these fields
                name=index_name,
                background=True  # Create in background to avoid blocking
            )
            print(f"✅ Created unique index '{index_name}' on {collection_name}")
        except Exception as e:
            # Index might already exist, which is fine
            error_str = str(e).lower()
            if 'already exists' not in error_str and 'duplicate' not in error_str and 'e11000' not in error_str:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Could not create unique index for ImageGenerationHistory: {e}")


class ProjectInvite(Document):
    project = ReferenceField(Project, required=True, reverse_delete_rule=2)
    inviter = ReferenceField(User, required=True)  # who sent the invite
    invitee = ReferenceField(User, required=True)  # who is being invited
    role = StringField(choices=["owner", "editor", "viewer"], default="viewer")
    accepted = BooleanField(default=False)
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.now(timezone.utc))
    updated_at = DateTimeField(default=datetime.now(timezone.utc))

    meta = {
        'collection': 'project_invites',
        'ordering': ['-created_at'],
        'strict': False,  # Allow extra fields for backward compatibility
        'allow_inheritance': False
    }

    def __str__(self):
        return f"Invite to {self.invitee.email} for {self.project.name}"


# -----------------------------
# Prompt Master Model
# -----------------------------
class PromptMaster(Document):
    """Model to store and manage all prompts used in the system"""
    # Prompt identifier/name (e.g., 'suggestion_prompt', 'white_background_template', etc.)
    prompt_key = StringField(required=True, unique=True)

    # Prompt title/description for UI
    title = StringField(required=True)
    description = StringField()

    # The actual prompt content
    prompt_content = StringField(required=True)

    # Instructions for prompt creation (editable by users)
    instructions = StringField()

    # Rules for prompt creation (editable by users)
    rules = StringField()

    # Prompt category/type (e.g., 'suggestion', 'template', 'generation')
    category = StringField(required=True)

    # Prompt type for templates (e.g., 'white_background', 'background_replace', 'model_image', 'campaign_image')
    prompt_type = StringField()

    # Whether this prompt is currently active
    is_active = BooleanField(default=True)

    # User who created/modified this prompt
    created_by = ReferenceField(User)
    updated_by = ReferenceField(User)

    # Timestamps
    created_at = DateTimeField(default=datetime.now(timezone.utc))
    updated_at = DateTimeField(default=datetime.now(timezone.utc))

    # Additional metadata
    metadata = DictField()

    def __str__(self):
        return f"{self.title} ({self.prompt_key})"

    meta = {
        'collection': 'prompt_master',
        'ordering': ['category', 'prompt_key'],
        'indexes': ['prompt_key', 'category', 'is_active'],
        'strict': False,  # Allow extra fields for backward compatibility
        'allow_inheritance': False
    }


