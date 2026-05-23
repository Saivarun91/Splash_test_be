
from django.core.management.base import BaseCommand
from payments.models import ContactSalesSubmission
from users.models import User, Role
from payments.views import get_all_sales_leads
from django.test import RequestFactory
import json
from datetime import datetime

class Command(BaseCommand):
    help = 'Verify Lead Generation API'

    def handle(self, *args, **options):
        self.stdout.write("Verifying Lead Generation API...")
        
        # 1. Create a dummy sales submission
        self.stdout.write("\n1. Creating dummy sales submission...")
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
            self.stdout.write(f"Created submission: {submission}")
        except Exception as e:
            self.stderr.write(f"FAILED to create submission: {e}")
            return

        # 2. Test Admin API access
        self.stdout.write("\n2. Testing Admin API access...")
        try:
            # Get an admin user
            admin_user = User.objects(role=Role.ADMIN).first()
            if not admin_user:
                self.stdout.write("No admin user found. Creating one...")
                admin_user = User(
                    email="admin@test.com",
                    username="admintest",
                    role=Role.ADMIN
                )
                admin_user.set_password("admin123")
                admin_user.save()
                
            self.stdout.write(f"Using admin user: {admin_user.email}")
            
            factory = RequestFactory()
            request = factory.get('/api/payments/admin/leads/')
            request.user = admin_user
            
            response = get_all_sales_leads(request)
            
            self.stdout.write(f"API Response Status Code: {response.status_code}")
            
            if response.status_code == 200:
                content = json.loads(response.content)
                self.stdout.write(f"Success: {content.get('success')}")
                self.stdout.write(f"Count: {content.get('count')}")
                
                leads = content.get('leads', [])
                found = False
                for lead in leads:
                    if lead['work_email'] == "test.lead@example.com":
                        self.stdout.write("Found the test lead in the response!")
                        found = True
                        break
                
                if found:
                     self.stdout.write(self.style.SUCCESS("Verification PASSED"))
                else:
                     self.stderr.write(self.style.ERROR("Verification FAILED: Test lead not found in response"))

            else:
                self.stderr.write(f"API Request Failed: {response.content}")

        except Exception as e:
            self.stderr.write(f"Verification FAILED: {e}")
            import traceback
            traceback.print_exc()

        # Clean up
        self.stdout.write("\nCleaning up...")
        try:
            submission.delete()
            self.stdout.write("Deleted test submission")
        except:
            pass
