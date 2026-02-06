
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "imgbackend.settings")
django.setup()

from legal.models import LegalCompliance

def seed_legal():
    data = [
        {
            'content_type': 'terms',
            'title': 'Terms and Conditions',
            'content': '<h3>Terms and Conditions</h3><p>Welcome to our service. These are the terms...</p>'
        },
        {
            'content_type': 'privacy',
            'title': 'Privacy Policy',
            'content': '<h3>Privacy Policy</h3><p>Your privacy is important to us...</p>'
        },
        {
            'content_type': 'gdpr',
            'title': 'GDPR Compliance',
            'content': '<h3>GDPR Compliance</h3><p>We are GDPR compliant...</p>'
        }
    ]

    for item in data:
        obj = LegalCompliance.objects(content_type=item['content_type']).first()
        if not obj:
            LegalCompliance(**item).save()
            print(f"Created {item['content_type']}")
        else:
            print(f"Updated {item['content_type']}")
            obj.title = item['title']
            obj.content = item['content']
            obj.save()

if __name__ == '__main__':
    seed_legal()
