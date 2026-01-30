"""
URL configuration for payments app
"""
from django.urls import path
from . import views

urlpatterns = [
    path('razorpay/create-order/', views.create_razorpay_order, name='create_razorpay_order'),
    path('razorpay/verify/', views.verify_razorpay_payment, name='verify_razorpay_payment'),
    path('history/', views.get_payment_history, name='get_payment_history'),
    path('admin/all/', views.get_all_payments, name='get_all_payments'),
    path('admin/revenue/', views.get_revenue_stats, name='get_revenue_stats'),
    path('contact-sales/', views.submit_contact_sales, name='submit_contact_sales'),
]
