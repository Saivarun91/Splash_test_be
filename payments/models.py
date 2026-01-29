from mongoengine import (
    Document,
    StringField,
    IntField,
    DateTimeField,
    ReferenceField,
    FloatField,
)
from datetime import datetime


class PaymentTransaction(Document):
    """Track payment transactions for organizations and individual users"""
    organization = ReferenceField("Organization", required=False)  # Optional for single users
    user = ReferenceField("User", required=True)  # User who initiated payment
    plan = ReferenceField("Plan")  # Plan subscription (if this is a plan purchase)
    
    # Payment details
    # Base amount (before GST) in INR
    amount = FloatField(required=True)
    credits = IntField(required=True)  # Credits purchased
    currency = StringField()

    # Billing details captured from user before payment
    billing_name = StringField()
    billing_address = StringField()
    billing_phone = StringField()
    billing_gst_number = StringField()
    billing_type = StringField(choices=["individual", "business"], default="individual")

    # Tax details (at time of payment)
    tax_rate = FloatField()  # GST percentage used
    tax_amount = FloatField()  # GST amount in INR
    total_amount = FloatField()  # Final amount charged (amount + tax_amount)
    
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
