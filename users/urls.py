from django.urls import path
from . import views

urlpatterns = [
    path("token/", views.token_obtain_pair, name="token_obtain_pair"),
    path("token/refresh/", views.token_refresh, name="token_refresh"),
    path("register/", views.register_user, name="register_user"),
    path("login/", views.login_user, name="login_user"),
    path("verify-email-otp/", views.verify_email_otp, name="verify_email_otp"),
    path("resend-email-otp/", views.resend_email_otp, name="resend_email_otp"),
    path("invite/", views.invite_user, name="invite_user"),
    path("profile/", views.get_user_profile, name="get_user_profile"),
    path("profile/update/", views.update_user_profile, name="update_user_profile"),
    path("profile/complete/", views.complete_profile, name="complete_profile"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/", views.reset_password, name="reset_password"),
]
