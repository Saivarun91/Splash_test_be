from celery import shared_task
# from probackendapp.models import ImageGenerationJob

from .views import (
    generate_single_product_model_image_background,
    generate_ai_images_background,
)

from mongoengine.errors import NotUniqueError, OperationError, ValidationError
from datetime import datetime
from .models import ImageGenerationHistory
from common.error_reporter import report_handled_exception

@shared_task(bind=True, acks_late=True)
def generate_single_image_task(self, job_id, collection_id, user_id, product_index, prompt_key):
    """
    Generate a single image with atomic lock acquisition to prevent duplicates.
    
    Uses a unique compound index on (job_id, product_index, prompt_key) to ensure
    only ONE worker can acquire the lock, preventing duplicate image generation
    and duplicate credit deductions.
    """
    try:
        # 🔒 ATOMIC LOCK ACQUISITION using unique index
        # Try to create the lock - only ONE worker will succeed due to unique index
        # Use placeholder URL and bypass validation for lock records (just a locking mechanism)
        lock_record = ImageGenerationHistory(
            collection=collection_id,
            image_type="pending",
            image_url="http://lock-pending",  # Placeholder - validation bypassed for lock records
            user_id=str(user_id),
            metadata={
                "job_id": job_id,
                "product_index": product_index,
                "prompt_key": prompt_key,
                "status": "started",
            },
            created_at=datetime.utcnow(),
        )
        # Bypass validation for lock records - we only need the unique index constraint
        lock_record.save(validate=False)
        
        # 🔐 Lock acquired successfully - this worker won the race
        # 🚀 generate exactly once
        return generate_single_product_model_image_background(
            collection_id=collection_id,
            user_id=user_id,
            product_index=product_index,
            prompt_key=prompt_key,
            job_id=job_id,
        )
        
    except (NotUniqueError, OperationError) as e:
        # Unique constraint violation - another worker already acquired the lock
        # This is expected behavior in a multi-worker setup
        error_str = str(e).lower()
        if 'duplicate' in error_str or 'e11000' in error_str or 'unique' in error_str:
            return "duplicate-blocked"
        # Re-raise if it's a different operation error
        raise
    except ValidationError as e:
        # If validation fails (e.g., URL format), check if it's a duplicate scenario
        # This shouldn't happen with valid URL, but handle gracefully
        error_str = str(e).lower()
        if 'duplicate' in error_str or 'e11000' in error_str or 'unique' in error_str:
            return "duplicate-blocked"
        # Re-raise validation errors so we can see what's wrong
        raise
    except Exception as e:
        # Check for MongoDB duplicate key error codes
        error_str = str(e).lower()
        if 'duplicate' in error_str or 'e11000' in error_str:
            return "duplicate-blocked"
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        raise


@shared_task(bind=True)
def generate_ai_images_task(self, collection_id, user_id):
    """
    Legacy bulk task – should NOT be used for paid flows.
    """
    try:
        return generate_ai_images_background(collection_id, user_id)
    except Exception as e:
        report_handled_exception(e, request=self.request, context={"user_id": user_id})
        raise
