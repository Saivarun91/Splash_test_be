"""
URL configuration for homepage app
"""
from django.urls import path
from . import views

urlpatterns = [
    # Public: Get all active before/after images (for frontend display)
    path('before-after/', views.get_before_after_images, name='get_before_after_images'),
    
    # Admin-only: Get all before/after images (including inactive)
    path('before-after/all/', views.get_all_before_after_images, name='get_all_before_after_images'),
    
    # Admin-only: Upload before/after images
    path('before-after/upload/', views.upload_before_after_images, name='upload_before_after_images'),
    
    # Admin-only: Update before/after image
    path('before-after/<str:image_id>/update/', views.update_before_after_image, name='update_before_after_image'),
    
    # Admin-only: Delete before/after image
    path('before-after/<str:image_id>/delete/', views.delete_before_after_image, name='delete_before_after_image'),
    
    # Public: Submit contact form
    path('contact/', views.submit_contact_form, name='submit_contact_form'),
    
    # Authenticated: Submit help/support request
    path('help/submit/', views.submit_support_request, name='submit_support_request'),
    
    # Admin-only: Get all support/contact requests
    path('support/all/', views.get_all_support_requests, name='get_all_support_requests'),
]
