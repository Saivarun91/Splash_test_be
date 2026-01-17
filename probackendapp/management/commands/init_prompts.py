"""
Django management command to initialize default prompts in the database.
Run with: python manage.py init_prompts
"""
from django.core.management.base import BaseCommand
from probackendapp.prompt_initializer import initialize_default_prompts


class Command(BaseCommand):
    help = 'Initialize default prompts in the database'

    def handle(self, *args, **options):
        self.stdout.write('Initializing default prompts...')
        created, updated = initialize_default_prompts()
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully initialized prompts! Created: {created}, Already existed: {updated}'
            )
        )

