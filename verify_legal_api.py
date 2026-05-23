
import requests
import json

base_url = "http://127.0.0.1:8000/api/legal"

endpoints = ["terms", "privacy"]

for endpoint in endpoints:
    url = f"{base_url}/{endpoint}/"
    print(f"Testing {url}...")
    try:
        response = requests.get(url)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ Success! Title: {data.get('content', {}).get('title')}")
            else:
                print(f"❌ Failed: {data.get('error')}")
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Exception: {e}")
    print("-" * 20)
