# imgbackendapp/models.py
from django.db import models


class Ornament(models.Model):
    image = models.ImageField(upload_to='uploads/')
    prompt = models.CharField(
        max_length=255, blank=True, null=True)  # ✅ allow blank
    generated_image = models.ImageField(
        upload_to='generated/', null=True, blank=True)
    # Store User ID as string since User is a MongoEngine model

    def __str__(self):
        return f'Ornament {self.id}'
