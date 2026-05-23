
from pymongo import MongoClient

def check_db():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tarnika']
    col = db['legal_compliance']
    
    print(f"Database: tarnika")
    print(f"Collection: legal_compliance")
    count = col.count_documents({})
    print(f"Count: {count}")
    
    for doc in col.find():
        print(f"Found: {doc.get('content_type')} - {doc.get('title')}")

if __name__ == '__main__':
    check_db()
