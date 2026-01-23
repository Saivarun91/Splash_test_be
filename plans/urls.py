"""
URL configuration for plans app
"""
from django.urls import path
from . import views

urlpatterns = [
    # Public endpoints
    path('', views.list_plans, name='list_plans'),
    
    # Admin-only endpoints - must come before <str:plan_id>/ to avoid conflicts
    path('create/', views.create_plan, name='create_plan'),
    
    # Public endpoint - must come after create/ to avoid matching "create" as plan_id
    path('<str:plan_id>/', views.get_plan, name='get_plan'),
    
    # Admin-only endpoints
    path('<str:plan_id>/update/', views.update_plan, name='update_plan'),
    path('<str:plan_id>/delete/', views.delete_plan, name='delete_plan'),
]

