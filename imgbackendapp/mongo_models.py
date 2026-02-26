# # # imgbackendapp/mongo_models.py
# # from mongoengine import Document, StringField, URLField, DateTimeField, BinaryField
# # import datetime


# # class OrnamentMongo(Document):
# #     prompt = StringField(required=True, max_length=255)
# #     image_url = URLField(required=True)  # Cloudinary URL of generated image
# #     # image_data = BinaryField(required=True)
# #     created_at = DateTimeField(default=datetime.datetime.utcnow)

# #     meta = {"collection": "jewellery"}


# from mongoengine import Document, StringField, URLField, DateTimeField
# import datetime


# class OrnamentMongo(Document):
#     prompt = StringField(required=True, max_length=255)
#     type = StringField(required=True, max_length=255)
#     model_image_url = URLField(required=True)
#     # URLs (Cloudinary)
#     uploaded_image_url = URLField(required=True)
#     generated_image_url = URLField(required=True)

#     # Local paths
#     uploaded_image_path = StringField()
#     generated_image_path = StringField()

#     created_at = DateTimeField(default=datetime.datetime.utcnow)

#     meta = {"collection": "jewellery"}


from mongoengine import Document, StringField, DateTimeField, ListField, ReferenceField, ObjectIdField
import datetime


class OrnamentMongo(Document):
    prompt = StringField(required=True)
    type = StringField(required=True, max_length=255)

    # User tracking
    user_id = StringField()  # Store user ID from JWT token
    created_by = ReferenceField("User")
    updated_by = ReferenceField("User")

    # Regeneration tracking - reference to parent image if this is a regeneration
    parent_image_id = ObjectIdField()
    original_prompt = StringField()  # Store the original prompt for context

    # Single model image (only for campaign)
    # Can be either an absolute URL (http/https) or a local /media/... path
    model_image_url = StringField()

    # Single uploaded image (for 4 basic types)
    # Can be either an absolute URL (http/https) or a local /media/... path
    uploaded_image_url = StringField()

    # Multiple uploaded ornaments (for campaign)
    # Can be either absolute URLs or local /media/... paths
    uploaded_ornament_urls = ListField(StringField())

    # Generated image
    # Can be either an absolute URL (http/https) or a local /media/... path
    generated_image_url = StringField(required=True)

    # Local paths
    uploaded_image_path = StringField()
    generated_image_path = StringField()

    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    # Analyzed reference description (background/pose/theme) for use in regeneration
    reference_analysis = StringField()

    meta = {
        "collection": "jewellery",
        "strict": False,  # Allow extra fields for backward compatibility
        "allow_inheritance": False
    }
