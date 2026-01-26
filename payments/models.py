from mongoengine import Document, StringField, IntField, DateTimeField, ReferenceField, FloatField
from datetime import datetime


class PaymentTransaction(Document):
    """Track payment transactions for organizations"""
    organization = ReferenceField("Organization", required=True)
    user = ReferenceField("User", required=True)  # User who initiated payment
    plan = ReferenceField("Plan")  # Plan subscription (if this is a plan purchase)
    
    # Payment details
    amount = FloatField(required=True)  # Amount in INR
    credits = IntField(required=True)  # Credits purchased
    currency = StringField()
    
    # Razorpay details
    razorpay_order_id = StringField(required=True, unique=True)
    razorpay_payment_id = StringField()
    razorpay_signature = StringField()
    
    # Status
    status = StringField(choices=["pending", "completed", "failed", "refunded"], default="pending")
    
    # Metadata
    metadata = StringField()  # JSON string for additional data
    
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        "collection": "payment_transactions",
        "strict": False,
        "allow_inheritance": False,
        "indexes": ["razorpay_order_id", "organization", "status"]
    }
    
    def __str__(self):
        return f"Payment {self.razorpay_order_id} - {self.status}"
