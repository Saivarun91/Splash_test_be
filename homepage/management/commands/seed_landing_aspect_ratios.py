from django.core.management.base import BaseCommand

from homepage.landing_seed import ensure_aspect_ratios


class Command(BaseCommand):
    help = "Seed the predefined landing-page aspect-ratio library."

    def handle(self, *args, **options):
        created = ensure_aspect_ratios()
        self.stdout.write(self.style.SUCCESS(f"Aspect ratios ready ({created} created)."))
