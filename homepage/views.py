"""
Homepage Content API views
Admin-only endpoints for managing homepage content (Before/After images)
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
import os
from mongoengine.errors import DoesNotExist, ValidationError
from .models import BeforeAfterImage, PageContent, BlogPost
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime
from django.conf import settings
import cloudinary.uploader


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
            before_image_path=before_path,
            after_image_path=after_path,
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
def get_default_page_content(slug):
    defaults = {
        'home': {
            'hero': {
                'title': 'CAMPAIGN READY VISUALS, WITHOUT THE SHOOT',
                'cta_primary_text': 'Try Free Splash AI',
                'cta_primary_href': '/login',
                'cta_secondary_text': 'See Showcase',
                'cta_secondary_href': '#showcase',
                'bottom_text': 'Moodboard to model shots to perfect retouches— Splash AI Studio turns your concepts into stunning, shoppable imagery.',
                'images': ['/images/hero-campaign-01.jpg', '/images/hero-campaign-02.jpg', '/images/hero-campaign-03.jpg'],
            },
            'product_chapters': [
                {'title': 'Start with a spark.', 'description': 'Upload moodboards, pick styles, and define your brand feel. Our AI understands luxury aesthetics and translates your vision into precise creative direction.', 'image_url': '/images/chapter-brief.jpg', 'image_alt': 'Luxury jewelry design moodboard', 'image_position': 'right'},
                {'title': 'Cast the perfect face.', 'description': 'Choose AI models or upload approved talent—control poses, angles, and expressions.', 'image_url': '/images/chapter-model.jpeg', 'image_alt': 'Professional model portrait', 'image_position': 'left'},
                {'title': 'Your pieces, flawlessly rendered.', 'description': 'Import SKUs and we preserve every detail—metal sheen, stone fire, and micro-details.', 'image_url': '/images/chapter-product.jpg', 'image_alt': 'Macro close-up of luxury diamond ring', 'image_position': 'right'},
                {'title': 'Set the scene.', 'description': 'Pick locations, backdrops, and palettes. Go from studio-clean to editorial drama.', 'image_url': '/images/chapter-scene.png', 'image_alt': 'Editorial jewelry photography setup', 'image_position': 'left'},
                {'title': 'Generate. Refine. Perfect.', 'description': 'Create multiple takes, prompt micro-edits, correct reflections, and match skin tones.', 'image_url': '/images/variants-bangles.jpg', 'image_alt': 'Three bangle variants', 'image_position': 'right'},
            ],
            'features': [
                {'title': 'Photoreal Metals & Gems', 'description': 'True-to-life sheen and sparkle.', 'icon': 'Gem'},
                {'title': 'Skin-Tone Fidelity', 'description': 'Editorial lighting and natural texture.', 'icon': 'Star'},
                {'title': 'Pose Library', 'description': 'From subtle tilts to bold looks.', 'icon': 'User'},
                {'title': 'Style Presets', 'description': 'Studio clean, editorial luxe, outdoor daylight.', 'icon': 'Palette'},
                {'title': 'Variant Consistency', 'description': 'One look, many SKUs.', 'icon': 'Repeat'},
                {'title': 'Marketplace-Ready', 'description': 'Compliant crops, backgrounds, and sizes.', 'icon': 'Box'},
            ],
            'showcase': {
                'heading': 'See it in action',
                'subheading': 'Campaign-ready visuals created entirely with Splash AI Studio.',
                'images': [
                    {'src': '/images/showcase-01.jpg', 'alt': 'Pearl and diamond drop earrings editorial close-up', 'tall': True},
                    {'src': '/images/showcase-02.jpg', 'alt': 'Luxury tennis bracelet with diamonds', 'tall': False},
                    {'src': '/images/showcase-03.jpg', 'alt': 'Stack of gold rings with gemstones', 'tall': False},
                    {'src': '/images/showcase-04.jpg', 'alt': 'Pendant necklace editorial portrait', 'tall': True},
                    {'src': '/images/showcase-05.jpg', 'alt': 'Flat lay jewelry collection on marble', 'tall': False},
                    {'src': '/images/showcase-06.jpg', 'alt': 'Model wearing statement earrings and necklaces', 'tall': True},
                ],
            },
            'how_it_works': {
                'heading': 'How it works',
                'steps': [
                    {'title': 'Brief', 'description': 'Upload moodboards and define your brand feel.'},
                    {'title': 'Model', 'description': 'Choose AI models or upload approved talent.'},
                    {'title': 'Generate', 'description': 'Create multiple takes and refine details.'},
                    {'title': 'Publish', 'description': 'Export for PDP, marketplace, and social.'},
                ],
                'image_options': [
                    {'title': 'Background Generation', 'description': 'Generate plain background images or replace existing backgrounds for your product.'},
                    {'title': 'Model Integration', 'description': 'Generate AI or real model images with the product for authentic representation.'},
                    {'title': 'Campaign Shots', 'description': 'Generate campaign shots after selecting your campaign reference materials.'},
                    {'title': 'Direct Prompting', 'description': 'Generate custom images by providing direct text prompts for maximum flexibility.'},
                ],
            },
            'footer': {
                'logo_url': '/images/logo-splash.png',
                'tagline': 'Campaign-ready visuals powered by AI.',
                'copyright': '© 2026 Splash AI Studio. All rights reserved.',
                'links': {
                    'Platform': [{'label': 'Features', 'href': '/#product'}, {'label': 'Pricing', 'href': '/#pricing'}, {'label': 'Showcase', 'href': '/#showcase'}],
                    'Resources': [{'label': 'Blog', 'href': '/blog'}, {'label': 'Tutorials', 'href': '/tutorials'}, {'label': 'FAQs', 'href': '/faqs'}],
                    'Company': [{'label': 'About Us', 'href': '/about'}, {'label': 'Contact Us', 'href': '/contact'}, {'label': 'Vision & Mission', 'href': '/vision-mision'}],
                    'Legal': [{'label': 'Privacy Policy', 'href': '/privacy'}, {'label': 'Terms & Conditions', 'href': '/terms'}, {'label': 'Security & Data Protection', 'href': '/security'}],
                },
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
    """Public: Get CMS content for a page (home, about, vision_mission, tutorials, security)."""
    try:
        doc = PageContent.objects(page_slug=slug).first()
        content = doc.content if doc else get_default_page_content(slug)
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
        doc = PageContent.objects(page_slug=slug).first()
        content = doc.content if doc else get_default_page_content(slug)
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

