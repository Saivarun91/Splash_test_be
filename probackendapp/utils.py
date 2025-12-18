import os
import requests
import json
import re
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def call_gemini_api(prompt: str, image_url: str = None):
    """
    Call Gemini API with optional image URL for vision analysis.

    Args:
        prompt: Text prompt for the API
        image_url: Optional image URL for vision analysis

    Returns:
        API response text or None on error
    """
    import base64

    headers = {"x-goog-api-key": GEMINI_API_KEY,
               "Content-Type": "application/json"}

    # Build parts array
    parts = [{"text": prompt}]

    # If image_url is provided, download and encode it as base64
    if image_url:
        try:
            # Download the image
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()

            # Encode as base64
            img_base64 = base64.b64encode(img_response.content).decode('utf-8')

            # Determine mime type from URL or response headers
            mime_type = "image/jpeg"  # default
            if 'content-type' in img_response.headers:
                mime_type = img_response.headers['content-type'].split(';')[0]
            elif image_url.lower().endswith('.png'):
                mime_type = "image/png"
            elif image_url.lower().endswith('.webp'):
                mime_type = "image/webp"

            # Add image as inline_data
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": img_base64
                }
            })
        except Exception as img_error:
            print(
                f"Error downloading/encoding image from {image_url}: {img_error}")
            # Continue without image if download fails

    data = {"contents": [{"parts": parts}]}

    try:
        response = requests.post(
            GEMINI_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        text_output = result["candidates"][0]["content"]["parts"][0]["text"]

        return text_output
    except Exception as e:
        print("Gemini API error:", e)
        return None


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

Generate JSON containing 5 types:
- Themes
- Backgrounds/Backdrops
- Poses
- Locations
- Color palettes

Limit 10 prompts per category."""

    # Get prompt from database with fallback
    prompt = get_prompt_from_db(
        'suggestion_prompt_base',
        default_prompt,
        description=description,
        target_audience=target_audience if target_audience else "Not specified",
        campaign_season=campaign_season if campaign_season else "Not specified"
    )

    response_text = call_gemini_api(prompt)
    parsed = parse_gemini_response(response_text)

    key_map = {
        "Themes": "themes",
        "Backgrounds/Backdrops": "backgrounds",
        "Poses": "poses",
        "Locations": "locations",
        "Color palettes": "colors"
    }
    suggestions = {norm_key: parsed.get(api_key, [])[:10] for api_key, norm_key in key_map.items(
    )} if parsed else {k: [] for k in key_map.values()}
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
