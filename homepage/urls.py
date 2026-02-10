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
    
    # Page content (CMS): home, about, vision_mission, tutorials, security
    path('content/<str:slug>/', views.get_page_content, name='get_page_content'),
    path('content/<str:slug>/admin/', views.get_page_content_admin, name='get_page_content_admin'),
    path('content/<str:slug>/admin/update/', views.update_page_content, name='update_page_content'),
    
    # Blog (admin - must be before blog/<slug>)
    path('blog/admin/all/', views.get_all_blog_posts, name='get_all_blog_posts'),
    path('blog/admin/create/', views.create_blog_post, name='create_blog_post'),
    path('blog/admin/<str:slug>/update/', views.update_blog_post, name='update_blog_post'),
    path('blog/admin/<str:slug>/delete/', views.delete_blog_post, name='delete_blog_post'),
    # Blog (public)
    path('blog/', views.get_blog_posts, name='get_blog_posts'),
    path('blog/<str:slug>/', views.get_blog_post, name='get_blog_post'),
    
    # Admin: Upload content image (hero, showcase, etc.)
    path('upload-image/', views.upload_content_image, name='upload_content_image'),
]
