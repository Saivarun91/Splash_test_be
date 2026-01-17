"""
Initialize default prompts in the database.
This ensures all system prompts are available in the PromptMaster collection.
"""
from .models import PromptMaster
from users.models import User
from datetime import datetime, timezone


def initialize_default_prompts():
    """Initialize all default prompts in the database if they don't exist"""

    # Get or create a system user (first admin user or create a placeholder)
    try:
        system_user = User.objects.first()
    except Exception:
        system_user = None

    default_prompts = [
        {
            "prompt_key": "suggestion_prompt_base",
            "title": "Suggestion Generation Base Prompt",
            "description": "Base prompt for generating visual suggestions (themes, backgrounds, poses, locations, colors) from collection description",
            "prompt_content": """You are a highly skilled AI creative director and visual concept designer.
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

Limit 10 prompts per category.""",
            "category": "suggestion",
            "prompt_type": "suggestion_prompt",
            "is_active": True,
        },
        {
            "prompt_key": "generation_prompt_with_images",
            "title": "Generation Prompt with Uploaded Images",
            "description": "Prompt for generating image prompts when user has uploaded reference images",
            "prompt_content": """You are a professional creative AI assistant specializing in product photography and marketing. You have been provided with a collection description and user-uploaded reference images that should be analyzed in detail to create highly specific and targeted image generation prompts.

COLLECTION DESCRIPTION: {collection_description}

USER-UPLOADED REFERENCE IMAGES (ANALYZE THESE IN DETAIL):
{uploaded_images_analysis}

SELECTED SUGGESTIONS (use only for categories without uploaded images):
Themes: {themes}
Backgrounds: {backgrounds}
Poses: {poses}
Locations: {locations}
Colors: {colors}{picked_colors_info}{global_instructions_info}

{instructions}

{rules}
{global_instruction_rule}

Generate prompts for the following 4 types. Respond ONLY in valid JSON:
{{
    "white_background": "Detailed prompt for white background product photography incorporating visual elements from uploaded images",
    "background_replace": "Detailed prompt for themed background images that match the style and aesthetic of uploaded reference images",
    "model_image": "Detailed prompt for realistic model photography incorporating poses, expressions, and styling from uploaded reference images",
    "campaign_image": "Detailed prompt for campaign shots that capture the mood, composition, and visual style of uploaded reference images"
}}""",
            "instructions": """# INSTRUCTIONS:
# 1. For categories with uploaded images, analyze the visual content, style, mood, lighting, composition, and aesthetic elements from the uploaded images
# 2. Extract specific visual details like color palettes, textures, lighting conditions, composition styles, and mood from the uploaded images
# 3. For categories without uploaded images, use the selected suggestions
# 4. Create prompts that incorporate the visual elements and style from uploaded images
# 5. Ensure prompts are specific, detailed, and actionable for AI image generation""",
            "rules": """RULES FOR PROMPT CREATION:
1. PRIORITIZE analysis of uploaded images. Extract their style, lighting, camera composition, colors, and artistic tone.
2. For missing categories, use the user's selected text inputs.
3. Blend both to create cohesive, brand-consistent image prompts.
4. Be specific — describe lighting, materials, perspective, model type, emotion, and background details.
5. Keep prompts actionable and detailed for AI image generation systems.
6. COLOR PRIORITY: If picked colors are provided, use them as the primary color scheme. If only selected suggestions are provided, use those instead.""",
            "category": "generation",
            "prompt_type": "generation_prompt",
            "is_active": True,
        },
        {
            "prompt_key": "generation_prompt_simple",
            "title": "Generation Prompt Simple (No Images)",
            "description": "Prompt for generating image prompts when user has not uploaded reference images",
            "prompt_content": """You are a professional creative AI assistant. Analyze the collection description and user selections carefully and generate structured image generation prompts.

Collection Description: {collection_description}
Selected Themes: {themes}
Selected Backgrounds: {backgrounds}
Selected Poses: {poses}
Selected Locations: {locations}
Selected Colors: {colors}{picked_colors_info}{global_instructions_info}

{instructions}

{rules}
{global_instruction_rule}

Generate prompts for the following 4 types. Respond ONLY in valid JSON:
{{
    "white_background": "Prompt for white background images of the product, sharp, clean, isolated.",
    "background_replace": "Prompt for images with themed backgrounds while keeping the product identical.",
    "model_image": "Prompt to generate realistic model wearing/holding the product. Model face and body must be accurate. Match selected poses and expressions, photo should be focused mainly on the product.",
    "campaign_image": "Prompt for campaign/promotional shots with models and products in themed backgrounds, stylish composition."
}}""",
            "instructions": """# INSTRUCTIONS:
# 1. Analyze the collection description and user selections carefully
# 2. Create prompts that are specific, detailed, and actionable for AI image generation
# 3. Ensure prompts match the selected themes, backgrounds, poses, locations, and colors
# 4. Maintain consistency across all four prompt types
# 5. Focus on product clarity and professional photography standards""",
            "rules": """RULES FOR PROMPT CREATION:
1. Use the selected themes, backgrounds, poses, locations, and colors as primary guidance
2. Be specific — describe lighting, materials, perspective, model type, emotion, and background details
3. Keep prompts actionable and detailed for AI image generation systems
4. COLOR PRIORITY: If picked colors are provided, use them as the primary color scheme. If only selected suggestions are provided, use those instead
5. Ensure all prompts maintain brand consistency and professional quality
6. Model images must have accurate facial features and body proportions""",
            "category": "generation",
            "prompt_type": "generation_prompt",
            "is_active": True,
        },
        {
            "prompt_key": "white_background_template",
            "title": "White Background Image Generation Template",
            "description": "Template prompt for generating white background product images",
            "prompt_content": """CRITICAL RULES - DO NOT VIOLATE:
1. Do NOT modify, alter, or redesign the product in any way — its color, shape, texture, proportions, stones, pendant details, and all minute elements must remain EXACTLY the same as the input product image.
2. The product image must be the MAIN FOCUS of the frame - it should be the primary subject with maximum clarity and detail.
3. Based on the prompt context and style prompt provided, position the ornament appropriately:
   - If the prompt suggests hanging (necklace, pendant, earrings), display the ornament hanging naturally
   - If the prompt suggests laying (bracelet, ring, decorative piece), display it laying on a clean surface (ground, table, or elegant platform)
   - The positioning must match the context of the style prompt while keeping the product identical
4. Generate a high-quality product photo on a clean, elegant white studio background.
5. The product should appear exactly as in the input image, only placed against a professional white background with appropriate positioning based on context.
6. Ensure balanced, soft studio lighting with natural shadows and realistic reflections that enhance product visibility.
7. Highlight product clarity and detail - every stone, pendant, chain link, and design element must be clearly visible and identical to the original.
8. Follow this specific style prompt: {prompt_text}""",
            "rules": """RULES FOR WHITE BACKGROUND IMAGE GENERATION:

1. PRODUCT PRESERVATION (MANDATORY):
   - The product/ornament must remain EXACTLY identical to the input product image
   - Do NOT change: color, shape, size, texture, material, finish, or any design elements
   - Preserve ALL minute details: every stone, gem, pendant, chain link, clasp, engraving, pattern, and decorative element
   - The product must appear as if it's the exact same physical item from the input image

2. POSITIONING BASED ON PROMPT CONTEXT:
   - Analyze the style prompt to determine appropriate positioning
   - HANGING POSITION: For necklaces, pendants, earrings, or any ornament meant to be worn hanging
     * Display the ornament hanging naturally from a hook, stand, or elegant support
     * Ensure natural drape and flow that matches the product type
     * Maintain product clarity while showing realistic hanging position
   - LAYING POSITION: For bracelets, rings, decorative pieces, or ornaments meant to rest on surfaces
     * Display the ornament laying flat or elegantly arranged on a clean surface (table, ground, platform)
     * Use a clean, minimal surface that doesn't distract from the product
     * Ensure the product is fully visible and all details are clear
   - The positioning must enhance product visibility while matching the context of the style prompt

3. FOCUS AND COMPOSITION:
   - The product must be the MAIN FOCUS and PRIMARY SUBJECT of the image
   - Center the product in the frame or use rule-of-thirds for elegant composition
   - Ensure the product occupies a significant portion of the frame (at least 40-60% of visible area)
   - Background should be completely white with no distractions, patterns, or elements that compete for attention
   - Use shallow depth of field if needed to ensure product is sharp while background is pure white

4. LIGHTING REQUIREMENTS:
   - Use balanced, soft studio lighting that evenly illuminates the product
   - Create natural shadows that enhance product dimension without obscuring details
   - Ensure realistic reflections on metallic surfaces that match the product's material
   - Avoid harsh shadows or overexposure that would hide product details
   - Lighting should make every stone, texture, and design element clearly visible

5. DETAIL PRESERVATION:
   - Every stone, gem, or decorative element must be clearly visible and identical to the original
   - Chain links, clasps, and structural elements must maintain exact proportions
   - Engravings, patterns, and textures must be preserved exactly
   - Color accuracy is critical - match the exact hues, tones, and finishes from the input image
   - Surface finishes (matte, glossy, brushed) must remain identical

6. QUALITY STANDARDS:
   - Generate high-resolution, professional product photography quality
   - Ensure sharp focus on all product details
   - Maintain realistic proportions and perspective
   - The final image should be suitable for e-commerce, catalog, or marketing use""",
            "category": "template",
            "prompt_type": "white_background",
            "is_active": True,
        },
        {
            "prompt_key": "background_replace_template",
            "title": "Background Replace Image Generation Template",
            "description": "Template prompt for replacing product backgrounds",
            "prompt_content": """CRITICAL RULES - DO NOT VIOLATE:
1. Do NOT modify the product itself — preserve its original look, proportions, color, texture, stones, pendant details, and ALL minute elements EXACTLY as they appear in the input product image.
2. The product image must be the MAIN FOCUS of the frame - it should be the primary subject with maximum clarity and detail.
3. Based on the prompt context and style prompt provided, position the ornament appropriately:
   - If the prompt suggests hanging (necklace, pendant, earrings), display the ornament hanging naturally against the new background
   - If the prompt suggests laying (bracelet, ring, decorative piece), display it laying on a clean surface (ground, table, or elegant platform) that matches the new background
   - The positioning must match the context of the style prompt while keeping the product identical
4. Replace ONLY the background of the product image with one that enhances and highlights the ornament elegantly.
5. The new background should create a professional photo-shoot vibe with proper lighting, depth, and composition that complements the product.
6. Ensure the product is the focal point of the frame and stands out naturally under studio lighting.
7. Use soft shadows, realistic reflections, and balanced highlights that enhance product visibility without altering the product itself.
8. Every stone, pendant, chain link, and design element must remain EXACTLY as in the original product image.
9. MASTER ANALYSIS FOLLOWING (CRITICAL): If the style prompt below is a comprehensive master theme analysis, you MUST follow it EXACTLY without missing a single detail. The master analysis contains specific information about:
   - Exact placement and positioning of ornaments (e.g., "rests diagonally", "gracefully drapes", "positioned elegantly beside")
   - Precise lighting conditions (e.g., "soft, warm ambient lighting", "shallow depth of field", "soft diffused top lighting")
   - Specific surface materials and textures (e.g., "light beige, rectangular jewelry box", "soft, neutral surface", "silk fabric, velvet, marble")
   - Exact artistic style and mood (e.g., "sophisticated minimalism", "opulent heritage", "serene luxury")
   - All supporting elements and props mentioned (e.g., flowers, decorative pieces, fabrics)
   - Follow EVERY detail from the master analysis exactly as described - do not generalize or simplify any aspect.
10. Follow this specific style prompt EXACTLY: {prompt_text}""",
            "rules": """RULES FOR MODEL IMAGE GENERATION:

1. MODEL PRESERVATION (MANDATORY - EXACT MATCH):
   - The uploaded model image must be EXACTLY the same in the generated image
   - Preserve ALL facial features: exact facial structure, bone structure, jawline, cheekbones, nose shape, eye shape, eyebrow shape, lip shape
   - Maintain EXACT skin tone, skin texture, complexion, undertones, and skin characteristics
   - Preserve hair: exact color, texture, style, length, and any highlights or natural variations
   - Keep body proportions identical: height, build, body shape, muscle definition, and physical characteristics
   - Maintain exact facial expressions, natural features, and distinctive characteristics
   - Do NOT alter, enhance, or modify any aspect of the model's appearance

2. PRODUCT/ORNAMENT PRESERVATION (MANDATORY - EXACT MATCH):
   - The product/ornament must be EXACTLY identical to the input product image
   - Preserve ALL minute details: every stone, gem, pendant, chain link, clasp, engraving, pattern, decorative element
   - Maintain exact color, shape, size, texture, material, finish, and all design elements
   - Every stone must be the same: size, cut, color, clarity, placement, and setting
   - Pendant details must be identical: shape, design, engravings, decorative elements
   - Chain links must be exact: size, style, pattern, and construction
   - Metal finish must match: gold tone, silver tone, plating, polish, and surface texture
   - The product must appear as if it's the exact same physical item from the input image

3. NATURAL INTEGRATION:
   - The product must fit the model naturally and proportionally
   - Ensure correct placement on the model (neck, wrist, ear, etc.) based on product type
   - The product should appear to be naturally worn, not artificially placed
   - Maintain realistic weight and drape of the product on the model
   - Ensure the product sits naturally against the model's skin or clothing

4. LIGHTING CONSISTENCY:
   - Lighting on the model and product must be consistent and natural
   - Ensure the product's lighting matches the model's lighting direction and intensity
   - Shadows and highlights on both model and product should be consistent
   - Product should appear naturally lit, not artificially illuminated
   - Maintain realistic reflections on both model's skin and product's metallic surfaces

5. COMPOSITION AND FOCUS:
   - The product should be clearly visible and well-positioned on the model
   - Use professional fashion photography composition and framing
   - Ensure both model and product are in sharp focus
   - The product should be a prominent element while maintaining model's natural appearance
   - Create elegant composition that showcases both model and product effectively

6. QUALITY STANDARDS:
   - Generate high-resolution, professional fashion photography quality
   - Maintain realistic skin texture, product details, and overall image quality
   - Ensure natural-looking integration between model and product
   - The final image should look like a professional fashion or jewelry photoshoot
   - Both model and product should appear natural, realistic, and professionally photographed

7. STYLE PROMPT INTEGRATION:
   - Follow the style prompt while maintaining exact model and product preservation
   - Style elements (pose, expression, background hints) should enhance but not alter core elements
   - Ensure style prompt elements don't compromise model or product accuracy""",
            "category": "template",
            "prompt_type": "model_image",
            "is_active": True,
        },
        {
            "prompt_key": "campaign_image_template",
            "title": "Campaign Image Generation Template",
            "description": "Template prompt for generating campaign-style images",
            "prompt_content": """Create a professional campaign-style image where the uploaded model (where the uploaded model is present in the model_image_path should be exactly the same) is wearing ONLY the given product, 
keeping the product exactly as it appears in the original product image — no changes in color, shape, or design. 
Use a lifestyle or editorial-style background that enhances the brand aesthetic while maintaining focus on the product. 
Ensure cinematic yet natural studio lighting, soft shadows, and high-end magazine-quality realism. 
Follow this specific style prompt: {prompt_text}""",
            "rules": """RULES FOR CAMPAIGN IMAGE GENERATION:

1. MODEL PRESERVATION (MANDATORY - EXACT MATCH):
   - The uploaded model image must be EXACTLY the same in the generated campaign image
   - Preserve ALL facial features: exact facial structure, bone structure, jawline, cheekbones, nose shape, eye shape, eyebrow shape, lip shape
   - Maintain EXACT skin tone, skin texture, complexion, undertones, and skin characteristics
   - Preserve hair: exact color, texture, style, length, and any highlights or natural variations
   - Keep body proportions identical: height, build, body shape, muscle definition, and physical characteristics
   - Maintain exact facial expressions, natural features, and distinctive characteristics
   - Do NOT alter, enhance, or modify any aspect of the model's appearance
   - The model should be immediately recognizable as the same person from the uploaded image

2. PRODUCT/ORNAMENT PRESERVATION (MANDATORY - EXACT MATCH):
   - The product/ornament must be EXACTLY identical to the input product image
   - Preserve ALL minute details: every stone, gem, pendant, chain link, clasp, engraving, pattern, decorative element
   - Maintain exact color, shape, size, texture, material, finish, and all design elements
   - Every stone must be the same: size, cut, color, clarity, placement, and setting
   - Pendant details must be identical: shape, design, engravings, decorative elements
   - Chain links must be exact: size, style, pattern, and construction
   - Metal finish must match: gold tone, silver tone, plating, polish, and surface texture
   - The product must appear as if it's the exact same physical item from the input image

3. CAMPAIGN AESTHETIC:
   - Create a lifestyle or editorial-style background that enhances the brand aesthetic
   - Background should complement the product and model while maintaining focus on the product
   - Use backgrounds that match the style prompt's theme, mood, and brand identity
   - Background should be sophisticated and appropriate for high-end campaign imagery
   - Ensure background doesn't compete with or distract from the product

4. NATURAL INTEGRATION:
   - The product must fit the model naturally and proportionally
   - Ensure correct placement on the model (neck, wrist, ear, etc.) based on product type
   - The product should appear to be naturally worn, not artificially placed
   - Maintain realistic weight and drape of the product on the model
   - Ensure the product sits naturally against the model's skin or clothing
   - Integration should look natural and effortless, as if the model naturally owns and wears the product

5. LIGHTING CONSISTENCY:
   - Use cinematic yet natural studio lighting that works for campaign photography
   - Lighting on the model and product must be consistent and natural
   - Ensure the product's lighting matches the model's lighting direction and intensity
   - Shadows and highlights on both model and product should be consistent
   - Create soft shadows that enhance dimension without obscuring details
   - Product should appear naturally lit, matching the overall lighting scheme
   - Maintain realistic reflections on both model's skin and product's metallic surfaces

6. COMPOSITION AND FOCUS:
   - The product should be clearly visible and well-positioned on the model
   - Use professional campaign photography composition and framing
   - Ensure both model and product are in appropriate focus (product should be sharp)
   - The product should be a prominent, focal element while maintaining model's natural appearance
   - Create elegant, magazine-quality composition that showcases both model and product effectively
   - Use depth of field strategically to keep product sharp while background can have appropriate blur

7. QUALITY STANDARDS:
   - Generate high-resolution, professional campaign/magazine photography quality
   - Maintain realistic skin texture, product details, and overall image quality
   - Ensure natural-looking integration between model and product
   - The final image should look like a professional fashion campaign or editorial photoshoot
   - Both model and product should appear natural, realistic, and professionally photographed
   - Image should meet high-end magazine, advertising, or luxury brand campaign standards

8. STYLE PROMPT INTEGRATION:
   - Follow the style prompt while maintaining exact model and product preservation
   - Style elements (pose, expression, background, mood) should enhance but not alter core elements
   - Ensure style prompt elements don't compromise model or product accuracy
   - Campaign aesthetic should align with brand identity while preserving all critical details""",
            "category": "template",
            "prompt_type": "campaign_image",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_white_background_template",
            "title": "Regenerate White Background Template",
            "description": "Template for regenerating white background images",
            "prompt_content": """Generate a high-quality product photo on a clean, elegant white studio background. 
Do NOT modify the product - keep its color, shape, texture exactly the same. 
{original_prompt}""",
            "category": "template",
            "prompt_type": "white_background",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_background_replace_template",
            "title": "Regenerate Background Replace Template",
            "description": "Template for regenerating background replace images",
            "prompt_content": """Replace only the background elegantly while keeping the product identical. 
{original_prompt}""",
            "category": "template",
            "prompt_type": "background_replace",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_model_image_template",
            "title": "Regenerate Model Image Template",
            "description": "Template for regenerating model images",
            "prompt_content": """Generate a realistic photo of the model wearing ONLY the given product. 
Keep the product design identical to the original. 
{original_prompt}""",
            "category": "template",
            "prompt_type": "model_image",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_campaign_image_template",
            "title": "Regenerate Campaign Image Template",
            "description": "Template for regenerating campaign images",
            "prompt_content": """Create a professional campaign-style image with the model wearing ONLY the product. 
Keep the product exactly as it appears in the original. 
{original_prompt}""",
            "category": "template",
            "prompt_type": "campaign_image",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_with_modifications_white",
            "title": "Regenerate White Background with Modifications",
            "description": "Template for regenerating white background images with user modifications",
            "prompt_content": """Generate a high-quality product photo on a clean, elegant white studio background. 
Do NOT modify the product - keep its color, shape, texture exactly the same. 
Original style: {original_prompt}. 
Modifications: {new_prompt}""",
            "category": "template",
            "prompt_type": "white_background",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_with_modifications_bg",
            "title": "Regenerate Background Replace with Modifications",
            "description": "Template for regenerating background replace images with user modifications",
            "prompt_content": """Replace only the background elegantly while keeping the product identical. 
Original style: {original_prompt}. 
Modifications: {new_prompt}""",
            "category": "template",
            "prompt_type": "background_replace",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_with_modifications_model",
            "title": "Regenerate Model Image with Modifications",
            "description": "Template for regenerating model images with user modifications",
            "prompt_content": """Generate a realistic photo of the model wearing ONLY the given product. 
Keep the product design identical to the original. 
Original style: {original_prompt}. 
Modifications: {new_prompt}""",
            "category": "template",
            "prompt_type": "model_image",
            "is_active": True,
        },
        {
            "prompt_key": "regenerate_with_modifications_campaign",
            "title": "Regenerate Campaign Image with Modifications",
            "description": "Template for regenerating campaign images with user modifications",
            "prompt_content": """Create a professional campaign-style image with the model wearing ONLY the product. 
Keep the product exactly as it appears in the original. 
Original style: {original_prompt}. 
Modifications: {new_prompt}""",
            "category": "template",
            "prompt_type": "campaign_image",
            "is_active": True,
        },
        {
            "prompt_key": "images_white_background",
            "title": "White Background Image Generation Prompt",
            "description": "Prompt for generating white background images from ornament uploads",
            "prompt_content": "Remove the background from this ornament image and replace it with a plain {bg_color} background.{extra_prompt}",
            "category": "images",
            "prompt_type": "white_background",
            "is_active": True,
        },
        {
            "prompt_key": "images_background_change_base",
            "title": "Background Change Base Prompt",
            "description": "Base prompt for changing ornament backgrounds",
            "prompt_content": "Change the background of this ornament. {final_prompt}",
            "rules": """RULES FOR BACKGROUND CHANGE IMAGE GENERATION:

1. ORNAMENT PRESERVATION (MANDATORY - EXACT MATCH):
   - The ornament must remain EXACTLY identical to the uploaded ornament image
   - Do NOT modify, alter, or redesign the ornament in any way — its color, shape, texture, proportions, stones, pendant details, and ALL minute elements must remain EXACTLY the same
   - Preserve ALL minute details: every stone, gem, pendant, chain link, clasp, engraving, pattern, decorative element, and design feature
   - Every stone must be the same: size, cut, color, clarity, placement, and setting
   - Pendant details must be identical: shape, design, engravings, decorative elements
   - Chain links must be exact: size, style, pattern, and construction
   - Metal finish must match: gold tone, silver tone, plating, polish, and surface texture
   - The ornament must appear as if it's the exact same physical item from the uploaded image

2. ORNAMENT AS MAIN FOCUS (MANDATORY):
   - The ornament must be the PRIMARY SUBJECT and MAIN FOCUS of the image
   - Center the ornament in the frame or use rule-of-thirds for elegant composition
   - Ensure the ornament occupies a significant portion of the frame (at least 50-70% of visible area)
   - The ornament should be the dominant element that immediately draws attention
   - Background should enhance but NEVER compete with or distract from the ornament

3. HIGHLIGHT AND ENHANCE ORNAMENT:
   - Use lighting, shadows, and composition to make the ornament stand out prominently
   - Ensure the ornament is clearly visible and well-lit against the new background
   - Create visual contrast between the ornament and background to enhance visibility
   - Use depth of field to keep ornament sharp while background can have appropriate blur
   - Make sure every detail of the ornament is clearly visible and highlighted

4. BACKGROUND REPLACEMENT:
   - Replace ONLY the background - the ornament itself must remain completely unchanged
   - The new background should complement the ornament's colors and style
   - Background should enhance ornament visibility without clashing or competing
   - Create seamless integration where shadows and lighting appear natural
   - Ensure the background doesn't obscure or hide any ornament details

5. LIGHTING REQUIREMENTS:
   - Use balanced, professional lighting that highlights the ornament
   - Create natural shadows that enhance ornament dimension without obscuring details
   - Ensure realistic reflections on metallic surfaces that match the ornament's material
   - Lighting should make every stone, texture, and design element clearly visible
   - Shadows should appear natural and consistent with the background's lighting direction
   - Avoid harsh shadows or overexposure that would hide ornament details

6. DETAIL PRESERVATION:
   - Every stone, gem, or decorative element must be clearly visible and identical to the original
   - Chain links, clasps, and structural elements must maintain exact proportions
   - Engravings, patterns, and textures must be preserved exactly
   - Color accuracy is critical - match the exact hues, tones, and finishes from the uploaded image
   - Surface finishes (matte, glossy, brushed) must remain identical
   - All minute details must be preserved: clasps, hooks, connectors, decorative elements

7. QUALITY STANDARDS:
   - Generate high-resolution, professional product photography quality
   - Ensure sharp focus on all ornament details
   - Maintain realistic proportions and perspective
   - Create seamless background integration that looks natural and professional
   - The final image should be suitable for marketing, advertising, or e-commerce use
   - The ornament should appear as the star of the image with maximum clarity and detail""",
            "category": "images",
            "prompt_type": "background_replace",
            "is_active": True,
        },
        {
            "prompt_key": "images_background_change_with_color",
            "title": "Background Change with Color Prompt",
            "description": "Prompt for background change when color is specified",
            "prompt_content": "The background should be {bg_color}, but make sure to highlight the ornament and make it stand out and the background color should be the same as the {bg_color}.",
            "rules": """RULES FOR BACKGROUND CHANGE WITH COLOR IMAGE GENERATION:

1. ORNAMENT PRESERVATION (MANDATORY - EXACT MATCH):
   - The ornament must remain EXACTLY identical to the uploaded ornament image
   - Do NOT modify, alter, or redesign the ornament in any way — its color, shape, texture, proportions, stones, pendant details, and ALL minute elements must remain EXACTLY the same
   - Preserve ALL minute details: every stone, gem, pendant, chain link, clasp, engraving, pattern, decorative element, and design feature
   - Every stone must be the same: size, cut, color, clarity, placement, and setting
   - Pendant details must be identical: shape, design, engravings, decorative elements
   - Chain links must be exact: size, style, pattern, and construction
   - Metal finish must match: gold tone, silver tone, plating, polish, and surface texture
   - The ornament must appear as if it's the exact same physical item from the uploaded image

2. ORNAMENT AS MAIN FOCUS (MANDATORY):
   - The ornament must be the PRIMARY SUBJECT and MAIN FOCUS of the image
   - Center the ornament in the frame or use rule-of-thirds for elegant composition
   - Ensure the ornament occupies a significant portion of the frame (at least 50-70% of visible area)
   - The ornament should be the dominant element that immediately draws attention
   - Background color should enhance but NEVER compete with or distract from the ornament

3. HIGHLIGHT AND ENHANCE ORNAMENT:
   - Use lighting, shadows, and composition to make the ornament stand out prominently against the colored background
   - Ensure the ornament is clearly visible and well-lit against the specified background color
   - Create visual contrast between the ornament and colored background to enhance visibility
   - Use depth of field to keep ornament sharp while colored background can have appropriate blur
   - Make sure every detail of the ornament is clearly visible and highlighted
   - The colored background should make the ornament pop and stand out

4. BACKGROUND COLOR APPLICATION:
   - Apply the specified background color ({bg_color}) EXACTLY as requested
   - The background color should be uniform and match the specified color precisely
   - Replace ONLY the background - the ornament itself must remain completely unchanged
   - The colored background should complement the ornament's colors and style
   - Ensure the background color doesn't clash with the ornament or obscure any details
   - Create seamless integration where shadows and lighting appear natural with the colored background

5. LIGHTING REQUIREMENTS:
   - Use balanced, professional lighting that highlights the ornament against the colored background
   - Create natural shadows that enhance ornament dimension without obscuring details
   - Ensure realistic reflections on metallic surfaces that match the ornament's material
   - Lighting should make every stone, texture, and design element clearly visible
   - Shadows should appear natural and consistent with the colored background's lighting direction
   - Avoid harsh shadows or overexposure that would hide ornament details
   - Lighting should create contrast that makes the ornament stand out from the colored background

6. DETAIL PRESERVATION:
   - Every stone, gem, or decorative element must be clearly visible and identical to the original
   - Chain links, clasps, and structural elements must maintain exact proportions
   - Engravings, patterns, and textures must be preserved exactly
   - Color accuracy is critical - match the exact hues, tones, and finishes from the uploaded image
   - Surface finishes (matte, glossy, brushed) must remain identical
   - All minute details must be preserved: clasps, hooks, connectors, decorative elements
   - The colored background should not affect or alter any ornament details

7. COLOR CONTRAST AND VISIBILITY:
   - Ensure the ornament is clearly visible against the specified background color
   - If the ornament and background colors are similar, use lighting and shadows to create distinction
   - Make sure the ornament doesn't blend into the background - it must stand out clearly
   - Use appropriate contrast techniques to ensure all ornament details remain visible
   - The background color should enhance ornament visibility, not diminish it

8. QUALITY STANDARDS:
   - Generate high-resolution, professional product photography quality
   - Ensure sharp focus on all ornament details
   - Maintain realistic proportions and perspective
   - Create seamless colored background integration that looks natural and professional
   - The final image should be suitable for marketing, advertising, or e-commerce use
   - The ornament should appear as the star of the image with maximum clarity and detail against the colored background""",
            "category": "images",
            "prompt_type": "background_replace",
            "is_active": True,
        },
        {
            "prompt_key": "images_background_change_default",
            "title": "Background Change Default Prompt",
            "description": "Default prompt for background change without color",
            "prompt_content": "Change only the background without modifying the ornament.",
            "rules": """RULES FOR BACKGROUND CHANGE DEFAULT IMAGE GENERATION:

1. ORNAMENT PRESERVATION (MANDATORY - EXACT MATCH):
   - The ornament must remain EXACTLY identical to the uploaded ornament image
   - Do NOT modify, alter, or redesign the ornament in any way — its color, shape, texture, proportions, stones, pendant details, and ALL minute elements must remain EXACTLY the same
   - Preserve ALL minute details: every stone, gem, pendant, chain link, clasp, engraving, pattern, decorative element, and design feature
   - Every stone must be the same: size, cut, color, clarity, placement, and setting
   - Pendant details must be identical: shape, design, engravings, decorative elements
   - Chain links must be exact: size, style, pattern, and construction
   - Metal finish must match: gold tone, silver tone, plating, polish, and surface texture
   - The ornament must appear as if it's the exact same physical item from the uploaded image

2. ORNAMENT AS MAIN FOCUS (MANDATORY):
   - The ornament must be the PRIMARY SUBJECT and MAIN FOCUS of the image
   - Center the ornament in the frame or use rule-of-thirds for elegant composition
   - Ensure the ornament occupies a significant portion of the frame (at least 50-70% of visible area)
   - The ornament should be the dominant element that immediately draws attention
   - Background should enhance but NEVER compete with or distract from the ornament

3. HIGHLIGHT AND ENHANCE ORNAMENT:
   - Use lighting, shadows, and composition to make the ornament stand out prominently
   - Ensure the ornament is clearly visible and well-lit against the new background
   - Create visual contrast between the ornament and background to enhance visibility
   - Use depth of field to keep ornament sharp while background can have appropriate blur
   - Make sure every detail of the ornament is clearly visible and highlighted

4. BACKGROUND REPLACEMENT ONLY:
   - Change ONLY the background - the ornament itself must remain completely unchanged
   - Do NOT modify the ornament in any way, shape, or form
   - The new background should complement the ornament's colors and style
   - Background should enhance ornament visibility without clashing or competing
   - Create seamless integration where shadows and lighting appear natural
   - Ensure the background doesn't obscure or hide any ornament details
   - Choose a background that makes the ornament the clear focal point

5. LIGHTING REQUIREMENTS:
   - Use balanced, professional lighting that highlights the ornament
   - Create natural shadows that enhance ornament dimension without obscuring details
   - Ensure realistic reflections on metallic surfaces that match the ornament's material
   - Lighting should make every stone, texture, and design element clearly visible
   - Shadows should appear natural and consistent with the background's lighting direction
   - Avoid harsh shadows or overexposure that would hide ornament details
   - Lighting should create contrast that makes the ornament stand out from the background

6. DETAIL PRESERVATION:
   - Every stone, gem, or decorative element must be clearly visible and identical to the original
   - Chain links, clasps, and structural elements must maintain exact proportions
   - Engravings, patterns, and textures must be preserved exactly
   - Color accuracy is critical - match the exact hues, tones, and finishes from the uploaded image
   - Surface finishes (matte, glossy, brushed) must remain identical
   - All minute details must be preserved: clasps, hooks, connectors, decorative elements
   - The background change should not affect or alter any ornament details

7. QUALITY STANDARDS:
   - Generate high-resolution, professional product photography quality
   - Ensure sharp focus on all ornament details
   - Maintain realistic proportions and perspective
   - Create seamless background integration that looks natural and professional
   - The final image should be suitable for marketing, advertising, or e-commerce use
   - The ornament should appear as the star of the image with maximum clarity and detail
   - The background should be professional and appropriate for product photography""",
            "category": "images",
            "prompt_type": "background_replace",
            "is_active": True,
        },
        {
            "prompt_key": "images_model_with_ornament",
            "title": "Model with Ornament Generation Prompt",
            "description": "Prompt for generating AI model images wearing ornaments",
            "prompt_content": """Generate a close-up, high-fashion portrait of an elegant Indian woman wearing this 100% real accurate uploaded ornament. Focus tightly on the neckline and jewelry area according to the ornament. 
Ensure the jewelry fits naturally and realistically on the model. 
Lighting should be soft and natural, highlighting the sparkle of the jewelry and the model's features. 
Use a shallow depth of field with a softly blurred background that hints at an elegant setting. 
Do not include any watermark, text, or unnatural effects. 
{ornament_description}{measurements_text} Make sure to follow the measurements strictly.
mandatory consideration details: {user_prompt}""",
            "category": "images",
            "prompt_type": "model_image",
            "is_active": True,
        },
        {
            "prompt_key": "images_real_model_with_ornament",
            "title": "Real Model with Ornament Generation Prompt",
            "description": "Prompt for generating images of real uploaded models wearing ornaments",
            "prompt_content": """Generate a realistic, high-quality close-up image of the uploaded model wearing the exact uploaded ornament. Keep the model's face fully intact and recognizable. 
Ensure the ornament fits naturally and realistically on the model. 
Generate a background suitable for both the model and the ornament. 
Lighting should be soft, natural, and elegant. 
Focus tightly on the jewelry area. 
Follow the pose from the uploaded pose image if provided. 
{ornament_description}{measurements_text}Additional user instructions: {user_prompt}""",
            "category": "images",
            "prompt_type": "model_image",
            "is_active": True,
        },
        {
            "prompt_key": "images_campaign_shot_ai",
            "title": "Campaign Shot AI Model Prompt",
            "description": "Prompt for generating campaign shots with AI models",
            "prompt_content": """Generate a high-quality campaign image of a model wearing all the uploaded ornaments. 
Use realistic lighting, texture, and cohesive fashion aesthetics. 
Campaign instructions: {user_prompt}""",
            "category": "images",
            "prompt_type": "campaign_image",
            "is_active": True,
        },
        {
            "prompt_key": "images_campaign_shot_real",
            "title": "Campaign Shot Real Model Prompt",
            "description": "Prompt for generating campaign shots with real uploaded models",
            "prompt_content": """Generate a realistic image of the uploaded real model wearing all the uploaded ornaments. 
Preserve the model's facial features and natural pose while making a small smile. 
Campaign instructions: {user_prompt}""",
            "category": "images",
            "prompt_type": "campaign_image",
            "is_active": True,
        },
    ]

    created_count = 0
    updated_count = 0

    for prompt_data in default_prompts:
        prompt_key = prompt_data["prompt_key"]
        existing = PromptMaster.objects(prompt_key=prompt_key).first()

        if existing:
            # Update existing prompt template if it's missing instructions/rules placeholders
            # This preserves user's instructions and rules but updates the template structure
            needs_update = False

            # Check if prompt_content needs placeholders added
            if prompt_key in ['generation_prompt_with_images', 'generation_prompt_simple']:
                if '{instructions}' not in existing.prompt_content or '{rules}' not in existing.prompt_content:
                    # Update the template to include placeholders
                    # Find where to insert (before "Generate prompts" line)
                    if 'Generate prompts for the following' in existing.prompt_content:
                        # Split at that point and insert placeholders
                        parts = existing.prompt_content.split(
                            'Generate prompts for the following', 1)
                        if len(parts) == 2:
                            # Check if placeholders already exist between parts
                            if '{instructions}' not in parts[0] and '{rules}' not in parts[0]:
                                existing.prompt_content = parts[0].rstrip(
                                ) + '\n\n{instructions}\n\n{rules}\n{global_instruction_rule}\n\nGenerate prompts for the following' + parts[1]
                                needs_update = True
                    elif '{instructions}' not in existing.prompt_content:
                        # Add placeholders at the end before JSON section
                        if 'Respond ONLY in valid JSON' in existing.prompt_content:
                            existing.prompt_content = existing.prompt_content.replace(
                                'Respond ONLY in valid JSON',
                                '{instructions}\n\n{rules}\n{global_instruction_rule}\n\nRespond ONLY in valid JSON'
                            )
                            needs_update = True

            # Update instructions and rules if they're empty but defaults exist
            # Also update rules if new comprehensive rules are provided (for template prompts)
            if prompt_data.get("instructions") and not existing.instructions:
                existing.instructions = prompt_data.get("instructions", "")
                needs_update = True
            if prompt_data.get("rules"):
                # For template prompts, always update rules if new comprehensive rules are provided
                if existing.prompt_type in ['white_background', 'background_replace', 'model_image', 'campaign_image']:
                    if not existing.rules or len(prompt_data.get("rules", "")) > len(existing.rules or ""):
                        existing.rules = prompt_data.get("rules", "")
                        needs_update = True
                elif not existing.rules:
                    existing.rules = prompt_data.get("rules", "")
                    needs_update = True

            if needs_update:
                existing.save()
                print(
                    f"Updated prompt '{prompt_key}' with new template structure")
                updated_count += 1
            else:
                print(f"Prompt '{prompt_key}' already exists, skipping update")
                updated_count += 1
        else:
            # Create new prompt
            try:
                prompt = PromptMaster(
                    prompt_key=prompt_key,
                    title=prompt_data["title"],
                    description=prompt_data.get("description", ""),
                    prompt_content=prompt_data["prompt_content"],
                    instructions=prompt_data.get("instructions", ""),
                    rules=prompt_data.get("rules", ""),
                    category=prompt_data["category"],
                    prompt_type=prompt_data.get("prompt_type"),
                    is_active=prompt_data.get("is_active", True),
                    created_by=system_user,
                    updated_by=system_user,
                )
                prompt.save()
                created_count += 1
                print(
                    f"Created prompt: {prompt_key} (category: {prompt_data['category']})")
            except Exception as e:
                print(f"Error creating prompt '{prompt_key}': {e}")
                # Continue with other prompts even if one fails

    print("\n✅ Prompt initialization complete!")
    print(f"   Created: {created_count} prompts")
    print(f"   Already existed: {updated_count} prompts")

    return created_count, updated_count


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
