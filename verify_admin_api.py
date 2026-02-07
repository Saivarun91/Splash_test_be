import os
import django
import json
import sys

# Setup Django Environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'imgbackend.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from homepage.views import get_all_support_requests
from users.models import Role

User = get_user_model()

def verify_admin_api():
    print(">> Verifying Admin API Access...")
    
    # 1. Get Admin User
    admin_email = "admin_help@example.com"
    try:
        admin = User.objects.get(email=admin_email)
        print(f"[OK] Found admin user: {admin_email}")
    except User.DoesNotExist:
        print(f"[FAIL] Admin user {admin_email} not found. Run verify_help_center.py first.")
        return

    # 2. Test Admin View (get_all_support_requests)
    print("\n>> Testing get_all_support_requests with Admin User...")
    factory = RequestFactory()
    request = factory.get('/api/homepage/support/all/')
    request.user = admin
    
    response = get_all_support_requests(request)
    print(f"Response Status: {response.status_code}")
    
    if response.status_code == 200:
        content = json.loads(response.content.decode())
        if content.get('success'):
            print(f"[OK] Success. Found {len(content.get('requests', []))} requests.")
            for req in content.get('requests', [])[:3]: # Show first 3
                print(f"   - {req['type'].upper()}: {req['name']} ({req['email']})")
        else:
            print(f"[FAIL] API returned success=False: {content}")
    else:
        print(f"[FAIL] Status code {response.status_code}")
        print(response.content.decode())

if __name__ == "__main__":
    verify_admin_api()
