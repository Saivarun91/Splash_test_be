from django.apps import AppConfig


class HomepageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'homepage'

    def ready(self):
        from . import landing_models  # noqa: F401 — register MongoEngine documents
