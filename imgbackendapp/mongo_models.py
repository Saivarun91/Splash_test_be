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


from mongoengine import Document, StringField, URLField, DateTimeField, ListField, ReferenceField, ObjectIdField
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
    model_image_url = URLField()

    # Single uploaded image (for 4 basic types)
    uploaded_image_url = URLField()

    # Multiple uploaded ornaments (for campaign)
    uploaded_ornament_urls = ListField(URLField())

    # Generated image
    generated_image_url = URLField(required=True)

    # Local paths
    uploaded_image_path = StringField()
    generated_image_path = StringField()

    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    meta = {"collection": "jewellery"}
