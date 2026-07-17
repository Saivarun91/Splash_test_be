"""
Homepage Content API views
Admin-only endpoints for managing homepage content (Before/After images)
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
import os
from pathlib import Path
from mongoengine.errors import DoesNotExist, ValidationError
from .models import BeforeAfterImage, PageContent, BlogPost, PublicGalleryImage
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime
from django.conf import settings
import cloudinary.uploader
from imgbackendapp.file_utils import resolve_media_path, to_media_db_path


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN


# =====================
# Get All Before/After Images
# =====================
@api_view(['GET'])
@csrf_exempt
def get_before_after_images(request):
    """
    Get all before/after images
    Public endpoint - can be used by frontend to display images
    """
    try:
        # Get all active images ordered by order field
        images = BeforeAfterImage.objects(is_active='true').order_by('order', '-created_at')
        
        image_list = []
        for img in images:
            image_list.append({
                'id': str(img.id),
                'before_image_url': img.before_image_url,
                'after_image_url': img.after_image_url,
                'order': img.order,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'updated_at': img.updated_at.isoformat() if img.updated_at else None,
            })
        
        return JsonResponse({
            'success': True,
            'images': image_list
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Get All Before/After Images (Admin)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_all_before_after_images(request):
    """
    Get all before/after images including inactive ones
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access this endpoint'}, status=403)
    
    try:
        # Get all images ordered by order field
        images = BeforeAfterImage.objects().order_by('order', '-created_at')
        
        image_list = []
        for img in images:
            image_list.append({
                'id': str(img.id),
                'before_image_url': img.before_image_url,
                'after_image_url': img.after_image_url,
                'before_image_path': img.before_image_path or '',
                'after_image_path': img.after_image_path or '',
                'order': img.order,
                'is_active': img.is_active,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'updated_at': img.updated_at.isoformat() if img.updated_at else None,
            })
        
        return JsonResponse({
            'success': True,
            'images': image_list
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Upload Before/After Images
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def upload_before_after_images(request):
    """
    Upload before/after image pairs
    Admin-only endpoint
    Expects: multipart/form-data with 'before_image' and 'after_image' files
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can upload images'}, status=403)
    
    try:
        before_file = request.FILES.get('before_image')
        after_file = request.FILES.get('after_image')
        
        if not before_file or not after_file:
            return JsonResponse({
                'success': False,
                'error': 'Both before_image and after_image are required'
            }, status=400)
        
        # Get the highest order number
        max_order = 0
        existing_images = BeforeAfterImage.objects()
        if existing_images:
            max_order = max([img.order for img in existing_images] or [0])
        
        # Upload to Cloudinary
        before_upload = cloudinary.uploader.upload(
            before_file,
            folder="homepage/before_after",
            overwrite=True
        )
        before_url = before_upload.get("secure_url")
        
        after_upload = cloudinary.uploader.upload(
            after_file,
            folder="homepage/before_after",
            overwrite=True
        )
        after_url = after_upload.get("secure_url")
        
        # Save locally (optional)
        local_dir = os.path.join(settings.MEDIA_ROOT, "homepage", "before_after")
        os.makedirs(local_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        before_filename = f"before_{timestamp}_{before_file.name}"
        after_filename = f"after_{timestamp}_{after_file.name}"
        
        before_path = os.path.join(local_dir, before_filename)
        after_path = os.path.join(local_dir, after_filename)
        
        with open(before_path, "wb") as f:
            for chunk in before_file.chunks():
                f.write(chunk)
        
        with open(after_path, "wb") as f:
            for chunk in after_file.chunks():
                f.write(chunk)
        
        # Create database entry
        before_after_image = BeforeAfterImage(
            before_image_url=before_url,
            after_image_url=after_url,
            before_image_path=to_media_db_path(before_path),
            after_image_path=to_media_db_path(after_path),
            order=max_order + 1,
            is_active='true',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        before_after_image.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Images uploaded successfully',
            'image': {
                'id': str(before_after_image.id),
                'before_image_url': before_after_image.before_image_url,
                'after_image_url': before_after_image.after_image_url,
                'order': before_after_image.order,
                'is_active': before_after_image.is_active,
            }
        }, status=200)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Update Before/After Image
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_before_after_image(request, image_id):
    """
    Update a before/after image (order, is_active)
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update images'}, status=403)
    
    try:
        data = json.loads(request.body)
        
        before_after_image = BeforeAfterImage.objects.get(id=image_id)
        
        # Update order if provided
        if 'order' in data:
            before_after_image.order = int(data['order'])
        
        # Update is_active if provided
        if 'is_active' in data:
            before_after_image.is_active = str(data['is_active']).lower()
        
        before_after_image.updated_at = datetime.utcnow()
        before_after_image.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Image updated successfully',
            'image': {
                'id': str(before_after_image.id),
                'before_image_url': before_after_image.before_image_url,
                'after_image_url': before_after_image.after_image_url,
                'order': before_after_image.order,
                'is_active': before_after_image.is_active,
            }
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Delete Before/After Image
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def delete_before_after_image(request, image_id):
    """
    Delete a before/after image
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can delete images'}, status=403)
    
    try:
        before_after_image = BeforeAfterImage.objects.get(id=image_id)
        before_after_image.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Image deleted successfully'
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Submit Contact Form
# =====================
@api_view(['POST'])
@csrf_exempt
def submit_contact_form(request):
    """
    Submit contact form from footer
    Public endpoint - no auth required
    """
    try:
        data = json.loads(request.body)
        
        name = data.get('name')
        mobile = data.get('mobile')
        email = data.get('email')
        reason = data.get('reason')
        source = (data.get('source') or 'public').strip().lower()
        
        # Validation
        if not all([name, mobile, email, reason]):
            return JsonResponse({
                'success': False,
                'error': 'All fields are required'
            }, status=400)
            
        # Create submission record
        from .models import ContactSubmission
        submission = ContactSubmission(
            name=name,
            mobile=mobile,
            email=email,
            reason=reason,
            created_at=datetime.utcnow()
        )
        if source in ('public', 'dashboard'):
            submission.source = source
        submission.save()
        
        # Send admin email
        try:
            from common.email_utils import send_contact_admin_email
            # Convert to dict for email utility
            submission_data = {
                'name': name,
                'mobile': mobile,
                'email': email,
                'reason': reason
            }
            send_contact_admin_email(submission_data)
        except Exception as e:
            print(f"Failed to send contact admin email: {e}")
            # Continue even if email fails
            
        return JsonResponse({
            'success': True,
            'message': 'Thank you! We will contact you shortly.'
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Submit Support Request (Help Center - Authenticated)
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def submit_support_request(request):
    """
    Submit help/support request from dashboard
    Authenticated endpoint - automatically links user
    """
    try:
        data = json.loads(request.body)
        
        # User details from request.user (authenticated)
        user = request.user
        
        # Allow overriding name/mobile/email but default to user profile
        name = data.get('name') or user.full_name or user.username
        email = data.get('email') or user.email
        mobile = data.get('mobile') or getattr(user, 'phone_number', '')
        
        reason = data.get('reason')
        
        # Validation
        if not reason:
            return JsonResponse({
                'success': False,
                'error': 'Message/Reason is required'
            }, status=400)
            
        # Create submission record
        from .models import ContactSubmission
        submission = ContactSubmission(
            name=name,
            mobile=mobile,
            email=email,
            reason=reason,
            user=user,
            type='support',
            created_at=datetime.utcnow()
        )
        submission.save()
        
        # Send admin email
        try:
            from common.email_utils import send_support_admin_email
            # Convert to dict for email utility
            submission_data = {
                'name': name,
                'mobile': mobile,
                'email': email,
                'reason': reason,
                'username': user.username,
                'user_email': user.email
            }
            send_support_admin_email(submission_data)
        except Exception as e:
            print(f"Failed to send support admin email: {e}")
            
        return JsonResponse({
            'success': True,
            'message': 'Support request submitted successfully.'
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Get All Support/Contact Requests (Admin)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_all_support_requests(request):
    """
    Get all contact and support submissions
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can list support requests'}, status=403)
    
    try:
        from .models import ContactSubmission
        
        # Determine type filter if any
        type_filter = request.GET.get('type')
        
        query = {}
        if type_filter in ['contact', 'support']:
            query['type'] = type_filter
            
        submissions = ContactSubmission.objects(**query).order_by('-created_at')
        
        data = []
        for sub in submissions:
            user_info = None
            if sub.user:
                user_info = {
                    'username': sub.user.username,
                    'email': sub.user.email,
                    'id': str(sub.user.id)
                }
                
            data.append({
                'id': str(sub.id),
                'name': sub.name,
                'email': sub.email,
                'mobile': sub.mobile,
                'reason': sub.reason,
                'type': sub.type,
                'user': user_info,
                'created_at': sub.created_at.isoformat() if sub.created_at else None
            })
            
        return JsonResponse({
            'success': True,
            'requests': data
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Default page content (fallback when no DB record)
# =====================
def _deep_merge_content(base, override):
    """Merge stored CMS content over defaults; lists replace only when non-empty."""
    if override is None:
        return base
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override if override is not None else base
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge_content(merged[key], value)
        elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = value if len(value) > 0 else merged[key]
        else:
            merged[key] = value
    return merged


def get_resolved_page_content(slug):
    defaults = get_default_page_content(slug)
    if not defaults:
        doc = PageContent.objects(page_slug=slug).first()
        return doc.content if doc else {}
    doc = PageContent.objects(page_slug=slug).first()
    stored = doc.content if doc else {}
    return _deep_merge_content(defaults, stored)


def get_default_page_content(slug):
    defaults = {
        'home': {
            'hero': {
                'pill_text': 'Built exclusively for jewelry brands',
                'title_html': 'Your jewelry.<br /><em>Studio-quality visuals.</em><br />No photographer needed.',
                'title': 'Your jewelry. Studio-quality visuals. No photographer needed.',
                'subtitle': 'Upload a reference photo — or nothing at all. Splash understands jewelry and generates product shots, model imagery, and campaign visuals in minutes.',
                'cta_primary_text': 'Get a demo',
                'cta_primary_href': 'https://calendly.com/mousumi-gosplash/30min',
                'cta_secondary_text': 'Start creating for free',
                'cta_secondary_href': '/signup',
                'note': 'No credit card required · No prompts needed · First images on us',
                'bottom_text': 'Upload a reference photo — or nothing at all. Splash understands jewelry and generates product shots, model imagery, and campaign visuals in minutes.',
                'images': [],
            },
            'ticker': [
                {'strong': 'Save up to 80%', 'span': 'on photography costs'},
                {'strong': 'No prompts needed', 'span': 'upload & generate'},
                {'strong': 'Understands jewelry', 'span': 'metals, gems & styling'},
                {'strong': 'India-first', 'span': 'built for the Indian jewelry market'},
            ],
            'showcase': {
                'eye_label': 'Showcase',
                'title_html': 'Created<br />with Splash',
                'heading': 'Created with Splash',
                'subheading': 'Campaign-ready visuals created entirely with Splash AI Studio.',
                'cta_text': 'View all →',
                'cta_href': '/gallery',
            },
            'how': {
                'eye_label': 'How it works',
                'title_html': 'Three steps to<br /><em>studio-perfect visuals</em>',
                'steps': [
                    {'number': '01', 'title': 'Upload your jewelry piece', 'description': 'Take a simple photo with your phone or use an existing product image. Or skip it entirely — Splash can generate beautiful visuals from scratch. It works brilliantly either way.'},
                    {'number': '02', 'title': 'AI composes the scene', 'description': "Splash reads your jewelry's metal finish, gemstone type, and style — then generates a campaign-ready visual with the perfect lighting, backdrop, and composition. Share a reference image to match any mood."},
                    {'number': '03', 'title': 'Download & publish', 'description': 'Export in full resolution. Use it on your website, social media, ads, catalogues, or share directly with your team for review — all from one place.'},
                ],
                'visual': {
                    'label': 'One upload',
                    'title_html': 'Multiple campaign-ready<br />outputs in seconds',
                },
            },
            'how_it_works': {
                'heading': 'How it works',
                'steps': [
                    {'title': 'Upload your jewelry piece', 'description': 'Take a simple photo with your phone or use an existing product image. Or skip it entirely — Splash can generate beautiful visuals from scratch. It works brilliantly either way.'},
                    {'title': 'AI composes the scene', 'description': "Splash reads your jewelry's metal finish, gemstone type, and style — then generates a campaign-ready visual with the perfect lighting, backdrop, and composition. Share a reference image to match any mood."},
                    {'title': 'Download & publish', 'description': 'Export in full resolution. Use it on your website, social media, ads, catalogues, or share directly with your team for review — all from one place.'},
                ],
            },
            'output': {
                'eye_label': 'What you can create',
                'title_html': 'Every visual<br /><em>your brand needs</em>',
                'items': [
                    {'title': 'Clean product shot', 'description': 'White or plain background. Perfect for websites, marketplaces, and catalogs.'},
                    {'title': 'Campaign visual', 'description': 'Editorial, mood-driven imagery for ads, lookbooks, and seasonal campaigns.'},
                    {'title': 'Lifestyle setup', 'description': 'Themed scenes with props, textures, and environments that match your brand.'},
                    {'title': 'Model shot', 'description': 'Jewelry worn on a model — up to 5 pieces styled together in a single image.'},
                    {'title': 'Bulk catalog', 'description': 'Generate dozens of consistent images across your full collection in one session.'},
                ],
            },
            'capabilities': {
                'eye_label': 'Capabilities',
                'title_html': 'Built different.<br /><em>For jewelry.</em>',
                'items': [
                    {'tag': 'No prompt required', 'title': 'Generate without typing a single word', 'description': 'Most AI tools require technical descriptions. Splash understands jewelry — metals, gemstones, silhouettes — and composes the perfect scene automatically. Just upload and go.', 'pills': ['White background', 'Themed setups', 'Auto-composed'], 'highlighted': True},
                    {'tag': 'Mood matching', 'title': 'Share a reference. Get that exact feel.', 'description': "Upload any inspiration image — a campaign you love, a competitor's shoot, a mood board. Splash reads the lighting, backdrop, colour palette, and styling, then applies it to your piece.", 'pills': ['Reads lighting', 'Matches colour tone', 'Captures mood'], 'highlighted': True},
                    {'tag': 'Team collaboration', 'title': 'Your whole team, one shared studio', 'description': 'Invite designers, marketers, and your agency. Work inside shared projects, review outputs, and publish — no email chains, no file transfers.', 'pills': ['Shared projects', 'Review & comment', 'Agency ready'], 'highlighted': False},
                    {'tag': 'Multi-piece generation', 'title': 'Style up to 5 pieces in one image', 'description': 'Create cohesive campaign shots featuring a full set — necklace, earrings, ring, bracelet — worn together on a model or arranged in a single scene.', 'pills': ['Up to 5 pieces', 'Model shots', 'Set styling'], 'highlighted': False},
                ],
            },
            'features': [
                {'title': 'Generate without typing a single word', 'description': 'Most AI tools require technical descriptions. Splash understands jewelry — metals, gemstones, silhouettes — and composes the perfect scene automatically.', 'icon': 'Gem'},
                {'title': 'Share a reference. Get that exact feel.', 'description': 'Upload any inspiration image — a campaign you love, a competitor\'s shoot, a mood board.', 'icon': 'Star'},
                {'title': 'Your whole team, one shared studio', 'description': 'Invite designers, marketers, and your agency. Work inside shared projects, review outputs, and publish.', 'icon': 'User'},
                {'title': 'Style up to 5 pieces in one image', 'description': 'Create cohesive campaign shots featuring a full set — necklace, earrings, ring, bracelet.', 'icon': 'Palette'},
            ],
            'who_uses': {
                'eye_label': 'Who uses Splash',
                'title_html': 'Built for everyone<br /><em>in the jewelry space</em>',
                'items': [
                    {'icon': 'Gem', 'title': 'D2C Jewelry Brands', 'description': 'Stop spending ₹25,000–₹1,50,000 per photoshoot. Splash gives you studio-quality product images for your website, Instagram, and marketplace listings — at a fraction of the cost and in a fraction of the time.', 'pills': ['Product catalog', 'Instagram content', 'Marketplace listings', 'Campaign visuals']},
                    {'icon': 'Store', 'title': 'Traditional Jewelers Going Digital', 'description': 'Upload one photo of your piece. Get stunning catalog images, ready to share on WhatsApp or your new website. No technical knowledge needed.', 'pills': ['WhatsApp catalog', 'Website gallery']},
                    {'icon': 'Palette', 'title': 'Creative Agencies', 'description': 'Deliver more for your jewelry clients without adding headcount. Team collaboration, bulk generation, and white-label ready.', 'pills': ['Bulk delivery', 'Team projects']},
                    {'icon': 'Share2', 'title': 'Social Media Managers', 'description': 'Never run out of jewelry content again. Generate 30 days of social posts in one session with consistent styling.', 'pills': ['Content calendar', 'Reels & Stories']},
                ],
            },
            'testimonials': {
                'eye_label': 'Stories',
                'title_html': 'What jewelry brands<br /><em>are saying</em>',
                'items': [
                    {'quote_html': '"A single jewellery shoot used to cost us <strong>₹2 lakhs minimum</strong> — studio, photographer, stylist, editing. With Splash we generate the same campaign-quality imagery in minutes, at a fraction of that cost."', 'initials': 'TR', 'name': 'Tarinika', 'role': 'Fine Jewellery Brand'},
                    {'quote_html': '"We were spending <strong>₹3.5 lakhs+ per shoot</strong> every season. Splash replaced our entire production workflow — we now launch collections faster, with more visual variations, and at a cost that actually makes sense."', 'initials': 'PK', 'name': 'Paksha', 'role': 'Contemporary Jewellery Brand'},
                    {'quote_html': '"Our Diwali campaign had <strong>5 collections, 200+ images, generated in 2 days</strong>. Previously that would take 3 weeks and a full production crew costing ₹2 lakhs+. Splash is now our primary creative tool."', 'initials': 'SN', 'name': 'Sneha Nair', 'role': 'Marketing Director'},
                ],
            },
            'pricing': {
                'eye_label': 'Pricing',
                'title_html': 'Need pricing details?<br /><em>We\'ll help you find the best plan for you.</em>',
                'card_title': 'Every jewellery brand is different — the number of products, the type of shoots, the frequency of content.',
                'card_description': "We'll understand your needs and help you get the most out of Splash.",
                'cta_text': 'Contact Us',
                'cta_href': '/contact',
            },
            'cta': {
                'title_html': 'Your next collection.<br /><em>Ready before the shoot<br />would\'ve been booked.</em>',
                'subtitle': 'Start creating jewelry visuals today — your first images are on us.',
                'primary_text': 'Start creating for free',
                'primary_href': '/signup',
                'whatsapp_text': 'Chat on WhatsApp',
                'whatsapp_number': '+918861308898',
                'whatsapp_href': 'https://wa.me/918861308898',
                'note': 'No credit card · No prompts · Just your jewelry and Splash',
            },
            'footer': {
                'logo_url': '/images/SplashLogoPNG.png',
                'copyright': '© 2025 Splash AI Studio',
                'links': [
                    {'label': 'Instagram', 'href': 'https://www.instagram.com/splash_ai_studios/'},
                    {'label': 'Privacy', 'href': '/privacy'},
                    {'label': 'Terms', 'href': '/terms'},
                    {'label': 'Contact', 'href': '/contact'},
                ],
            },
            'product_chapters': [],
        },
        'faqs': {
            'header': {
                'title': 'Frequently Asked Questions',
                'subtitle': 'Quick answers to common questions about Splash AI Studio',
            },
            'items': [
                {'question': 'How many credits does each generation cost?', 'answer': 'Plain images cost 2 credits, themed images cost 8 credits, model images cost 12 credits, and campaign images cost 15 credits.'},
                {'question': 'Can I use my own model photos?', 'answer': 'Yes! You can upload human model photos with plain backgrounds and front or 3/4 angle poses for best results.'},
                {'question': 'How long does image generation take?', 'answer': 'Plain images take 2–3 seconds, themed images 3–4 seconds, model images 4–5 seconds, and campaign images 5–6 seconds.'},
                {'question': 'Can I collaborate with team members?', 'answer': 'Yes! You can invite collaborators to your projects with Owner, Editor, or Viewer permissions.'},
            ],
            'cta': {
                'title': 'Still have questions?',
                'subtitle': 'Our team is happy to help you understand how Splash AI Studio fits your workflow.',
                'button_text': 'Contact Us',
                'button_href': '/contact',
            },
        },
        'contact': {
            'header': {
                'title': 'Contact Us',
                'subtitle': "We'd love to hear from you. Please fill out the form below or reach out to us directly.",
            },
            'details': {
                'section_title': 'Get in Touch',
                'office': {
                    'label': 'Office Address',
                    'lines': ['501, Manjeera Majestic Commercial Complex,', 'JNTU Road,KPHB, Hyderabad , Telangana, India 500085'],
                    'map_url': 'https://maps.app.goo.gl/3tMuX7F4xemYYrxH6',
                },
                'phone': {
                    'label': 'Contact Number',
                    'number': '+91 8790900881',
                    'tel_href': 'tel:+918790900881',
                    'hours': 'Assistance hours: Monday - Sunday 24/7 Hours',
                },
                'email': {
                    'label': 'Email Address',
                    'address': 'support@gosplash.ai',
                    'mailto_href': 'mailto:support@gosplash.ai',
                    'hours': 'Assistance hours: Monday - Sunday 24/7 Hours',
                },
            },
            'map_embed_url': 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3805.323180100733!2d78.39097917516732!3d17.492079483413075!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3bcb910057424ed5%3A0x199dce60198e6b9b!2sTechsprout%20AI%20Labs%20Pvt.%20Ltd.!5e0!3m2!1sen!2sin!4v1770624140087!5m2!1sen!2sin',
            'form': {
                'title': 'Have any query?',
                'success_title': 'Thank you!',
                'success_message': 'We have received your message and will get back to you shortly.',
                'submit_text': 'Send Message',
            },
        },
        'about': {
            'header': {'title': 'About Splash AI Studio', 'subtitle': 'Splash AI Studio is an AI-powered photoshoot replacement platform built for the fashion and apparel retail industry.'},
            'who_we_are': {'badge': 'Who We Are', 'title': 'Virtual Creative Studio', 'paragraphs': ['Splash AI Studio transforms the traditional product photography process into an automated, AI-driven workflow. It enables fashion brands and D2C retailers to generate high-quality product visuals, lifestyle images, and campaign assets without the need for cameras, physical studios, or professional models.', 'The platform functions as a virtual creative studio that simplifies visual content creation while maintaining professional quality and brand consistency.'], 'images': ['/images/about1.jpg', '/images/about2.jpg', '/images/about3.jpg', '/images/logo-Splash.png']},
            'purpose_vision': {'purpose_title': 'Our Purpose', 'purpose_text': 'The purpose of Splash AI Studio is to eliminate the limitations of traditional photoshoots — high costs, long production cycles, and limited scalability. By leveraging artificial intelligence, the platform allows brands to create visual content instantly, reduce operational overhead, and adapt quickly to changing marketing needs.', 'vision_title': 'Our Vision', 'vision_text': 'The vision of Splash AI Studio is to make AI-powered visual content creation accessible to every fashion retailer, regardless of team size, budget, or technical expertise.'},
            'platform_offers': {'heading': 'What the Platform Offers', 'subheading': 'A complete suite of tools designed to replace the traditional studio workflow.', 'items': [{'title': 'Product Visuals', 'description': 'Tools to generate individual product visuals and campaign imagery with high fidelity.'}, {'title': 'Centralized Dashboard', 'description': 'A centralized dashboard to manage, organize, and retrieve all your AI-generated images.'}, {'title': 'Campaign Creation', 'description': 'Support for project-based campaign creation to keep your seasonal assets organized.'}, {'title': 'Collaboration', 'description': 'Built-in collaboration capabilities for growing teams and agencies.'}, {'title': 'Flexible Plans', 'description': 'Flexible subscription and credit-based usage plans tailored to your needs.'}, {'title': 'Intuitive Design', 'description': 'The platform is designed to be intuitive and usable by non-technical users.'}]},
            'how_it_works': {'heading': 'How It Works', 'steps': [{'title': 'Upload & Select', 'description': 'Users upload product images, select visual styles or themes, and generate AI-powered visuals through guided workflows.'}, {'title': 'Refine & Download', 'description': 'Generated images can be previewed, refined, organized, and downloaded directly from the platform.'}]},
            'who_it_is_for': {'heading': 'Who It Is For', 'items': ['Fashion and apparel brands', 'D2C retailers', 'Ecommerce businesses', 'Creative teams and agencies']},
            'closing': {'title': 'Splash AI Studio represents a modern approach to fashion photography — combining speed, scalability, and creative flexibility through artificial intelligence.', 'cta_text': 'Get Started'},
        },
        'vision_mission': {
            'header': {'title': 'Our Vision & Mission', 'subtitle': 'Shaping the future of fashion imagery with AI-powered creativity.'},
            'vision': {'title': 'Our Vision', 'points': ['Democratize professional visuals', 'Enable instant content creation', 'Remove photoshoot dependencies', 'Empower limitless creativity'], 'paragraphs': ['To become the global standard for AI-powered fashion and product imagery.', 'We envision a world where brands can create studio-quality visuals instantly, without physical shoots, heavy costs, or production delays.']},
            'mission': {'title': 'Our Mission', 'paragraphs': ['To replace traditional fashion photoshoots with an intelligent, AI-driven creative studio.', 'We help brands reduce costs, move faster, and maintain consistent visual quality across all digital channels.'], 'bullets': [{'text': 'Instant AI-generated visuals'}, {'text': 'Built for brands and creative teams'}, {'text': 'Scales globally with ease'}]},
            'core_values': {'heading': 'Our Core Values', 'items': [{'title': 'Innovation', 'desc': 'Pushing boundaries with AI-driven creativity.'}, {'title': 'Speed', 'desc': 'Helping brands go to market faster.'}, {'title': 'Accessibility', 'desc': 'High-quality visuals for everyone.'}, {'title': 'Creative Freedom', 'desc': 'Unlimited experimentation without limits.'}, {'title': 'Reliability', 'desc': 'Consistent, production-ready results.'}, {'title': 'Customer Focus', 'desc': 'Solving real-world fashion challenges.'}]},
            'cta': {'title': 'Build the future of fashion visuals with Splash AI Studio.', 'button_text': 'Get Started'},
        },
        'tutorials': {
            'header': {'title': 'Tutorials', 'subtitle': 'Step-by-step video guides to help you master Splash AI Studio'},
            'videos': [
                {'title': 'Getting Started with Splash AI', 'description': 'Learn how to create your first AI-generated fashion image in under 2 minutes.', 'youtube_id': 'VIDEO_ID_1'},
                {'title': 'Using Your Own Model Photos', 'description': 'Upload human model images and generate studio-quality fashion visuals.', 'youtube_id': 'VIDEO_ID_2'},
                {'title': 'Campaign Image Generation', 'description': 'Create high-conversion campaign creatives for ads, banners, and social media.', 'youtube_id': 'VIDEO_ID_3'},
                {'title': 'Team Collaboration & Roles', 'description': 'Invite your team, assign roles, and collaborate efficiently.', 'youtube_id': 'VIDEO_ID_4'},
            ],
            'cta': {'title': 'Want more advanced tutorials?', 'subtitle': 'We regularly add new walkthroughs covering advanced workflows and campaign strategies.', 'button_text': 'Request a Tutorial'},
        },
        'security': {
            'header': {'title': 'Security & Data Protection', 'subtitle': 'Your data, designs, and intellectual property are protected with enterprise-grade security at every level.'},
            'cards': [
                {'title': 'Infrastructure Security', 'description': 'Splash AI Studio runs on secure, cloud-based infrastructure with industry-standard firewalls, network isolation, and continuous monitoring to prevent unauthorized access.'},
                {'title': 'Data Encryption', 'description': 'All data is encrypted in transit using HTTPS/TLS and encrypted at rest using modern encryption standards to ensure confidentiality and integrity.'},
                {'title': 'Data Ownership', 'description': 'You retain full ownership of all images, uploads, and generated assets. Splash AI never sells or shares your content with third parties.'},
                {'title': 'Access Control', 'description': 'Role-based access controls allow teams to collaborate securely with defined permissions for Owners, Editors, and Viewers.'},
            ],
            'compliance': {'heading': 'Compliance & Best Practices', 'paragraphs': ['Splash AI Studio follows globally recognized best practices for data protection, privacy, and secure software development.', 'We continuously review and improve our security posture to stay aligned with evolving industry standards.']},
            'cta': {'title': 'Have security questions?', 'subtitle': 'Our team is happy to answer any security or compliance questions you may have.', 'button_text': 'Contact Security Team'},
        },
    }
    return defaults.get(slug, {})


# =====================
# Get Page Content (Public)
# =====================
@api_view(['GET'])
@csrf_exempt
def get_page_content(request, slug):
    """Public: Get CMS content for a page (home, about, vision_mission, tutorials, security, faqs, contact)."""
    try:
        content = get_resolved_page_content(slug)
        return JsonResponse({'success': True, 'content': content}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Get Page Content (Admin)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_page_content_admin(request, slug):
    """Admin: Get page content (same as public)."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access this endpoint'}, status=403)
    try:
        content = get_resolved_page_content(slug)
        return JsonResponse({'success': True, 'content': content}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Update Page Content (Admin)
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_page_content(request, slug):
    """Admin: Update page content."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update content'}, status=403)
    try:
        data = json.loads(request.body)
        content = data.get('content')
        if content is None:
            return JsonResponse({'success': False, 'error': 'content is required'}, status=400)
        doc = PageContent.objects(page_slug=slug).first()
        if doc:
            doc.content = content
            doc.save()
        else:
            doc = PageContent(page_slug=slug, content=content)
            doc.save()
        return JsonResponse({'success': True, 'content': doc.content}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Blog: List (Public)
# =====================
@api_view(['GET'])
@csrf_exempt
def get_blog_posts(request):
    """Public: List published blog posts."""
    try:
        posts = BlogPost.objects(is_published='true').order_by('order', '-created_at')
        data = []
        for p in posts:
            data.append({
                'slug': p.slug,
                'title': p.title,
                'excerpt': p.excerpt or '',
                'date': p.date or '',
                'author': p.author or 'Splash Team',
                'category': p.category or '',
                'read_time': p.read_time or '5 min read',
                'image': p.image_url or '',
            })
        return JsonResponse({'success': True, 'posts': data}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Blog: Single Post (Public)
# =====================
@api_view(['GET'])
@csrf_exempt
def get_blog_post(request, slug):
    """Public: Get single blog post by slug."""
    try:
        post = BlogPost.objects(slug=slug, is_published='true').first()
        if not post:
            return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
        return JsonResponse({
            'success': True,
            'post': {
                'slug': post.slug,
                'title': post.title,
                'excerpt': post.excerpt or '',
                'body': post.body or '',
                'date': post.date or '',
                'author': post.author or 'Splash Team',
                'category': post.category or '',
                'read_time': post.read_time or '5 min read',
                'image': post.image_url or '',
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Blog: List All (Admin)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_all_blog_posts(request):
    """Admin: List all blog posts."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access this endpoint'}, status=403)
    try:
        posts = BlogPost.objects().order_by('order', '-created_at')
        data = []
        for p in posts:
            data.append({
                'id': str(p.id),
                'slug': p.slug,
                'title': p.title,
                'excerpt': p.excerpt or '',
                'body': p.body or '',
                'date': p.date or '',
                'author': p.author or 'Splash Team',
                'category': p.category or '',
                'read_time': p.read_time or '5 min read',
                'image_url': p.image_url or '',
                'order': p.order,
                'is_published': p.is_published,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None,
            })
        return JsonResponse({'success': True, 'posts': data}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Blog: Create (Admin)
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def create_blog_post(request):
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can create posts'}, status=403)
    try:
        data = json.loads(request.body)
        slug = data.get('slug') or (data.get('title', '') or '').lower().replace(' ', '-')
        import re
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        if not slug:
            slug = 'post-' + datetime.utcnow().strftime('%Y%m%d%H%M')
        if BlogPost.objects(slug=slug).first():
            return JsonResponse({'success': False, 'error': 'A post with this slug already exists'}, status=400)
        post = BlogPost(
            slug=slug,
            title=data.get('title', ''),
            excerpt=data.get('excerpt', ''),
            body=data.get('body', ''),
            date=data.get('date', ''),
            author=data.get('author', 'Splash Team'),
            category=data.get('category', ''),
            read_time=data.get('read_time', '5 min read'),
            image_url=data.get('image_url', ''),
            order=int(data.get('order', 0)),
            is_published='true' if data.get('is_published', True) else 'false',
        )
        post.save()
        return JsonResponse({
            'success': True,
            'post': {
                'id': str(post.id),
                'slug': post.slug,
                'title': post.title,
                'excerpt': post.excerpt,
                'body': post.body,
                'date': post.date,
                'author': post.author,
                'category': post.category,
                'read_time': post.read_time,
                'image_url': post.image_url,
                'order': post.order,
                'is_published': post.is_published,
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Blog: Update (Admin)
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_blog_post(request, slug):
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update posts'}, status=403)
    try:
        post = BlogPost.objects(slug=slug).first()
        if not post:
            return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
        data = json.loads(request.body)
        if 'title' in data:
            post.title = data['title']
        if 'excerpt' in data:
            post.excerpt = data['excerpt']
        if 'body' in data:
            post.body = data['body']
        if 'date' in data:
            post.date = data['date']
        if 'author' in data:
            post.author = data['author']
        if 'category' in data:
            post.category = data['category']
        if 'read_time' in data:
            post.read_time = data['read_time']
        if 'image_url' in data:
            post.image_url = data['image_url']
        if 'order' in data:
            post.order = int(data['order'])
        if 'is_published' in data:
            post.is_published = 'true' if data['is_published'] else 'false'
        post.save()
        return JsonResponse({
            'success': True,
            'post': {
                'id': str(post.id),
                'slug': post.slug,
                'title': post.title,
                'excerpt': post.excerpt,
                'body': post.body,
                'date': post.date,
                'author': post.author,
                'category': post.category,
                'read_time': post.read_time,
                'image_url': post.image_url,
                'order': post.order,
                'is_published': post.is_published,
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Blog: Delete (Admin)
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def delete_blog_post(request, slug):
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can delete posts'}, status=403)
    try:
        post = BlogPost.objects(slug=slug).first()
        if not post:
            return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
        post.delete()
        return JsonResponse({'success': True, 'message': 'Post deleted'}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


PUBLIC_GALLERY_TYPE_LABELS = {
    'lifestyle': 'Lifestyle',
    'campaign': 'Campaign visual',
    'product': 'Product shot',
    'model': 'Model shot',
    'multi_piece': 'Multi piece',
    'background_change': 'Background change',
}

PUBLIC_GALLERY_DEFAULT_LAYOUT = {
    'lifestyle': 'lifestyle',
    'campaign': 'campaign',
    'product': 'product',
    'model': 'model',
    'multi_piece': 'multipiece',
    'background_change': 'product',
}

DEFAULT_SHOWCASE_STATIC = [
    {
        'source_key': 'default:lifestyle',
        'path': '/images/lifestyle.webp',
        'image_type': 'lifestyle',
        'label': 'Lifestyle',
        'alt_text': 'Gold and emerald necklace product shot',
        'homepage_layout': 'lifestyle',
    },
    {
        'source_key': 'default:campaign',
        'path': '/images/campaign.webp',
        'image_type': 'campaign',
        'label': 'Campaign visual',
        'alt_text': 'Campaign visual with model wearing gold necklace',
        'homepage_layout': 'campaign',
    },
    {
        'source_key': 'default:product',
        'path': '/images/product.webp',
        'image_type': 'product',
        'label': 'Product shot',
        'alt_text': 'Lifestyle setup at a festive jewelry event',
        'homepage_layout': 'product',
    },
    {
        'source_key': 'default:model',
        'path': '/images/model.webp',
        'image_type': 'model',
        'label': 'Model shot',
        'alt_text': 'Model shot with gold chain necklace',
        'homepage_layout': 'model',
    },
    {
        'source_key': 'default:multi_piece',
        'path': '/images/multipice.png',
        'image_type': 'multi_piece',
        'label': 'Multi piece',
        'alt_text': 'Multi-piece gold earrings collection',
        'homepage_layout': 'multipiece',
    },
]

GALLERY_FILE_EXTENSIONS = {'.webp', '.png', '.jpg', '.jpeg', '.gif'}


def _frontend_public_url():
    return os.getenv('FRONTEND_PUBLIC_URL', 'http://localhost:3000').rstrip('/')


def _frontend_public_dir():
    return Path(settings.BASE_DIR).parent / 'frontend' / 'public'


def _to_public_src(relative_path):
    path = relative_path if relative_path.startswith('/') else f'/{relative_path}'
    return f"{_frontend_public_url()}{path}"


def _infer_gallery_type_from_filename(filename):
    lower = filename.lower()
    if lower.startswith('background_change'):
        return 'background_change'
    if lower.startswith('campaign_shot'):
        return 'campaign'
    if lower.startswith('image-plain'):
        return 'product'
    return 'lifestyle'


def _serialize_catalog_image(item, origin):
    image_type = item.get('image_type') or 'product'
    category = 'background' if image_type == 'background_change' else image_type
    path = item.get('path') or ''
    return {
        'id': item.get('source_key') or path,
        'source_key': item.get('source_key') or path,
        'origin': origin,
        'path': path,
        'src': _to_public_src(path),
        'image_url': _to_public_src(path),
        'image_type': image_type,
        'category': category,
        'label': item.get('label') or PUBLIC_GALLERY_TYPE_LABELS.get(image_type, 'Jewelry visual'),
        'alt': item.get('alt_text') or item.get('label') or PUBLIC_GALLERY_TYPE_LABELS.get(image_type, 'Jewelry visual'),
        'homepage_layout': item.get('homepage_layout') or PUBLIC_GALLERY_DEFAULT_LAYOUT.get(image_type, 'product'),
        'local_file': item.get('local_file'),
    }


def _scan_filesystem_gallery_catalog():
    gallery_dir = _frontend_public_dir() / 'galery'
    if not gallery_dir.exists():
        return []

    items = []
    for file_path in sorted(gallery_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in GALLERY_FILE_EXTENSIONS:
            continue
        image_type = _infer_gallery_type_from_filename(file_path.name)
        relative_path = f"/galery/{file_path.name}"
        items.append(_serialize_catalog_image({
            'source_key': f'filesystem:{file_path.name}',
            'path': relative_path,
            'image_type': image_type,
            'label': PUBLIC_GALLERY_TYPE_LABELS.get(image_type, 'Jewelry visual'),
            'alt_text': PUBLIC_GALLERY_TYPE_LABELS.get(image_type, 'Jewelry visual'),
            'homepage_layout': PUBLIC_GALLERY_DEFAULT_LAYOUT.get(image_type, 'product'),
            'local_file': str(file_path),
        }, origin='filesystem'))
    return items


def _default_showcase_catalog():
    return [_serialize_catalog_image(item, origin='default_showcase') for item in DEFAULT_SHOWCASE_STATIC]


def _resolve_live_gallery_images():
    cms_active = PublicGalleryImage.objects(is_active='true').order_by('order', '-created_at')
    if cms_active.count() > 0:
        return 'cms', [_serialize_public_gallery_image(img) for img in cms_active]
    filesystem = _scan_filesystem_gallery_catalog()
    if filesystem:
        return 'filesystem', filesystem
    return 'empty', []


def _resolve_live_showcase_images():
    cms_showcase = PublicGalleryImage.objects(
        is_active='true',
        show_on_homepage='true',
    ).order_by('order', '-created_at')
    if cms_showcase.count() > 0:
        return 'cms', [_serialize_public_gallery_image(img) for img in cms_showcase]
    defaults = _default_showcase_catalog()
    if defaults:
        return 'defaults', defaults
    return 'empty', []


def _catalog_item_to_local_path(catalog_item):
    local_file = catalog_item.get('local_file')
    if local_file and os.path.exists(local_file):
        return local_file
    path = catalog_item.get('path') or ''
    if path.startswith('/'):
        candidate = _frontend_public_dir() / path.lstrip('/')
        if candidate.exists():
            return str(candidate)
    return None


def _import_catalog_item_to_cms(catalog_item, visibility='gallery_only'):
    local_path = _catalog_item_to_local_path(catalog_item)
    if not local_path:
        raise FileNotFoundError(f"Local file not found for {catalog_item.get('source_key')}")

    show_on_homepage = visibility == 'gallery_and_homepage'
    is_active = visibility != 'hidden'

    existing = PublicGalleryImage.objects()
    max_order = max([img.order for img in existing] or [0]) if existing else 0

    upload = cloudinary.uploader.upload(
        local_path,
        folder="homepage/public_gallery",
        overwrite=True,
    )

    image_type = catalog_item.get('image_type') or 'product'
    gallery_image = PublicGalleryImage(
        image_url=upload.get('secure_url'),
        image_type=image_type,
        label=catalog_item.get('label') or PUBLIC_GALLERY_TYPE_LABELS.get(image_type, ''),
        alt_text=catalog_item.get('alt') or catalog_item.get('label') or '',
        homepage_layout=catalog_item.get('homepage_layout') or PUBLIC_GALLERY_DEFAULT_LAYOUT.get(image_type, 'product'),
        order=max_order + 1,
        is_active='true' if is_active else 'false',
        show_on_homepage='true' if show_on_homepage else 'false',
    )
    gallery_image.save()
    return gallery_image


def _serialize_public_gallery_image(img, include_admin_fields=False):
    image_type = img.image_type or 'product'
    category = 'background' if image_type == 'background_change' else image_type
    data = {
        'id': str(img.id),
        'src': img.image_url,
        'image_url': img.image_url,
        'image_type': image_type,
        'category': category,
        'label': img.label or PUBLIC_GALLERY_TYPE_LABELS.get(image_type, 'Jewelry visual'),
        'alt': img.alt_text or img.label or PUBLIC_GALLERY_TYPE_LABELS.get(image_type, 'Jewelry visual'),
        'homepage_layout': img.homepage_layout or PUBLIC_GALLERY_DEFAULT_LAYOUT.get(image_type, 'product'),
        'order': img.order,
    }
    if include_admin_fields:
        data.update({
            'is_active': img.is_active,
            'show_on_homepage': img.show_on_homepage,
            'created_at': img.created_at.isoformat() if img.created_at else None,
            'updated_at': img.updated_at.isoformat() if img.updated_at else None,
        })
    return data


# =====================
# Public Gallery (Public)
# =====================
@api_view(['GET'])
@csrf_exempt
def get_public_gallery_images(request):
    """Public: all active public gallery images for /gallery."""
    try:
        images = PublicGalleryImage.objects(is_active='true').order_by('order', '-created_at')
        return JsonResponse({
            'success': True,
            'images': [_serialize_public_gallery_image(img) for img in images],
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
def get_homepage_showcase_images(request):
    """Public: active gallery images flagged for homepage showcase."""
    try:
        images = PublicGalleryImage.objects(
            is_active='true',
            show_on_homepage='true',
        ).order_by('order', '-created_at')
        return JsonResponse({
            'success': True,
            'images': [_serialize_public_gallery_image(img) for img in images],
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def get_all_public_gallery_images(request):
    """Admin: list all public gallery images."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access this endpoint'}, status=403)
    try:
        images = PublicGalleryImage.objects().order_by('order', '-created_at')
        return JsonResponse({
            'success': True,
            'images': [_serialize_public_gallery_image(img, include_admin_fields=True) for img in images],
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@csrf_exempt
@authenticate
def get_public_gallery_admin_overview(request):
    """Admin: CMS library plus what is currently live on /gallery and homepage showcase."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access this endpoint'}, status=403)
    try:
        cms_images = PublicGalleryImage.objects().order_by('order', '-created_at')
        cms_list = [_serialize_public_gallery_image(img, include_admin_fields=True) for img in cms_images]

        gallery_source, live_gallery = _resolve_live_gallery_images()
        showcase_source, live_showcase = _resolve_live_showcase_images()
        filesystem_catalog = _scan_filesystem_gallery_catalog()
        default_showcase_catalog = _default_showcase_catalog()

        return JsonResponse({
            'success': True,
            'frontend_public_url': _frontend_public_url(),
            'cms_images': cms_list,
            'live': {
                'gallery_source': gallery_source,
                'showcase_source': showcase_source,
                'gallery_images': live_gallery,
                'showcase_images': live_showcase,
            },
            'catalog': {
                'filesystem_gallery': filesystem_catalog,
                'default_showcase': default_showcase_catalog,
            },
        }, status=200)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def import_public_gallery_images(request):
    """Admin: import filesystem/default images into CMS."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can import images'}, status=403)
    try:
        data = json.loads(request.body)
        source_keys = data.get('source_keys') or []
        visibility = data.get('visibility', 'gallery_only')
        if visibility not in ('gallery_only', 'gallery_and_homepage', 'hidden'):
            return JsonResponse({'success': False, 'error': 'Invalid visibility'}, status=400)

        if not source_keys:
            preset = data.get('preset')
            if preset == 'filesystem_gallery':
                source_keys = [item['source_key'] for item in _scan_filesystem_gallery_catalog()]
                visibility = data.get('visibility', 'gallery_only')
            elif preset == 'default_showcase':
                source_keys = [item['source_key'] for item in DEFAULT_SHOWCASE_STATIC]
                visibility = data.get('visibility', 'gallery_and_homepage')
            else:
                return JsonResponse({'success': False, 'error': 'source_keys or preset is required'}, status=400)

        catalog = {}
        for item in _scan_filesystem_gallery_catalog():
            catalog[item['source_key']] = item
        for item in _default_showcase_catalog():
            catalog[item['source_key']] = item

        imported = []
        errors = []
        for key in source_keys:
            catalog_item = catalog.get(key)
            if not catalog_item:
                errors.append({'source_key': key, 'error': 'Unknown source'})
                continue
            try:
                gallery_image = _import_catalog_item_to_cms(catalog_item, visibility=visibility)
                imported.append(_serialize_public_gallery_image(gallery_image, include_admin_fields=True))
            except Exception as exc:
                errors.append({'source_key': key, 'error': str(exc)})

        return JsonResponse({
            'success': True,
            'imported_count': len(imported),
            'imported': imported,
            'errors': errors,
        }, status=200)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def upload_public_gallery_image(request):
    """Admin: upload a public gallery image."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can upload images'}, status=403)
    try:
        image_file = request.FILES.get('image')
        if not image_file:
            return JsonResponse({'success': False, 'error': 'image file is required'}, status=400)

        image_type = request.POST.get('image_type', 'product')
        if image_type not in PUBLIC_GALLERY_TYPE_LABELS:
            return JsonResponse({'success': False, 'error': 'Invalid image_type'}, status=400)

        label = request.POST.get('label', '')
        alt_text = request.POST.get('alt_text', '')
        homepage_layout = request.POST.get('homepage_layout') or PUBLIC_GALLERY_DEFAULT_LAYOUT.get(image_type, 'product')
        show_on_homepage = 'true' if str(request.POST.get('show_on_homepage', 'false')).lower() in ('1', 'true', 'yes') else 'false'
        is_active = 'true' if str(request.POST.get('is_active', 'true')).lower() in ('1', 'true', 'yes') else 'false'

        max_order = 0
        existing = PublicGalleryImage.objects()
        if existing:
            max_order = max([img.order for img in existing] or [0])

        upload = cloudinary.uploader.upload(
            image_file,
            folder="homepage/public_gallery",
            overwrite=True,
        )
        image_url = upload.get('secure_url')

        gallery_image = PublicGalleryImage(
            image_url=image_url,
            image_type=image_type,
            label=label or PUBLIC_GALLERY_TYPE_LABELS.get(image_type, ''),
            alt_text=alt_text or label or PUBLIC_GALLERY_TYPE_LABELS.get(image_type, ''),
            homepage_layout=homepage_layout,
            order=max_order + 1,
            is_active=is_active,
            show_on_homepage=show_on_homepage,
        )
        gallery_image.save()

        return JsonResponse({
            'success': True,
            'message': 'Gallery image uploaded successfully',
            'image': _serialize_public_gallery_image(gallery_image, include_admin_fields=True),
        }, status=200)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_public_gallery_image(request, image_id):
    """Admin: update public gallery image metadata."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update images'}, status=403)
    try:
        data = json.loads(request.body)
        gallery_image = PublicGalleryImage.objects.get(id=image_id)

        if 'order' in data:
            gallery_image.order = int(data['order'])
        if 'is_active' in data:
            gallery_image.is_active = 'true' if data['is_active'] in (True, 'true', 'True', '1', 1) else 'false'
        if 'show_on_homepage' in data:
            gallery_image.show_on_homepage = 'true' if data['show_on_homepage'] in (True, 'true', 'True', '1', 1) else 'false'
        if 'label' in data:
            gallery_image.label = data['label']
        if 'alt_text' in data:
            gallery_image.alt_text = data['alt_text']
        if 'image_type' in data and data['image_type'] in PUBLIC_GALLERY_TYPE_LABELS:
            gallery_image.image_type = data['image_type']
        if 'homepage_layout' in data:
            gallery_image.homepage_layout = data['homepage_layout']

        gallery_image.save()

        return JsonResponse({
            'success': True,
            'message': 'Gallery image updated successfully',
            'image': _serialize_public_gallery_image(gallery_image, include_admin_fields=True),
        }, status=200)
    except DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Image not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_view(['DELETE'])
@csrf_exempt
@authenticate
def delete_public_gallery_image(request, image_id):
    """Admin: delete public gallery image."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can delete images'}, status=403)
    try:
        gallery_image = PublicGalleryImage.objects.get(id=image_id)
        gallery_image.delete()
        return JsonResponse({'success': True, 'message': 'Gallery image deleted successfully'}, status=200)
    except DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Image not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================
# Upload Content Image (Admin)
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def upload_content_image(request):
    """Admin: Upload image to Cloudinary; return URL."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can upload images'}, status=403)
    try:
        file = request.FILES.get('image') or request.FILES.get('file')
        if not file:
            return JsonResponse({'success': False, 'error': 'No image file provided'}, status=400)
        upload = cloudinary.uploader.upload(file, folder='homepage/content', overwrite=True)
        url = upload.get('secure_url')
        return JsonResponse({'success': True, 'url': url}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

