"""
Django management command to ensure MongoDB indexes are created.
Run with: python manage.py ensure_indexes
"""
from django.core.management.base import BaseCommand
from probackendapp.models import ImageGenerationHistory


class Command(BaseCommand):
    help = 'Ensure MongoDB indexes are created (especially unique index for duplicate prevention)'

    def handle(self, *args, **options):
        self.stdout.write('Ensuring MongoDB indexes...')
        
        try:
            ImageGenerationHistory.ensure_unique_index()
            self.stdout.write(
                self.style.SUCCESS('✅ Successfully ensured ImageGenerationHistory unique index!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Warning: {e}')
            )
