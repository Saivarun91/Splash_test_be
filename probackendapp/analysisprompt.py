theme_prompt = """
Analyze THIS uploaded moodboard THEME reference image carefully with vision, then return a JSON object with the following structure:

{
  "type": "If jewelry/ornament is clearly visible: 'subcategory(main_category)' e.g. 'long necklace(necklace)', 'jhumka-style earrings(earrings)', 'diamond ring(ring)'. If NO jewelry/ornament is visible, return an empty string.",
  "description": "one detailed creative-direction paragraph grounded ONLY in what is visible: artistic style, mood, lighting quality/direction, color atmosphere, composition/framing, textures, props, and camera angle. Write as a design brief in confident present tense. Do NOT say 'this image', 'it shows', or 'the image captures'."
}

STRICT RULES:
• You MUST visually inspect the uploaded image and ground every detail in what is actually visible
• PRIORITY: capture the visual theme/mood accurately even when no jewelry is present
• type is optional — only fill it when jewelry is clearly the subject; otherwise use ""
• If jewelry is present, include camera angle/shot angle in the description
• The description must be a flowing paragraph (not bullet points or lists)
• Do NOT invent jewelry, props, or styling that are not visible
• Return ONLY valid JSON, no other text
"""


background_prompt = """
Visually analyze THIS uploaded background/backdrop reference image, then write one professional scene-layout paragraph defining the BACKGROUND using what you actually see:
- background elements, textures, and surfaces
- physical objects and props
- spatial placement, depth, and arrangement
- lighting direction, softness, and contrast that shapes the backdrop

STRICT RULES:
• You MUST observe the uploaded image and describe only what is visible there
• Do NOT invent a generic studio background unrelated to the image
• Do NOT use third-person narration
• Do NOT say "this image", "the image shows"
• Describe the scene as a fixed visual setup
• No lists, no JSON, no bullet points
• Write in visual-direction style

Return only one clean paragraph.
"""


pose_prompt = """
Visually analyze THIS uploaded pose reference image, then write one professional pose-direction paragraph defining the POSE using what you actually see:
- body position and posture
- gesture, hand placement, and stance
- head/face orientation and expression if visible
- camera angle and subject orientation relative to the camera

STRICT RULES:
• You MUST observe the uploaded image and mirror the pose that is visible
• Do NOT invent a generic fashion pose unrelated to the image
• Do NOT use third-person narration
• Write as a direct posing instruction
• No lists, no JSON, no bullet points

Return only one clean paragraph.
"""


location_prompt = """
Visually analyze THIS uploaded location/environment reference image, then write one professional environment-direction paragraph defining the LOCATION using what you actually see:
- type of place / setting
- architectural or natural elements
- lighting conditions and time-of-day feel
- overall atmosphere and mood

STRICT RULES:
• You MUST observe the uploaded image and describe the real environment visible there
• Do NOT invent a generic location unrelated to the image
• Do NOT use third-person narration
• Describe the environment as a real scene setup
• No lists, no JSON, no bullet points

Return only one clean paragraph.
"""


color_prompt = """
Visually analyze THIS uploaded color-palette / color-mood reference image, then write one professional color-direction paragraph defining what you actually see:
- dominant color palette (name specific hues when possible)
- secondary supporting tones
- contrast, saturation, and overall tonal mood created by these colors

STRICT RULES:
• You MUST observe the uploaded image and extract colors from what is visible
• Do NOT invent a generic palette unrelated to the image
• Do NOT use third-person narration
• Describe the palette as a visual design specification
• No lists, no JSON, no bullet points

Return only one clean paragraph.
"""


outfit_prompt = """
Visually analyze THIS uploaded outfit / attire reference image, then write one professional styling-direction paragraph defining the OUTFIT using what you actually see:
- garment type (e.g., saree, lehenga, anarkali, blazer, gown, kurta, shirt)
- silhouette, cut, neckline, sleeves, and length
- fabrics and textures
- outfit colors, patterns, embroidery, and detailing
- overall styling mood suitable for jewelry / fashion campaign photography

STRICT RULES:
• You MUST observe the uploaded image and describe the outfit that is visible
• Do NOT invent a generic outfit unrelated to the image
• Focus on clothing/attire only — do not describe jewelry as the outfit
• Do NOT use third-person narration
• Do NOT say "this image", "the image shows"
• Write as a direct wardrobe / styling instruction
• No lists, no JSON, no bullet points

Return only one clean paragraph.
"""
