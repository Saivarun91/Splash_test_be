#!/usr/bin/env python3
"""
Test script for ornament extraction and background removal
"""
import os
import sys
import django
from PIL import Image
import numpy as np
import cv2
from io import BytesIO

# Add Django project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'imgbackend.settings')
django.setup()

def test_background_removal(image_path):
    """Test ornament extraction and background removal"""
    try:
        print(f"Testing background removal on: {image_path}")

        # Load image
        original = Image.open(image_path).convert("RGB")
        img_array = np.array(original)

        # Convert RGB to BGR for OpenCV
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # Convert to grayscale & blur
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5,5), 0)

        # Threshold (invert: object=white)
        _, thresh = cv2.threshold(blur, 240, 255, cv2.THRESH_BINARY_INV)

        # Morphology to clean up small noise
        kernel = np.ones((3,3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours and select largest (assume ornament)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise Exception("No contours found for ornament.")
        largest_contour = max(contours, key=cv2.contourArea)

        # Create mask from contour
        mask = np.zeros_like(gray)
        cv2.drawContours(mask, [largest_contour], -1, 255, -1)

        # Smooth mask edges
        mask = cv2.GaussianBlur(mask, (5,5), 0)

        # Add alpha channel
        rgba_array = np.dstack((img_array, mask))
        transparent_img = Image.fromarray(rgba_array, 'RGBA')

        # Paste on white background
        white_bg = Image.new("RGB", original.size, (255, 255, 255))
        white_bg.paste(transparent_img, mask=transparent_img.split()[3])

        # Save result
        output_path = os.path.splitext(image_path)[0] + "_processed.jpg"
        white_bg.save(output_path, format="JPEG", quality=95)

        print(f"✅ Ornament extraction completed! Saved to: {output_path}")
        return True

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error during ornament extraction: {str(e)}")
        return False

if __name__ == "__main__":
    # Example test images
    test_images = [
        "media/ornaments/Gemini_Generated_Image_2rvxph2rvxph2rvx_1-pica.png",
        "media/ornaments/Gemini_Generated_Image_8x66ou8x66ou8x66.png",
    ]

    for img_path in test_images:
        if os.path.exists(img_path):
            test_background_removal(img_path)
            break
    else:
        print("No test images found. Upload an image first.")
