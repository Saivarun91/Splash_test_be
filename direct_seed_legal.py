
from pymongo import MongoClient
from datetime import datetime

def seed_legal_direct():
    # Use the URI from settings.py
    uri = "mongodb+srv://bhargavraavi4444_db_user:bhargav4444@cluster0.5dfeawc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    print(f"Connecting to Atlas: {uri.split('@')[1]}") # Hide credentials in log
    
    client = MongoClient(uri)
    target_db = client['tarnika']
    target_col = target_db['legal_compliance']
    
    potential_dbs = [] # Unused now
    print("Updating 'legal_compliance' collection in 'tarnika' database...")

    data = [
        {
            'content_type': 'terms',
            'title': 'Terms and Conditions',
            'content': '''
<div class="space-y-6 text-gray-700">
    <p>Last Updated: 24th December 2025</p>
    <p>Welcome to our service. Please read these terms carefully before using our platform.</p>

    <h3 class="text-xl font-bold text-gray-900 mt-6">1. Acceptance of Terms</h3>
    <p>By accessing and using this website, you accept and agree to be bound by the terms and provision of this agreement.</p>

    <h3 class="text-xl font-bold text-gray-900 mt-6">2. Use License</h3>
    <ul class="list-disc pl-5 space-y-2">
        <li>Permission is granted to temporarily download one copy of the materials (information or software) on the website for personal, non-commercial transitory viewing only.</li>
        <li>This is the grant of a license, not a transfer of title.</li>
        <li>This license shall automatically terminate if you violate any of these restrictions.</li>
    </ul>

    <h3 class="text-xl font-bold text-gray-900 mt-6">3. Disclaimer</h3>
    <p>The materials on the website are provided "as is". We make no warranties, expressed or implied, and hereby disclaim and negate all other warranties, including without limitation, implied warranties or conditions of merchantability, fitness for a particular purpose, or non-infringement of intellectual property or other violation of rights.</p>

    <h3 class="text-xl font-bold text-gray-900 mt-6">4. Limitations</h3>
    <p>In no event shall we or our suppliers be liable for any damages (including, without limitation, damages for loss of data or profit, or due to business interruption) arising out of the use or inability to use the materials on the website.</p>
</div>
            '''
        },
        {
            'content_type': 'privacy',
            'title': 'Privacy Policy',
            'content': '''
<div class="space-y-6 text-gray-700">
    <p>Last Updated: 24th December 2025</p>
    <p>This Privacy Policy describes how TutorKhoj Private Limited ("Company", "we", "us", "our") collects, uses, stores, and protects information of users ("you", "your") who access or use our platform.</p>

    <h3 class="text-xl font-bold text-gray-900 mt-6">1. Information We Collect</h3>
    <p><strong>a) Personal Information</strong><br>When you register or use the Platform, we may collect:</p>
    <ul class="list-disc pl-5 space-y-2">
        <li>Full Name</li>
        <li>Email Address</li>
        <li>Phone Number</li>
        <li>Login credentials</li>
    </ul>
    
    <p class="mt-4"><strong>b) Search & Usage Data</strong><br>We collect data regarding your interactions with our AI services to improve model performance and user experience.</p>

    <h3 class="text-xl font-bold text-gray-900 mt-6">2. Purpose of Data Collection</h3>
    <p>We use your information to:</p>
    <ul class="list-disc pl-5 space-y-2">
        <li>Create and manage user accounts</li>
        <li>Provide access to our services</li>
        <li>Process payments</li>
        <li>Send notifications and updates</li>
        <li>Improve platform performance</li>
    </ul>

    <h3 class="text-xl font-bold text-gray-900 mt-6">3. Cookies & Analytics</h3>
    <p>We use cookies and similar technologies to maintain login sessions, analyze traffic, and improve user experience. You may disable cookies via browser settings, but certain features may not function properly.</p>

    <h3 class="text-xl font-bold text-gray-900 mt-6">4. Contact Information</h3>
    <p>For any privacy-related queries, please contact us at <a href="mailto:support@findmyguru.com" class="text-blue-600 hover:underline">support@findmyguru.com</a>.</p>
</div>
            '''
        }
    ]

    for item in data:
        # Update or Insert
        result = target_col.update_one(
            {'content_type': item['content_type']},
            {'$set': {
                'title': item['title'],
                'content': item['content'],
                'updated_at': datetime.utcnow()
            }},
            upsert=True
        )
        print(f"Processed {item['content_type']}: Matched={result.matched_count}, Modified={result.modified_count}, Upserted={result.upserted_id}")

if __name__ == '__main__':
    seed_legal_direct()
