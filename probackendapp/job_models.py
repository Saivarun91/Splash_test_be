from datetime import datetime

from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    IntField,
    DictField,
    ListField,
    ReferenceField,
)

from users.models import User
from .models import Project, Collection


class ImageGenerationJob(Document):
    """
    Tracks a bulk image generation job so that individual image
    tasks can update progress independently and clients can poll.
    """

    job_id = StringField(required=True, unique=True)

    # Who requested this job (tenant/user)
    user = ReferenceField(User)

    # Optional context
    project = ReferenceField(Project)
    collection = ReferenceField(Collection)

    total_images = IntField(default=0)
    completed_images = IntField(default=0)

    # Status for simple job lifecycle tracking
    status = StringField(
        choices=["pending", "running", "completed", "failed"],
        default="pending",
    )
    error = StringField()

    # List of generated images so far (progressive results)
    # Each entry is a small dict with URLs and minimal metadata.
    images = ListField(DictField(), default=list)

    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "image_generation_jobs",
        "ordering": ["-created_at"],
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)




