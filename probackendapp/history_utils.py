"""
Utility functions for tracking image generation history
"""
from .models import ImageGenerationHistory, Project, Collection
from datetime import datetime, timezone


def track_image_generation(
    user_id,
    image_type,
    image_url,
    prompt=None,
    original_prompt=None,
    parent_image_id=None,
    project_id=None,
    collection_id=None,
    local_path=None,
    metadata=None
):
    """
    Track an image generation event in the history

    Args:
        user_id (str): ID of the user who generated the image
        image_type (str): Type of image generation (e.g., 'white_background', 'model_with_ornament')
        image_url (str): URL of the generated image
        prompt (str, optional): The prompt used for generation
        original_prompt (str, optional): Original prompt for regenerated images
        parent_image_id (str, optional): ID of parent image for regenerations
        project_id (str, optional): ID of the project (if applicable)
        collection_id (str, optional): ID of the collection (if applicable)
        local_path (str, optional): Local path to the image file
        metadata (dict, optional): Additional metadata about the generation

    Returns:
        ImageGenerationHistory: The created history record
    """
    try:
        # Get project and collection references if IDs are provided
        project = None
        collection = None

        if project_id:
            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                pass

        if collection_id:
            try:
                collection = Collection.objects.get(id=collection_id)
            except Collection.DoesNotExist:
                pass

        # Create history record
        history_record = ImageGenerationHistory(
            user_id=user_id,
            image_type=image_type,
            image_url=image_url,
            prompt=prompt,
            original_prompt=original_prompt,
            parent_image_id=parent_image_id,
            project=project,
            collection=collection,
            local_path=local_path,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc)
        )

        history_record.save()
        return history_record

    except Exception as e:
        print(f"Error tracking image generation history: {str(e)}")
        # Don't raise the exception to avoid breaking the main flow
        return None


def track_project_image_generation(
    user_id,
    collection_id,
    image_type,
    image_url,
    prompt=None,
    local_path=None,
    metadata=None
):
    """
    Track image generation for project-based workflows

    Args:
        user_id (str): ID of the user who generated the image
        collection_id (str): ID of the collection
        image_type (str): Type of image generation
        image_url (str): URL of the generated image
        prompt (str, optional): The prompt used for generation
        local_path (str, optional): Local path to the image file
        metadata (dict, optional): Additional metadata

    Returns:
        ImageGenerationHistory: The created history record
    """
    try:
        collection = Collection.objects.get(id=collection_id)
        project = collection.project

        return track_image_generation(
            user_id=user_id,
            image_type=image_type,
            image_url=image_url,
            prompt=prompt,
            project_id=str(project.id),
            collection_id=str(collection.id),
            local_path=local_path,
            metadata=metadata
        )

    except Collection.DoesNotExist:
        print(f"Collection {collection_id} not found for history tracking")
        return None
    except Exception as e:
        print(f"Error tracking project image generation: {str(e)}")
        return None


def track_image_regeneration(
    user_id,
    original_image_id,
    new_image_url,
    new_prompt,
    original_prompt,
    image_type,
    project_id=None,
    collection_id=None,
    local_path=None,
    metadata=None
):
    """
    Track image regeneration events

    Args:
        user_id (str): ID of the user who regenerated the image
        original_image_id (str): ID of the original image
        new_image_url (str): URL of the regenerated image
        new_prompt (str): The new prompt used for regeneration
        original_prompt (str): The original prompt
        image_type (str): Type of image generation
        project_id (str, optional): ID of the project (if applicable)
        collection_id (str, optional): ID of the collection (if applicable)
        local_path (str, optional): Local path to the image file
        metadata (dict, optional): Additional metadata

    Returns:
        ImageGenerationHistory: The created history record
    """
    return track_image_generation(
        user_id=user_id,
        image_type=f"{image_type}_regenerated",
        image_url=new_image_url,
        prompt=new_prompt,
        original_prompt=original_prompt,
        parent_image_id=original_image_id,
        project_id=project_id,
        collection_id=collection_id,
        local_path=local_path,
        metadata=metadata
    )


def get_user_recent_activity(user_id, days=30, limit=50):
    """
    Get recent activity for a user

    Args:
        user_id (str): ID of the user
        days (int): Number of days to look back
        limit (int): Maximum number of records to return

    Returns:
        list: List of recent activity records
    """
    try:
        from datetime import timedelta
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        return ImageGenerationHistory.objects(
            user_id=user_id,
            created_at__gte=start_date,
            created_at__lte=end_date
        ).order_by('-created_at').limit(limit)

    except Exception as e:
        print(f"Error getting user recent activity: {str(e)}")
        return []


def get_project_recent_activity(project_id, days=30, limit=20):
    """
    Get recent activity for a project

    Args:
        project_id (str): ID of the project
        days (int): Number of days to look back
        limit (int): Maximum number of records to return

    Returns:
        list: List of recent activity records
    """
    try:
        from datetime import timedelta
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        return ImageGenerationHistory.objects(
            project=project_id,
            created_at__gte=start_date,
            created_at__lte=end_date
        ).order_by('-created_at').limit(limit)

    except Exception as e:
        print(f"Error getting project recent activity: {str(e)}")
        return []
