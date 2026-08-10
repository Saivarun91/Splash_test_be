"""
URL configuration for sitemap JSON APIs consumed by the Next.js frontend.
"""
from django.urls import path

from . import sitemap_views

urlpatterns = [
    path("blog", sitemap_views.sitemap_blog, name="sitemap_blog"),
    path("blog/", sitemap_views.sitemap_blog, name="sitemap_blog_slash"),
]
