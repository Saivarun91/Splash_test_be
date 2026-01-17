# imgbackendapp/templatetags/base64_filters.py
import base64
from django import template

register = template.Library()


@register.filter
def b64encode(value):
    """Convert binary image data to base64 for inline display"""
    if not value:
        return ''
    return base64.b64encode(value).decode('utf-8')
