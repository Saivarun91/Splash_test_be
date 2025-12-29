from celery import shared_task

from .views import (
    generate_single_product_model_image_background,
    generate_ai_images_background,
)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def generate_single_image_task(self, job_id, collection_id, user_id, product_index, prompt_key):
    """
    Celery task that generates exactly ONE image for a single product/prompt
    combination. All bulk jobs should dispatch many of these tasks in a group.
    """
    return generate_single_product_model_image_background(
        collection_id=collection_id,
        user_id=user_id,
        product_index=product_index,
        prompt_key=prompt_key,
        job_id=job_id,
    )


@shared_task
def generate_ai_images_task(collection_id, user_id):
    return generate_ai_images_background(collection_id, user_id)
