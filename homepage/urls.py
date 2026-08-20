"""
URL configuration for homepage app
"""
from django.urls import path
from . import views
from . import blog_admin_views
from . import landing_views

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
    
    # Public gallery CMS
    path('public-gallery/', views.get_public_gallery_images, name='get_public_gallery_images'),
    path('public-gallery/showcase/', views.get_homepage_showcase_images, name='get_homepage_showcase_images'),
    path('public-gallery/all/', views.get_all_public_gallery_images, name='get_all_public_gallery_images'),
    path('public-gallery/admin/overview/', views.get_public_gallery_admin_overview, name='get_public_gallery_admin_overview'),
    path('public-gallery/import/', views.import_public_gallery_images, name='import_public_gallery_images'),
    path('public-gallery/upload/', views.upload_public_gallery_image, name='upload_public_gallery_image'),
    path('public-gallery/<str:image_id>/update/', views.update_public_gallery_image, name='update_public_gallery_image'),
    path('public-gallery/<str:image_id>/delete/', views.delete_public_gallery_image, name='delete_public_gallery_image'),

    # Admin: Upload content image (hero, showcase, etc.)
    path('upload-image/', views.upload_content_image, name='upload_content_image'),

    # Public blogs (Published only)
    path('blog/', blog_admin_views.public_blog_list, name='public_blog_list'),
    path('blog/<slug:slug>/', blog_admin_views.public_blog_detail, name='public_blog_detail'),

    # Public landing pages
    path('landing-pages/nav/', landing_views.public_landing_nav, name='public_landing_nav'),
    path('landing-pages/<str:page_type>/', landing_views.public_landing_list, name='public_landing_list'),
    path(
        'landing-pages/<str:page_type>/<slug:slug>/',
        landing_views.public_landing_detail,
        name='public_landing_detail',
    ),
]
