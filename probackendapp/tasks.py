from celery import shared_task
from .views import generate_all_product_model_images_background


@shared_task
def generate_images_task(collection_id, user_id):
    return generate_all_product_model_images_background(collection_id, user_id)
