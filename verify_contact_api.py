
import requests
import json

url = "http://127.0.0.1:8000/api/homepage/contact/"

payload = {
    "name": "Test User",
    "mobile": "1234567890",
    "email": "test@example.com",
    "reason": "This is a test submission from verification script."
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        print("✅ Success! Contact form submitted.")
    else:
        print("❌ Failed to submit contact form.")

except Exception as e:
    print(f"❌ Error: {e}")
