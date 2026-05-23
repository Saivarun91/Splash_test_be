#!/usr/bin/env python3
"""
Script to verify generated images are valid
"""
import os
from PIL import Image

def verify_generated_images():
    """Check all generated images for validity"""
    generated_dir = "media/generated"
    
    if not os.path.exists(generated_dir):
        print("❌ Generated directory not found")
        return
    
    print("🔍 Checking generated images...")
    
    for filename in os.listdir(generated_dir):
        if filename.endswith('.jpg'):
            filepath = os.path.join(generated_dir, filename)
            file_size = os.path.getsize(filepath)
            
            print(f"\n📁 {filename}:")
            print(f"   Size: {file_size} bytes")
            
            if file_size < 1000:
                print("   ⚠️  WARNING: File too small, likely corrupted")
                continue
            
            try:
                with Image.open(filepath) as img:
                    print(f"   ✅ Valid image: {img.size}, mode: {img.mode}")
                    print(f"   📊 Format: {img.format}")
            except Exception as e:
                print(f"   ❌ ERROR: Invalid image - {e}")
    
    print("\n✅ Verification complete!")

if __name__ == "__main__":
    verify_generated_images()
