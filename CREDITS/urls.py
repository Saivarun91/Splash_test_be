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
    
    # Individual user credit usage
    path('user/usage/', views.user_credit_usage, name='user_credit_usage'),
    
    # Credits usage statistics for charts (admin only)
    path('admin/usage-statistics/', views.credits_usage_statistics, name='credits_usage_statistics'),
    
    # Credit settings (public read-only)
    path('settings/', views.get_credit_settings_public, name='get_credit_settings_public'),
    
    # Credit settings (admin only)
    path('admin/settings/', views.get_credit_settings, name='get_credit_settings'),
    path('admin/settings/update/', views.update_credit_settings, name='update_credit_settings'),
]


