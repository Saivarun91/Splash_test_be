"""
URL configuration for organization app
"""
from django.urls import path
from . import views, admin_views

urlpatterns = [
    # Admin-only: Create organization
    
    path('create/', views.create_organization, name='create_organization'),
    # Admin-only: Add user to organization
    path('add-user/', views.add_user_to_organization, name='add_user_to_organization'),
    
    # List organizations (admin sees all, users see their own)
    path('list/', views.list_organizations, name='list_organizations'),
    
    # Get organization details
    path('<str:organization_id>/', views.get_organization, name='get_organization'),
    
    # Update organization (owner/admin only)
    path('<str:organization_id>/update/', views.update_organization, name='update_organization'),
    
    # Delete organization (admin only)
    path('<str:organization_id>/delete/', views.delete_organization, name='delete_organization'),
    
    # Admin-only: Add credits to organization
    path('<str:organization_id>/add-credits/', views.add_organization_credits, name='add_organization_credits'),
    
    # Admin-only: Remove credits from organization
    path('<str:organization_id>/remove-credits/', views.remove_organization_credits, name='remove_organization_credits'),
]


