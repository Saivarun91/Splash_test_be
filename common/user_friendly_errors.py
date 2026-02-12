"""
Maps technical error messages to user-friendly messages for the frontend.
Used by imgbackendapp (individual model generation) and probackendapp (project batch generation).
"""

# Substrings in exception/error messages (lowercase) -> user-friendly message
IMAGE_GENERATION_ERROR_MAP = [
    # API / configuration
    ("GOOGLE_API_KEY not configured", "Image generation service is not configured. Please contact support."),
    ("Gemini SDK not available", "Image generation service is temporarily unavailable. Please try again later."),
    ("api_key", "Image generation service configuration error. Please try again later."),
    # Rate limits / quota
    ("quota", "We've reached our generation limit for now. Please try again in a few minutes."),
    ("rate limit", "Too many requests. Please wait a moment and try again."),
    ("429", "Service is busy. Please wait a moment and try again."),
    # Invalid input / content
    ("No image returned", "We couldn't create an image from your photos. Please try different images."),
    ("invalid", "Something about the image or request wasn't valid. Please check your uploads and try again."),
    ("Invalid image_id", "The image reference was invalid. Please refresh and try again."),
    ("Image record not found", "That image could not be found. It may have been deleted."),
    ("permission to regenerate", "You don't have permission to change this image."),
    ("ObjectId", "Invalid image reference. Please use the correct image and try again."),
    # Files / upload
    ("file", "There was a problem with the uploaded file. Please check format and size, then try again."),
    ("upload", "Upload failed. Please check your connection and try again."),
    ("Could not access product image", "We couldn't use one of the product images. Please check uploads and try again."),
    ("Product image path or URL not found", "A product image is missing. Please re-upload and try again."),
    ("path does not exist", "A required file could not be found. Please re-upload and try again."),
    # Network / external services
    ("connection", "Connection problem. Please check your internet and try again."),
    ("timeout", "The request took too long. Please try again."),
    ("network", "Network error. Please check your connection and try again."),
    # Credits
    ("insufficient credits", "You don't have enough credits. Please add credits to continue."),
    ("credits", "There was a problem with your credits. Please check your account and try again."),
    # Job / batch
    ("Job timed out", "Generation took too long and was cancelled. Please try again with fewer images."),
    ("Cancelled: New batch started", "A new generation was started, so the previous one was cancelled."),
    ("Too many active", "You have too many generations in progress. Please wait for some to finish."),
    ("No items found in collection", "No products in this collection. Please add products first."),
    ("No image types selected", "Please select at least one image type to generate."),
    ("Collection items not found", "Collection data could not be loaded. Please refresh and try again."),
    # Generic
    ("Task failed", "Something went wrong while generating. Please try again."),
    ("fallback method", "We couldn't process the image with the chosen method. Please try a different image."),
]


def get_user_friendly_message(technical_error, context="image_generation"):
    """
    Convert a technical error (Exception or string) to a user-friendly message.

    :param technical_error: Exception instance or str
    :param context: Optional context (e.g. "image_generation", "regeneration", "project_batch")
    :return: User-friendly string
    """
    if technical_error is None:
        return "Something went wrong. Please try again."

    raw = str(technical_error).strip()
    if not raw:
        return "Something went wrong. Please try again."

    raw_lower = raw.lower()
    for substring, friendly in IMAGE_GENERATION_ERROR_MAP:
        if substring.lower() in raw_lower:
            return friendly

    # Default: avoid exposing stack traces or internal paths
    if len(raw) > 200 or "traceback" in raw_lower or "file \"" in raw_lower:
        return "Something went wrong on our side. Please try again in a few moments."

    # If it looks like a short, safe message, we can return a generic wrap
    return "Something went wrong while generating. Please try again."
