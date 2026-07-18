import os
import requests
import json
import re
import hashlib
import base64
import mimetypes
from dotenv import load_dotenv
from imgbackend.ai_utils import genai

load_dotenv()
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-pro")


def _guess_mime_type(path_or_url: str, fallback: str = "image/jpeg") -> str:
    mime_type, _ = mimetypes.guess_type(path_or_url or "")
    if mime_type and mime_type.startswith("image/"):
        return mime_type
    return fallback


def _load_image_as_inline(image_path: str = None, image_url: str = None, image_bytes: bytes = None, mime_type: str = None):
    """Load one image into Gemini inline_data format. Prefers local path, then bytes, then URL."""
    data = None
    resolved_mime = mime_type

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            data = f.read()
        resolved_mime = resolved_mime or _guess_mime_type(image_path)
    elif image_bytes:
        data = image_bytes
        resolved_mime = resolved_mime or "image/jpeg"
    elif image_url:
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        data = img_response.content
        header_mime = img_response.headers.get("content-type", "image/jpeg").split(";")[0]
        resolved_mime = resolved_mime or (
            header_mime if header_mime.startswith("image/") else _guess_mime_type(image_url)
        )

    if not data:
        return None

    return {
        "inline_data": {
            "mime_type": resolved_mime or "image/jpeg",
            "data": base64.b64encode(data).decode("utf-8"),
        }
    }


def call_gemini_api(prompt: str, image_url: str = None, image_path: str = None, image_parts: list = None):
    """
    Call Gemini API with optional vision inputs.

    Args:
        prompt: Text prompt for the API
        image_url: Optional single image URL
        image_path: Optional local filesystem path (preferred over URL)
        image_parts: Optional list of dicts:
            {"label": "...", "path": "...", "url": "...", "bytes": b"...", "mime_type": "..."}

    Returns:
        API response text or None on error
    """
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        contents = [prompt]

        # Multi-image path used for moodboard prompt generation
        if image_parts:
            for part in image_parts:
                if not part:
                    continue
                label = (part.get("label") or "").strip()
                inline = _load_image_as_inline(
                    image_path=part.get("path"),
                    image_url=part.get("url"),
                    image_bytes=part.get("bytes"),
                    mime_type=part.get("mime_type"),
                )
                if not inline:
                    print(f"⚠️ Skipping unreadable moodboard image part: {label or part}")
                    continue
                if label:
                    contents.append(f"REFERENCE IMAGE — {label}:")
                contents.append(inline)
        else:
            inline = _load_image_as_inline(image_path=image_path, image_url=image_url)
            if inline:
                contents.append(inline)

        # Text-only if no images attached successfully
        if len(contents) == 1:
            contents = prompt

        response = client.models.generate_content(
            model=GEMINI_TEXT_MODEL,
            contents=contents,
        )
        return (response.text or "").strip()
    except Exception as e:
        print("Gemini API error:", e)
        return None


def normalize_analysis_text(analysis_text: str, category: str = "") -> str:
    """
    Convert stored analysis into clean prompt-ready text.
    Theme analyses are often JSON {"type","description"} — extract description.
    """
    if not analysis_text or not str(analysis_text).strip():
        return ""

    text = str(analysis_text).strip()
    placeholder = "analyze lighting, style, subject composition"
    if placeholder in text.lower():
        return ""

    if category == "theme" or text.startswith("{") or '"description"' in text:
        try:
            cleaned = re.sub(r'^```(?:json)?|```$', '', text, flags=re.IGNORECASE).strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                description = (parsed.get("description") or "").strip()
                ornament_type = (parsed.get("type") or "").strip()
                if description and ornament_type:
                    return f"{description} (ornament focus: {ornament_type})"
                return description or ornament_type or text
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return text


def collect_moodboard_image_parts(item, categories=None, max_per_category=1, max_total=8):
    """
    Collect local/cloud moodboard images for multimodal Gemini calls.
    Returns list of {"label","path","url"} parts.
    """
    from imgbackendapp.file_utils import resolve_media_path

    categories = categories or ['theme', 'background', 'pose', 'location', 'color', 'outfit']
    parts = []

    for category in categories:
        if len(parts) >= max_total:
            break
        images = getattr(item, f"uploaded_{category}_images", None) or []
        added = 0
        for img in images:
            if added >= max_per_category or len(parts) >= max_total:
                break
            local_path = None
            stored = getattr(img, "local_path", None)
            if stored:
                try:
                    resolved = resolve_media_path(stored)
                    if resolved and os.path.exists(resolved):
                        local_path = resolved
                except Exception:
                    local_path = None
            cloud_url = getattr(img, "cloud_url", None)
            if not local_path and not cloud_url:
                continue
            filename = getattr(img, "original_filename", None) or category
            parts.append({
                "label": f"{category.upper()} reference ({filename})",
                "path": local_path,
                "url": cloud_url,
            })
            added += 1

    return parts


def parse_gemini_response(raw_response):
    """Extract JSON safely from Gemini API response"""
    if isinstance(raw_response, str):
        cleaned_text = raw_response.strip()
    else:
        try:
            cleaned_text = raw_response.get("candidates", [])[
                0]["content"]["parts"][0]["text"]
        except (IndexError, KeyError, TypeError):
            return {}

    cleaned_text = re.sub(r'^```(?:json)?|```$', '',
                          cleaned_text, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(cleaned_text)
    except json.JSONDecodeError:
        import ast
        try:
            parsed = ast.literal_eval(cleaned_text)
        except Exception:
            parsed = {}
    return parsed


def request_suggestions(description, uploaded_image=None, target_audience=None, campaign_season=None):
    """Initial Gemini API request to get suggestions"""
    from .prompt_initializer import get_prompt_from_db

    default_prompt = """You are a highly skilled AI creative director and visual concept designer.
Your job is to generate structured, high-quality visual prompt suggestions for an AI image generation system.

Analyze the following inputs carefully:

Collection Description:
{description}

Target Audience (if provided):
{target_audience}

Campaign Season (if provided):
{campaign_season}

Your goal:
Create imaginative yet relevant visual concepts that perfectly match the product collection's description,
appeal to the specified audience, and align with the campaign season's mood, trends, and aesthetics.

Instructions:
1. Think of this as preparing visual ideas for a brand campaign or photoshoot.
2. Consider the overall tone, cultural context, and emotional appeal suited for the audience and season.
3. Make sure the ideas are cohesive and realistic to implement in a fashion/product photography or advertising context.
4. Each category must contain short, descriptive, and clear prompts suitable for use with AI image generation tools.
5. Outfits must describe complete wearable attire for models (garment type, silhouette, fabric, color, styling) that complements jewelry photography for this collection.

Generate JSON containing 6 types:
- Themes
- Backgrounds/Backdrops
- Poses
- Locations
- Color palettes
- Outfits

Limit 10 prompts per category."""

    # Get prompt from database with fallback
    prompt = get_prompt_from_db(
        'suggestion_prompt_base',
        default_prompt,
        description=description,
        target_audience=target_audience if target_audience else "Not specified",
        campaign_season=campaign_season if campaign_season else "Not specified"
    )

    # Ensure older DB prompt templates still request outfits
    if prompt and "Outfits" not in prompt:
        prompt = prompt.rstrip() + """

Also generate an "Outfits" array with up to 10 short, descriptive outfit/attire directions suitable for model and campaign photography for this collection (garment type, silhouette, fabric, color, styling). Include "Outfits" in the JSON response."""

    response_text = call_gemini_api(prompt)
    parsed = parse_gemini_response(response_text)

    key_map = {
        "Themes": "themes",
        "Backgrounds/Backdrops": "backgrounds",
        "Poses": "poses",
        "Locations": "locations",
        "Color palettes": "colors",
        "Outfits": "outfits",
    }

    # Accept common alternate keys Gemini may return
    alternate_keys = {
        "outfits": ["Outfits", "Outfit", "outfit", "outfits", "Attire", "attire", "Clothing", "clothing"],
        "themes": ["Themes", "themes", "Theme"],
        "backgrounds": ["Backgrounds/Backdrops", "Backgrounds", "backgrounds", "Backdrops"],
        "poses": ["Poses", "poses", "Pose"],
        "locations": ["Locations", "locations", "Location"],
        "colors": ["Color palettes", "Colors", "colors", "Color Palettes", "Colour palettes"],
    }

    suggestions = {}
    if parsed:
        for api_key, norm_key in key_map.items():
            values = parsed.get(api_key)
            if not values:
                for alt in alternate_keys.get(norm_key, []):
                    if parsed.get(alt):
                        values = parsed.get(alt)
                        break
            if isinstance(values, str):
                values = [values]
            suggestions[norm_key] = (values or [])[:10]
    else:
        suggestions = {k: [] for k in key_map.values()}
    return suggestions


def generate_images_from_prompt(prompt):
    """
    Placeholder function to generate images from prompt.
    Replace with Gemini image generation API when available.
    """
    return [
        "https://via.placeholder.com/400x300?text=Image+1",
        "https://via.placeholder.com/400x300?text=Image+2",
        "https://via.placeholder.com/400x300?text=Image+3",
    ]


def get_prompt_from_db(prompt_key, default_prompt=None, **format_kwargs):
    """
    Fetch a prompt from the database by key. If not found or inactive, return default_prompt.
    Format the prompt with provided kwargs if it's a template.
    Automatically inserts instructions and rules from the database if {instructions} and {rules} placeholders exist.

    Args:
        prompt_key: The key identifier for the prompt
        default_prompt: Fallback prompt if not found in database
        **format_kwargs: Variables to format into the prompt template

    Returns:
        The formatted prompt content from database or default_prompt
    """
    try:
        from .models import PromptMaster
        prompt = PromptMaster.objects(
            prompt_key=prompt_key, is_active=True).first()
        if prompt:
            prompt_content = prompt.prompt_content
            instructions = prompt.instructions or ""
            rules = prompt.rules or ""

            # Add instructions and rules to format_kwargs if they exist in the prompt
            if '{instructions}' in prompt_content or '{rules}' in prompt_content:
                if 'instructions' not in format_kwargs:
                    format_kwargs['instructions'] = instructions
                if 'rules' not in format_kwargs:
                    format_kwargs['rules'] = rules
            elif instructions or rules:
                # If placeholders don't exist but instructions/rules do, append them
                # Find insertion point (before "Generate prompts" or before JSON section)
                insertion_text = ""
                if instructions:
                    insertion_text += f"\n\n{instructions}"
                if rules:
                    insertion_text += f"\n\n{rules}"

                # Also add global_instruction_rule if provided
                global_rule = format_kwargs.get('global_instruction_rule', '')
                if global_rule:
                    insertion_text += f"\n{global_rule}"

                # Insert before "Generate prompts" if it exists
                if 'Generate prompts for the following' in prompt_content:
                    parts = prompt_content.split(
                        'Generate prompts for the following', 1)
                    if len(parts) == 2:
                        prompt_content = parts[0].rstrip(
                        ) + insertion_text + '\n\nGenerate prompts for the following' + parts[1]
                # Or insert before JSON section
                elif 'Respond ONLY in valid JSON' in prompt_content:
                    prompt_content = prompt_content.replace(
                        'Respond ONLY in valid JSON',
                        insertion_text + '\n\nRespond ONLY in valid JSON'
                    )
                # Or just append at the end before any closing braces
                else:
                    prompt_content = prompt_content.rstrip() + insertion_text

            # Format the prompt if kwargs are provided
            if format_kwargs:
                try:
                    return prompt_content.format(**format_kwargs)
                except KeyError as e:
                    print(
                        f"Warning: Missing format variable {e} in prompt {prompt_key}, using as-is")
                    return prompt_content
            print(f"Prompt content: {prompt_content}")
            return prompt_content
    except Exception as e:
        print(f"Error fetching prompt from database: {e}")

    # Fallback to default and format if needed
    if default_prompt:
        # Add default empty strings for instructions and rules if placeholders exist
        if '{instructions}' in default_prompt or '{rules}' in default_prompt:
            if 'instructions' not in format_kwargs:
                format_kwargs['instructions'] = ""
            if 'rules' not in format_kwargs:
                format_kwargs['rules'] = ""
        if format_kwargs:
            try:
                return default_prompt.format(**format_kwargs)
            except KeyError as e:
                print(
                    f"Warning: Missing format variable {e} in default prompt, using as-is")
                return default_prompt
        return default_prompt

    return None


def get_queue_for_user(user_id, num_queues=20):
    """
    Select a queue for a user based on consistent hashing of user_id.
    This ensures tasks from the same user are routed to the same queue,
    while distributing users across available queues.

    Args:
        user_id: User identifier (string or number)
        num_queues: Total number of queues (default: 20)

    Returns:
        Queue name string (e.g., 'queue_0', 'queue_1', ..., 'queue_19')
    """
    # Convert user_id to string for consistent hashing
    user_str = str(user_id)

    # Hash the user_id to get a consistent integer
    hash_value = int(hashlib.md5(user_str.encode('utf-8')).hexdigest(), 16)

    # Map hash to queue index (0 to num_queues-1)
    queue_index = hash_value % num_queues

    return f'queue_{queue_index}'


def enqueue_task_to_user_queue(task, queue_user_id, *args, **kwargs):
    """
    Helper function to enqueue a Celery task to the user's assigned queue.
    Uses consistent hashing based on a routing user id (legacy method).

    Args:
        task: Celery task (e.g., generate_ai_images_task)
        queue_user_id: User identifier for queue routing (used only for queue selection)
        *args: Positional arguments for the task
        **kwargs: Keyword arguments for the task

    Returns:
        AsyncResult: The result of apply_async
    """
    queue_name = get_queue_for_user(queue_user_id) if queue_user_id else 'queue_0'
    return task.apply_async(args=args, kwargs=kwargs, queue=queue_name)


def enqueue_task_with_load_balancing(task, *args, **kwargs):
    """
    Enqueue a Celery task using dynamic load-based queue selection.
    Selects the queue with the lowest (pending + running) count.
    Atomically increments the pending counter before enqueueing.

    Args:
        task: Celery task (e.g., generate_ai_images_task)
        *args: Positional arguments for the task
        **kwargs: Keyword arguments for the task

    Returns:
        AsyncResult: The result of apply_async
    """
    from probackendapp.queue_load_manager import (
        select_best_queue,
        increment_pending
    )

    # Select the least-loaded queue
    queue_name = select_best_queue()

    # Increment pending counter BEFORE enqueueing (atomic operation)
    increment_pending(queue_name)

    # Enqueue the task to the selected queue
    return task.apply_async(args=args, kwargs=kwargs, queue=queue_name)
