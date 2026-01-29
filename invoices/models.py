from mongoengine import Document, StringField, FloatField, IntField


class InvoiceConfig(Document):
    """
    Stores global invoice and taxation configuration used for GST calculations.
    Single-document collection – the latest document is treated as active config.
    """

    company_name = StringField(default="Splash Ai Studio")
    invoice_prefix = StringField(default="INV-")
    tax_rate = FloatField(default=18.0)  # GST percentage

    bank_name = StringField(default="Borcelle Bank")
    account_name = StringField(default="Studio Shodwe")
    account_number = StringField(default="123-456-7890")

    # Number of days from invoice date to compute "pay by" date
    pay_by_date = IntField(default=30)

    terms_and_conditions = StringField(
        default="Late payments may result in a 2% penalty fee."
    )

    meta = {
        "collection": "invoice_config",
        "strict": False,
        "allow_inheritance": False,
    }

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"InvoiceConfig(tax_rate={self.tax_rate})"

