from mongoengine import Document, ReferenceField, IntField, StringField, DateTimeField, DictField
from datetime import datetime


class CreditLedger(Document):
    user = ReferenceField("User", required=True)
    organization = ReferenceField("Organization", required=True)
    project = ReferenceField("Project", required=False)
    change_type = StringField(choices=["debit", "credit"], required=True)
    credits_changed = IntField(required=True)
    balance_after = IntField(required=True)
    reason = StringField()
    metadata = DictField()
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "credit_ledger",
        "strict": False,  # Allow extra fields for backward compatibility
        "allow_inheritance": False
    }
    
    def __str__(self):
        return f"{self.organization.name} - {self.change_type} - {self.credits_changed}"
