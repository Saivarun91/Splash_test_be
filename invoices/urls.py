from django.urls import path

from . import views

urlpatterns = [
    # GET and PUT handled by the same view
    path("config/", views.invoice_config, name="invoice_config"),
    
]


