from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_ornament, name='upload_ornament'),
    path('user-images/', views.get_user_images, name='get_user_images'),
    path('change_background/', views.change_background, name='change_background'),
    path('generate-model/', views.generate_model_with_ornament,
         name='generate_model_with_ornament'),
    path('generate-real-model/', views.generate_real_model_with_ornament,
         name='generate_real_model_with_ornament'),
    path('generate-campaign-shot/', views.generate_campaign_shot_advanced,
         name='generate_campaign_shot_advanced'),
    path('regenerate/', views.regenerate_image, name='regenerate_image'),
]


# imgbackendapp/urls.py
# from django.urls import path
# from . import views

# urlpatterns = [
#     path('', views.upload_ornament, name='upload_ornament'),
#     path('gallery/', views.ornament_gallery, name='ornament_gallery'),
#     path('image/<str:ornament_id>/', views.view_ornament_image,
#          name='view_ornament_image'),
#     path("gemini-black-bg/<str:ornament_id>/",
#          views.gemini_black_background, name="gemini_black_background"),
# ]
