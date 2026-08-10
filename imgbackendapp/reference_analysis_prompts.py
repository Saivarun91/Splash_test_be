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
    "outfit": "dress",
    "attire": "dress",
    "clothing": "dress",
}

REFERENCE_ANALYSIS_PROMPTS = {
    "background": f"""
Analyze this reference image and write one optimized paragraph for themed product image generation.

You MUST cover BOTH:
A) BACKGROUND / SCENE:
- backdrop elements, surfaces, and materials
- spatial layout and depth
- lighting quality, direction, and shadow behavior
- color palette and tonal mood
- props, decor, and atmospheric details (without naming brands)

B) ORNAMENT PLACEMENT IN THE REFERENCE (MANDATORY — analyze carefully):
- Where the ornament/jewelry sits in the frame (center, left, right, foreground, midground)
- How it is placed or presented (flat lay, hanging, resting on surface, draped, angled, standing)
- Orientation and facing direction (which way it points/faces, tilt, rotation)
- Scale and prominence relative to the scene
- Spacing/arrangement if multiple jewelry pieces are visible
- Surface contact and support (on fabric, stone, tray, velvet, table, etc.)

STRICT RULES:
• IGNORE people/models completely — describe only scene + how jewelry is placed in space
• Do NOT describe humans, faces, bodies, hands, or fashion models
• Do NOT copy or describe ornament/jewelry DESIGN details (stones, metal type, brand look)
• DO describe placement, position, orientation, direction, and presentation style of jewelry in the reference
• If no jewelry is visible, still describe ideal product placement zones implied by the composition

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
- ATTIRE / DRESS (ONLY if a model or human is clearly wearing clothing):
  - garment type (e.g. saree, lehenga, gown, kurta, blouse, suit, formal dress, casual wear)
  - dress/outfit colors (dominant and secondary tones)
  - fabric feel, silhouette, and styling details that help recreate the look (without naming brands)

STRICT ATTIRE RULES:
• Include attire details ONLY when clothing is clearly worn by a visible model/person
• If no model/human is wearing a dress or outfit, OMIT attire entirely — do not invent or guess
• Do NOT describe loose fabrics, draped textiles, background cloths, product textiles, or decorative cloths that are not worn as attire
• Do NOT describe jewelry, ornaments, or accessories as dress/attire
• When attire is present, weave garment type and colors naturally into the same paragraph

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

Do NOT describe dress, outfit, clothing, fabric, or garment colors in this paragraph — attire is analyzed separately.

{UNIVERSAL_SAFETY_RULES}
{_OUTPUT_FORMAT_RULES}
""",
    "dress": f"""
Analyze this reference image and write one optimized paragraph describing the DRESS / OUTFIT worn by a model or human for image generation.

Focus on (ONLY when clothing is clearly worn by a visible model/person):
- garment type (e.g. saree, lehenga, gown, kurta, blouse, suit, formal dress, casual wear)
- dress/outfit colors (dominant and secondary tones)
- fabric feel, silhouette, and styling details that help recreate the look (without naming brands)

STRICT RULES:
• Describe attire ONLY if a model or human in the image is clearly wearing that dress/outfit
• If no model/human is wearing a dress or outfit, return an empty response — do not invent or guess
• Do NOT describe loose fabrics, draped textiles, background cloths, product textiles, patterned designs, hanging garments, or decorative cloths that are not worn as attire
• Do NOT describe jewelry, ornaments, or accessories as dress
• Do NOT describe pose, face, identity, or background scene here

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
