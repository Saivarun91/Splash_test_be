from django.urls import path
from . import views, admin_views

urlpatterns = [
    path("token/", views.token_obtain_pair, name="token_obtain_pair"),
    path("token/refresh/", views.token_refresh, name="token_refresh"),
    path("register/", views.register_user, name="register_user"),
    path("login/", views.login_user, name="login_user"),
    path("verify-email-otp/", views.verify_email_otp, name="verify_email_otp"),
    path("verify-phone-otp/", views.verify_phone_otp, name="verify_phone_otp"),
    path("verify-phone-access-token/", views.verify_phone_otp, name="verify_phone_access_token"),
    path("resend-email-otp/", views.resend_email_otp, name="resend_email_otp"),
    path("resend-phone-otp/", views.resend_phone_otp, name="resend_phone_otp"),
    path("complete-signup/", views.complete_signup, name="complete_signup"),
    path("auth/complete-phone-signup/", views.complete_phone_signup, name="complete_phone_signup"),
    path("signup-status/", views.signup_status, name="signup_status"),
    path("invite/", views.invite_user, name="invite_user"),
    path("profile/", views.get_user_profile, name="get_user_profile"),
    path("profile/update/", views.update_user_profile, name="update_user_profile"),
    path("profile/complete/", views.complete_profile, name="complete_profile"),
    path("profile/change-password/", views.change_password, name="change_password"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/", views.reset_password, name="reset_password"),
    # Admin: individual users (no organization)
    path("admin/individual/list/", admin_views.list_individual_users, name="list_individual_users"),
    path("admin/individual/<str:user_id>/", admin_views.get_individual_user, name="get_individual_user"),
    path("admin/individual/<str:user_id>/images/", admin_views.get_individual_user_images, name="get_individual_user_images"),
    path("admin/individual/<str:user_id>/add-credits/", admin_views.add_individual_user_credits, name="add_individual_user_credits"),
    path("admin/individual/<str:user_id>/remove-credits/", admin_views.remove_individual_user_credits, name="remove_individual_user_credits"),
]
