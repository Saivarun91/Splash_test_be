#!/usr/bin/env python3
"""
Test script for image regeneration functionality
Run this to verify that the regeneration feature is working correctly
"""

import requests
import json
import os
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:8000/imgbackendapp"
TOKEN = None  # Set this to your JWT token


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


def print_result(result, success=True):
    """Print formatted result"""
    symbol = "✅" if success else "❌"
    print(f"{symbol} {json.dumps(result, indent=2)}")


def get_token():
    """Get JWT token from user or environment"""
    global TOKEN

    if TOKEN:
        return TOKEN

    # Try to get from environment
    TOKEN = os.environ.get('JWT_TOKEN')

    if not TOKEN:
        print("\n⚠️  No JWT token found!")
        print("Please set your JWT token:")
        print("  1. In this script: TOKEN = 'your_token_here'")
        print("  2. As environment variable: export JWT_TOKEN='your_token_here'")
        print("  3. Enter it now:")
        TOKEN = input("JWT Token: ").strip()

    return TOKEN


def get_headers():
    """Get request headers with authentication"""
    token = get_token()
    return {
        'Authorization': f'Bearer {token}'
    }


def test_upload_ornament():
    """Test uploading an ornament"""
    print_section("Test 1: Upload Ornament")

    # Check if test image exists
    test_image_path = Path("media/uploads")
    if not test_image_path.exists():
        print("❌ No test images found in media/uploads/")
        print("Please ensure you have some test images in the media/uploads directory")
        return None

    # Get first image file
    image_files = list(test_image_path.glob(
        "*.jpg")) + list(test_image_path.glob("*.jpeg")) + list(test_image_path.glob("*.png"))

    if not image_files:
        print("❌ No image files found")
        return None

    test_image = image_files[0]
    print(f"📁 Using test image: {test_image}")

    try:
        with open(test_image, 'rb') as f:
            files = {'image': f}
            data = {
                'prompt': 'Test upload - make it elegant',
                'background_color': 'white'
            }

            response = requests.post(
                f"{BASE_URL}/",
                headers=get_headers(),
                files=files,
                data=data,
                timeout=60
            )

        if response.status_code == 200:
            result = response.json()
            print_result(result, True)
            return result
        else:
            print_result(response.json(), False)
            print(f"Status Code: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def test_regenerate_image(image_id):
    """Test regenerating an image"""
    print_section("Test 2: Regenerate Image")

    if not image_id:
        print("❌ No image_id provided. Cannot test regeneration.")
        return None

    print(f"🔄 Regenerating image: {image_id}")

    try:
        data = {
            'image_id': image_id,
            'prompt': 'Add more sparkle and brightness'
        }

        response = requests.post(
            f"{BASE_URL}/regenerate/",
            headers=get_headers(),
            data=data,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            print_result(result, True)
            return result
        else:
            print_result(response.json(), False)
            print(f"Status Code: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def test_regenerate_again(image_id):
    """Test regenerating a regenerated image"""
    print_section("Test 3: Regenerate Again (Chain)")

    if not image_id:
        print("❌ No image_id provided. Cannot test second regeneration.")
        return None

    print(f"🔄 Regenerating image again: {image_id}")

    try:
        data = {
            'image_id': image_id,
            'prompt': 'Make it more vibrant with gold accents'
        }

        response = requests.post(
            f"{BASE_URL}/regenerate/",
            headers=get_headers(),
            data=data,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            print_result(result, True)
            return result
        else:
            print_result(response.json(), False)
            print(f"Status Code: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def test_get_user_images():
    """Test fetching user images"""
    print_section("Test 4: Get User Images")

    try:
        response = requests.get(
            f"{BASE_URL}/user-images/",
            headers=get_headers(),
            params={'page': 1, 'limit': 10},
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print_result(result, True)
            return result
        else:
            print_result(response.json(), False)
            print(f"Status Code: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def test_filter_by_type():
    """Test filtering images by type"""
    print_section("Test 5: Filter Images by Type")

    try:
        response = requests.get(
            f"{BASE_URL}/user-images/",
            headers=get_headers(),
            params={'type': 'white_background', 'page': 1, 'limit': 5},
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print_result(result, True)
            return result
        else:
            print_result(response.json(), False)
            print(f"Status Code: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def print_summary(results):
    """Print test summary"""
    print_section("Test Summary")

    passed = sum(1 for r in results.values() if r is not None)
    total = len(results)

    print(f"\n📊 Results: {passed}/{total} tests passed\n")

    for test_name, result in results.items():
        status = "✅ PASS" if result is not None else "❌ FAIL"
        print(f"  {status} - {test_name}")

    if passed == total:
        print("\n🎉 All tests passed! Regeneration feature is working correctly!")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")


def main():
    """Run all tests"""
    print("\n" + "🧪"*30)
    print("  Image Regeneration Test Suite")
    print("🧪"*30)

    results = {}

    # Test 1: Upload ornament
    upload_result = test_upload_ornament()
    results["Upload Ornament"] = upload_result

    if not upload_result or not upload_result.get('success'):
        print("\n⚠️  Upload failed. Cannot continue with regeneration tests.")
        print_summary(results)
        return

    # Get image ID (try mongo_id or ornament_id)
    image_id = upload_result.get(
        'mongo_id') or upload_result.get('ornament_id')

    if not image_id:
        print("\n⚠️  No image ID in response. Cannot continue.")
        print_summary(results)
        return

    # Test 2: Regenerate image
    regen_result = test_regenerate_image(str(image_id))
    results["Regenerate Image"] = regen_result

    # Test 3: Regenerate again (chain)
    if regen_result and regen_result.get('success'):
        regen_id = regen_result.get('mongo_id')
        regen_again_result = test_regenerate_again(str(regen_id))
        results["Regenerate Chain"] = regen_again_result
    else:
        results["Regenerate Chain"] = None

    # Test 4: Get user images
    user_images_result = test_get_user_images()
    results["Get User Images"] = user_images_result

    # Test 5: Filter by type
    filter_result = test_filter_by_type()
    results["Filter by Type"] = filter_result

    # Print summary
    print_summary(results)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
