"""
URL configuration for CREDITS app
"""
from django.urls import path
from . import views

urlpatterns = [
    # Organization credit usage (for organization members)
    path('organization/<str:organization_id>/usage/', views.organization_credit_usage, name='organization_credit_usage'),
    
    # Organization credit summary (quick stats)
    path('organization/<str:organization_id>/summary/', views.organization_credit_summary, name='organization_credit_summary'),
    
    # All organizations credit usage (admin only)
    path('all-organizations/usage/', views.all_organizations_credit_usage, name='all_organizations_credit_usage'),
]


