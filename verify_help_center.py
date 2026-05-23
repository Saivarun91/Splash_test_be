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
from homepage.views import submit_support_request, get_all_support_requests
from homepage.models import ContactSubmission
from users.models import Role

User = get_user_model()

def verify_help_center():
    print(">> Starting Help Center Verification...")
    
    # 1. Setup Test User
    email = "test_user_help@example.com"
    user, created = User.objects.get_or_create(email=email)
    if created:
        user.username = "test_user_help"
        user.set_password("password123")
        user.role = Role.USER
        user.save()
        print(f"[OK] Created test user: {email}")
    else:
        print(f"[INFO] Used existing test user: {email}")

    # 2. Setup Admin User (for checking admin view)
    admin_email = "admin_help@example.com"
    admin, admin_created = User.objects.get_or_create(email=admin_email)
    if admin_created:
        admin.username = "admin_help"
        admin.set_password("admin123")
        admin.role = Role.ADMIN
        admin.save()
        print(f"[OK] Created admin user: {admin_email}")
    else:
        admin.role = Role.ADMIN # Ensure is admin
        admin.save()
        print(f"[INFO] Used existing admin user: {admin_email}")

    # 3. Test Submit Support Request
    print("\n>> Testing submit_support_request...")
    factory = RequestFactory()
    data = {"reason": "This is a verification support request."}
    request = factory.post(
        '/api/homepage/help/submit/',
        data=json.dumps(data),
        content_type='application/json'
    )
    request.user = user
    
    response = submit_support_request(request)
    print(f"Response Status: {response.status_code}")
    print(f"Response Content: {response.content.decode()}")
    
    if response.status_code == 200:
        print("[OK] submit_support_request passed")
    else:
        print("[FAIL] submit_support_request failed")
        return

    # 4. Verify Database Entry
    print("\n>> Verifying Database Entry...")
    latest_submission = ContactSubmission.objects(email=user.email).order_by('-created_at').first()
    if latest_submission and latest_submission.type == 'support' and latest_submission.user.id == user.id:
        print(f"[OK] Database entry found: {latest_submission}")
        print(f"   - Type: {latest_submission.type}")
        print(f"   - User: {latest_submission.user.email}")
    else:
        print("[FAIL] Database entry verification failed")
        return

    # 5. Test Admin View (get_all_support_requests)
    print("\n>> Testing get_all_support_requests...")
    request_admin = factory.get('/api/homepage/support/all/')
    request_admin.user = admin
    
    response_admin = get_all_support_requests(request_admin)
    content = json.loads(response_admin.content.decode())
    
    if response_admin.status_code == 200 and content.get('success'):
        print("[OK] get_all_support_requests passed")
        requests = content.get('requests', [])
        found = False
        for req in requests:
            if req['id'] == str(latest_submission.id):
                found = True
                print(f"[OK] Found the submitted request in Admin response: ID {req['id']}")
                break
        if not found:
            print("[FAIL] Submittted request NOT found in Admin response")
    else:
        print(f"[FAIL] get_all_support_requests failed: {response_admin.status_code}")
        print(response_admin.content.decode())

    print("\n[DONE] Verification Complete!")

if __name__ == "__main__":
    try:
        verify_help_center()
    except Exception as e:
        print(f"[ERROR] Error during verification: {e}")
        import traceback
        traceback.print_exc()
