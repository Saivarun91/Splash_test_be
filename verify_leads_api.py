from datetime import datetime
import json
import requests # Keeping this as it's not part of Django setup and not explicitly removed
from payments.models import ContactSalesSubmission
from users.models import User, Role
from payments.views import get_all_sales_leads
from django.test import RequestFactory
from django.http import HttpRequest # Added as per instruction

def verify_leads_api():
    print("Verifying Lead Generation API...")
    
    # 1. Create a dummy sales submission
    print("\n1. Creating dummy sales submission...")
    try:
        submission = ContactSalesSubmission(
            first_name="Test",
            last_name="Lead",
            work_email="test.lead@example.com",
            phone="1234567890",
            company_website="https://example.com",
            problems_trying_to_solve="Testing lead generation",
            users_to_onboard="10",
            timeline="Immediately",
            created_at=datetime.utcnow()
        )
        submission.save()
        print(f"Created submission: {submission}")
    except Exception as e:
        print(f"FAILED to create submission: {e}")
        return

    # 2. Test Admin API access
    print("\n2. Testing Admin API access...")
    try:
        # We need a valid token to test the API. 
        # Since generating a token might be complex in this script without a user password,
        # we will rely on internal Django view testing or assume manual verification for the full API stack if token generation fails.
        
        # However, we can test the view function directly if we mock the request
        from payments.views import get_all_sales_leads
        from django.test import RequestFactory
        
        # Get an admin user
        admin_user = User.objects(role=Role.ADMIN).first()
        if not admin_user:
            print("No admin user found. Creating one...")
            admin_user = User(
                email="admin@test.com",
                username="admintest",
                role=Role.ADMIN
            )
            admin_user.set_password("admin123")
            admin_user.save()
            
        print(f"Using admin user: {admin_user.email}")
        
        factory = RequestFactory()
        request = factory.get('/api/payments/admin/leads/')
        request.user = admin_user
        
        response = get_all_sales_leads(request)
        
        print(f"API Response Status Code: {response.status_code}")
        
        if response.status_code == 200:
            content = json.loads(response.content)
            print(f"Success: {content.get('success')}")
            print(f"Count: {content.get('count')}")
            
            leads = content.get('leads', [])
            found = False
            for lead in leads:
                if lead['work_email'] == "test.lead@example.com":
                    print("Found the test lead in the response!")
                    found = True
                    break
            
            if found:
                 print(" verification PASSED")
            else:
                 print(" verification FAILED: Test lead not found in response")

        else:
            print(f"API Request Failed: {response.content}")

    except Exception as e:
        print(f"Verification FAILED: {e}")
        import traceback
        traceback.print_exc()

    # Clean up
    print("\nCleaning up...")
    try:
        submission.delete()
        print("Deleted test submission")
    except:
        pass

verify_leads_api()
