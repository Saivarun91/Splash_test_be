theme_prompt = """
Analyze this image and return a JSON object with the following structure:

{
  "type": "the specific type of ornament in the format 'subcategory(main_category)' where subcategory includes all modifiers and main_category is the MOST HIGHLIGHTED/PROMINENT ornament in the image. Examples: 'long necklace(necklace)', 'multi-layered pearl and gold necklace(necklace)', 'jhumka-style earrings(earrings)', 'stud earrings(earrings)', 'chunky bracelet(bracelet)', 'diamond ring(ring)'. IMPORTANT: Identify which ornament is the MAIN/MOST HIGHLIGHTED ornament in the image (necklace, earrings, bracelet, ring, anklet, brooch, etc.) - this becomes the main_category in parentheses. Other ornaments present in the image can be mentioned in the description but should NOT be in the type field. If no ornament is present, return empty string.",
  "description": "one professional creative-direction paragraph defining the THEME including: artistic style, overall mood, core creative concept, and camera angle/shot angle when describing ornaments (e.g., 'photographed from an overhead 90-degree angle', 'captured in a flat-lay top-down view', 'shot from a slight diagonal angle above', etc.). You can mention other ornaments present in the image in the description, but the type field should only contain the MOST HIGHLIGHTED ornament. The description should be written in design-brief direction style, using confident descriptive present-tense language. Do NOT use third-person narration. Do NOT say 'this image', 'it shows', 'the image captures', etc."
}

STRICT RULES:
• CRITICAL: The type must be in the format 'subcategory(main_category)' where main_category is the SINGLE MOST PROMINENT/HIGHLIGHTED ornament in the image (e.g., if necklace is most highlighted, use 'long necklace(necklace)' even if earrings are also present)
• If multiple ornaments are present, identify which one is the MAIN/MOST HIGHLIGHTED and use only that in the type field
• Other ornaments can be mentioned in the description but should NOT appear in the type field
• The description must be a flowing paragraph (not bullet points or lists)
• If ornaments are present, the description must include the camera angle/shot angle
• The description should focus on artistic style, mood, and creative concept
• Return ONLY valid JSON, no other text
"""


background_prompt = """
Write one professional scene-layout paragraph defining the BACKGROUND using:
- background elements
- physical objects
- spatial placement and arrangement

STRICT RULES:
• Do NOT use third-person narration
• Do NOT say "this image", "the image shows"
• Describe the scene as a fixed visual setup
• No lists, no JSON, no bullet points
• Write in visual-direction style

Return only one clean paragraph.
"""


pose_prompt = """
Write one professional pose-direction paragraph defining the POSE using:
- body position
- gesture and stance
- camera angle and subject orientation

STRICT RULES:
• Do NOT observe the image
• Do NOT use third-person narration
• Write as a direct posing instruction
• No lists, no JSON, no bullet points

Return only one clean paragraph.
"""


location_prompt = """
Write one professional environment-direction paragraph defining the LOCATION using:
- type of place
- lighting conditions
- overall atmosphere

STRICT RULES:
• Do NOT reference any image
• Do NOT use third-person narration
• Describe the environment as a real scene setup
• No lists, no JSON, no bullet points

Return only one clean paragraph.
"""


color_prompt = """
Write one professional color-direction paragraph defining:
- dominant color palette
- secondary supporting tones
- overall tonal mood created by these colors

STRICT RULES:
• Do NOT reference any image
• Do NOT use third-person narration
• Describe the palette as a visual design specification
• No lists, no JSON, no bullet points

Return only one clean paragraph.
"""
