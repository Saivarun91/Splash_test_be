from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from organization import admin_views
from homepage import blog_admin_views

urlpatterns = [
    # Blog admin APIs (must be registered before Django's /admin/ site)
    path('admin/blog/listing', blog_admin_views.blog_listing, name='admin_blog_listing'),
    path('admin/blog/add', blog_admin_views.blog_add, name='admin_blog_add'),
    path('admin/blog/details/<int:blog_id>', blog_admin_views.blog_details, name='admin_blog_details'),
    path('admin/blog/update/<int:blog_id>', blog_admin_views.blog_update, name='admin_blog_update'),
    path('admin/blog/delete/<int:blog_id>', blog_admin_views.blog_delete, name='admin_blog_delete'),
    path('admin/blog/download/<int:blog_id>', blog_admin_views.blog_download, name='admin_blog_download'),
    path('admin/', admin.site.urls),
    # replace 'myapp' with your app name
    path('image/', include('imgbackendapp.urls'), name='upload_ornament'),
    # replace 'myapp' with your app name
    path("probackendapp/", include("probackendapp.urls", namespace="probackendapp")),
    path('api/', include('users.urls'), name='users'),
    # Organization management endpoints
    path('api/organizations/', include('organization.urls'), name='organizations'),
    # Credit management endpoints
    path('api/credits/', include('CREDITS.urls'), name='credits'),
    # Payment endpoints
    path('api/payments/', include('payments.urls'), name='payments'),
    # Invoice / GST configuration endpoints
    path('api/invoices/', include('invoices.urls'), name='invoices'),
    # Plans endpoints
    path('api/plans/', include('plans.urls'), name='plans'),
    # Legal compliance endpoints
    path('api/legal/', include('legal.urls'), name='legal'),
    # Homepage content endpoints
    path('api/homepage/', include('homepage.urls'), name='homepage'),
    # Sitemap JSON APIs (paginated) for Next.js /sitemap/*
    path('api/sitemap/', include('homepage.sitemap_urls'), name='sitemap'),
    # Admin dashboard endpoints
    path('api/admin/dashboard/stats', admin_views.admin_dashboard_stats, name='admin_dashboard_stats'),
    path('api/admin/dashboard/images', admin_views.admin_dashboard_images, name='admin_dashboard_images'),
    path('api/admin/dashboard/all-charts', admin_views.admin_dashboard_all_charts, name='admin_dashboard_all_charts'),
    # Mail templates (admin only)
    path('api/mail-templates/', include('common.mail_urls')),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
