from django.apps import AppConfig


class ProbackendappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'probackendapp'
    
    def ready(self):
        """Initialize app - ensure unique index exists for duplicate prevention"""
        try:
            from .models import ImageGenerationHistory
            ImageGenerationHistory.ensure_unique_index()
        except Exception as e:
            # Don't fail app startup if index creation fails
            # It will be created on first model access or via management command
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not ensure ImageGenerationHistory index: {e}")
