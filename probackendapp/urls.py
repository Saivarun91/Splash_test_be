

from django.urls import path
from . import views, api_views, api_views_extended

app_name = "probackendapp"

urlpatterns = [
    # Original Django views
    #     path("", views.dashboard, name="dashboard"),
    #     path("create/", views.create_project, name="create_project"),
    #     path("setup/<str:project_id>/description/",
    #          views.project_setup_description, name="project_setup_description"),
    #     path("setup/<str:project_id>/<str:collection_id>/select/",
    #          views.project_setup_select, name="project_setup_select"),
    #     path("collection/<str:project_id>/<str:collection_id>/",
    #          views.collection_detail, name="collection_detail"),
    #     path('generate-images/<str:collection_id>/',
    #          views.generate_ai_images_page, name='generate_ai_images_page'),
    #     path('generate-images-api/<str:collection_id>/',
    #          views.generate_ai_images, name='generate_ai_images'),
    #     path('save-generated-images/<str:collection_id>/',
    #          views.save_generated_images, name='save_generated_images'),
    #     path('upload-products/<str:collection_id>/',
    #          views.upload_product_images_page, name='upload_product_images_page'),
    #     path('upload-products-api/<str:collection_id>/',
    #          views.upload_product_images_api, name='upload_product_images_api'),
    #     path(
    #         "generate-product-model/<str:collection_id>/",
    #         views.generate_product_model_page,
    #         name="generate_product_model_page"
    #     ),
    #     path(
    #         "generate-product-model-api/<str:collection_id>/",
    #         views.generate_product_model_api,
    #         name="generate_product_model_api"
    #     ),
    #     path(
    #         'generate-all-product-model-images/<str:collection_id>/',
    #         views.generate_all_product_model_images,
    #         name='generate_all_product_model_images'
    #     ),
    #     path(
    #         "regenerate/<str:collection_id>/",
    #         views.regenerate_product_model_image,
    #         name="regenerate_product_model_image"
    #     ),

    path("api/projects/create/", api_views.api_create_project,
         name="api_create_project"),
    # API endpoints for frontend
    path("api/projects/", api_views.api_projects_list, name="api_projects_list"),
    path("api/projects/<str:project_id>/",
         api_views.api_project_detail, name="api_project_detail"),
    path("api/projects/<str:project_id>/update/",
         api_views.api_update_project, name="api_update_project"),
    path("api/projects/<str:project_id>/delete/",
         api_views.api_delete_project, name="api_delete_project"),

    path("api/collections/<str:collection_id>/",
         api_views.api_collection_detail, name="api_collection_detail"),

    path("api/projects/<str:project_id>/setup/description/",
         api_views.api_project_setup_description, name="api_project_setup_description"),
    path("api/projects/<str:project_id>/collections/<str:collection_id>/select/",
         api_views.api_project_setup_select, name="api_project_setup_select"),
    path("api/projects/<str:project_id>/collections/<str:collection_id>/upload-workflow-image/",
         api_views.api_upload_workflow_image, name="api_upload_workflow_image"),
    path("api/projects/<str:project_id>/collections/<str:collection_id>/remove-workflow-image/",
         api_views.api_remove_workflow_image, name="api_remove_workflow_image"),

    path("api/collections/<str:collection_id>/generate-images/",
         api_views.api_generate_ai_images, name="api_generate_ai_images"),
    path("api/collections/<str:collection_id>/save-images/",
         api_views.api_save_generated_images, name="api_save_generated_images"),
    path("api/collections/<str:collection_id>/upload-products/",
         api_views.api_upload_product_images, name="api_upload_product_images"),
    path("api/collections/<str:collection_id>/products/",
         api_views.api_remove_product_image, name="api_remove_product_image"),
    path("api/collections/<str:collection_id>/products/generation-selections/",
         api_views.api_update_product_generation_selections, name="api_update_product_generation_selections"),
    path("api/collections/<str:collection_id>/generate-all-product-model-images/",
         api_views.api_generate_all_product_model_images, name="api_generate_all_product_model_images"),
    path("api/collections/<str:collection_id>/images-status/",
         api_views.api_collection_images_status, name="api_collection_images_status"),
    path("api/task-status/<str:task_id>/",
         api_views.get_task_status, name="get_task_status"),
    path("api/jobs/<str:job_id>/images/",
         api_views.api_job_images, name="api_job_images"),
    path("api/collections/<str:collection_id>/regenerate/",
         api_views.api_regenerate_product_model_image, name="api_regenerate_product_model_image"),

    # Model management endpoints
    path("api/collections/<str:collection_id>/upload-real-models/",
         api_views.api_upload_real_models, name="api_upload_real_models"),
    path("api/collections/<str:collection_id>/get-all-models/",
         api_views.api_get_all_models, name="api_get_all_models"),
    path("api/collections/<str:collection_id>/select-model/",
         api_views.api_select_model, name="api_select_model"),
    path("api/collections/<str:collection_id>/models/",
         api_views.api_remove_model, name="api_remove_model"),
    path('api/<str:project_id>/invite',
         api_views.api_invite_member, name='api_invite_member'),
    path('api/<str:project_id>/accept-invite',
         api_views.api_accept_invite, name='api_accept_invite'),
    path('api/<str:project_id>/invites',
         api_views.api_list_invites, name='api_list_invites'),
    path('api/<str:project_id>/available-users',
         api_views.api_available_users, name='api_available_users'),
    path('api/<str:project_id>/update-member-role',
         api_views.api_update_member_role, name='api_update_member_role'),
    # Global invite endpoints (not project-specific)
    path('api/invites/all',
         api_views.api_list_all_invites, name='api_list_all_invites'),
    path('api/invites/<str:invite_id>/accept',
         api_views.api_accept_invite_by_id, name='api_accept_invite_by_id'),
    path('api/invites/<str:invite_id>/reject',
         api_views.api_reject_invite, name='api_reject_invite'),
    path("api/image/enhance/", api_views.api_image_enhance,
         name="api_image_enhance"),

    # Extended API endpoints
    path('api/collections/<str:collection_id>/model-usage-stats/',
         api_views_extended.api_get_model_usage_stats, name='api_get_model_usage_stats'),
    path('api/projects/<str:project_id>/user-role/',
         api_views_extended.api_get_user_role, name='api_get_user_role'),

    # Recent History API endpoints
    path('api/recent/history/',
         api_views.api_recent_history, name='api_recent_history'),
    path('api/recent/images/',
         api_views.api_recent_images, name='api_recent_images'),
    path('api/recent/projects/',
         api_views.api_recent_projects, name='api_recent_projects'),
    path('api/recent/project-history/',
         api_views.api_recent_project_history, name='api_recent_project_history'),
    path('api/collections/<str:collection_id>/history/',
         api_views.api_collection_history, name='api_collection_history'),

    # Prompt Master API endpoints
    path('api/prompts/', api_views.api_prompt_master_list,
         name='api_prompt_master_list'),
    path('api/prompts/create/', api_views.api_prompt_master_create,
         name='api_prompt_master_create'),
    path('api/prompts/initialize/', api_views.api_prompt_master_initialize,
         name='api_prompt_master_initialize'),
    path('api/prompts/<str:prompt_id>/',
         api_views.api_prompt_master_detail, name='api_prompt_master_detail'),
    path('api/prompts/<str:prompt_id>/update/',
         api_views.api_prompt_master_update, name='api_prompt_master_update'),
    path('api/prompts/<str:prompt_id>/delete/',
         api_views.api_prompt_master_delete, name='api_prompt_master_delete'),
    path('api/prompts/key/<str:prompt_key>/',
         api_views.api_prompt_master_get_by_key, name='api_prompt_master_get_by_key'),
]
