from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # replace 'myapp' with your app name
    path('image/', include('imgbackendapp.urls'), name='upload_ornament'),
    # replace 'myapp' with your app name
    path("probackendapp/", include("probackendapp.urls", namespace="probackendapp")),
    path('api/', include('users.urls'), name='users'),

]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
