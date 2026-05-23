"""
URL configuration for legal app
"""
from django.urls import path
from . import views

urlpatterns = [
    # Admin-only: Get all legal content
    path('', views.get_all_legal_content, name='get_all_legal_content'),
    
    # Admin-only: Update specific content type
    path('<str:content_type>/update/', views.update_legal_content, name='update_legal_content'),
    
    # Public: Get specific content type (for frontend display)
    path('<str:content_type>/', views.get_legal_content, name='get_legal_content'),
]
