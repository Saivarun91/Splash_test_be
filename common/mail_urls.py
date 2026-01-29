from django.urls import path
from . import mail_views

urlpatterns = [
    path("", mail_views.mail_template_list),
    path("<str:slug>/", mail_views.mail_template_detail),
]
