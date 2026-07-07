"""Prompt templates for reference image analysis by type."""

UNIVERSAL_SAFETY_RULES = """
STRICT SAFETY RULES (MANDATORY):
• NEVER identify, name, or describe specific people or celebrities
• NEVER reproduce or describe facial features
• NEVER identify brands, logos, trademarks, or brand names
• NEVER reproduce or transcribe visible text
• NEVER describe copyrighted artwork
• IGNORE watermarks, trademarks, and brand names entirely
• Describe ONLY reusable visual characteristics — colors, lighting, materials, composition, atmosphere, styling, and spatial layout
"""

_OUTPUT_FORMAT_RULES = """
OUTPUT FORMAT:
• Return ONLY a single optimized paragraph suitable for direct append to an image generation prompt
• Do NOT return JSON, Markdown, bullet points, headings, labels, or explanations
• Write in present-tense visual-direction style
• Do NOT use third-person narration or phrases like "this image shows" or "the image depicts"
• Keep the description concise but information-rich
"""

REFERENCE_TYPE_ALIASES = {
    "themed": "background",
    "model": "pose",
    "bg": "background",
    "theme": "campaign",
    "style": "campaign",
}

REFERENCE_ANALYSIS_PROMPTS = {
    "background": f"""
Analyze this reference image and write one optimized paragraph describing the BACKGROUND and scene environment for image generation.

Focus on:
- backdrop elements, surfaces, and materials
- spatial layout and depth
- lighting quality, direction, and shadow behavior
- color palette and tonal mood
- props, decor, and atmospheric details (without naming brands)

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "campaign": f"""
Analyze this reference image and write one optimized paragraph describing the CAMPAIGN VISUAL STYLE for image generation.

Focus on:
- overall creative direction and editorial mood
- styling, composition, and art direction
- lighting setup and photographic aesthetic
- color grading and tonal harmony
- environment, props, and fashion/lifestyle context (without naming brands)

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "props": f"""
Analyze this reference image and write one optimized paragraph describing PROPS and supporting visual elements for image generation.

Focus on:
- objects, surfaces, and decorative elements
- material textures and finishes
- placement, scale, and spatial relationships
- how props support the overall scene mood
- color and lighting interaction with props

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "lifestyle": f"""
Analyze this reference image and write one optimized paragraph describing the LIFESTYLE SCENE for image generation.

Focus on:
- setting type and environmental context
- natural or ambient lighting
- casual or editorial lifestyle mood
- compositional framing and depth
- color palette and atmospheric feel

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "studio": f"""
Analyze this reference image and write one optimized paragraph describing the STUDIO SETUP for image generation.

Focus on:
- backdrop type and studio environment
- controlled lighting setup and shadow quality
- surface materials and set design
- professional photography aesthetic
- color palette and clean compositional structure

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "outdoor": f"""
Analyze this reference image and write one optimized paragraph describing the OUTDOOR ENVIRONMENT for image generation.

Focus on:
- location type and natural surroundings
- time-of-day lighting and sky conditions
- weather, atmosphere, and environmental mood
- foreground/background depth and composition
- dominant colors and natural textures

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "interior": f"""
Analyze this reference image and write one optimized paragraph describing the INTERIOR SPACE for image generation.

Focus on:
- room type and architectural elements
- interior materials, finishes, and furnishings
- ambient and accent lighting
- spatial depth and layout
- color palette and upscale or commercial aesthetic

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "pose": f"""
Analyze this reference image and write one optimized paragraph describing the POSE and body positioning for image generation.

Focus on:
- body stance, gesture, and posture
- head angle and subject orientation (without describing facial features)
- camera angle relative to the subject
- hand/arm placement and overall silhouette
- editorial or natural posing energy

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "custom": f"""
Analyze this reference image and write one optimized paragraph describing reusable visual characteristics for image generation.

Focus on:
- scene environment and atmosphere
- lighting, colors, and composition
- styling, materials, and spatial layout
- mood and photographic aesthetic

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
}

DEFAULT_REFERENCE_TYPE = "custom"
