from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from organization import admin_views

urlpatterns = [
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
    # Admin dashboard endpoints
    path('api/admin/dashboard/stats', admin_views.admin_dashboard_stats, name='admin_dashboard_stats'),
    path('api/admin/dashboard/images', admin_views.admin_dashboard_images, name='admin_dashboard_images'),
    path('api/admin/dashboard/all-charts', admin_views.admin_dashboard_all_charts, name='admin_dashboard_all_charts'),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
