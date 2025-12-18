from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register_user, name="register_user"),
    path("login/", views.login_user, name="login_user"),
    path("invite/", views.invite_user, name="invite_user"),
    path("profile/", views.get_user_profile, name="get_user_profile"),
    path("profile/update/", views.update_user_profile, name="update_user_profile"),
]
