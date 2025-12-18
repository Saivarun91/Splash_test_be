

# imgbackendapp/forms.py
from django import forms
from .models import Ornament


class OrnamentForm(forms.ModelForm):
    class Meta:
        model = Ornament
        fields = ['image', 'prompt']


class BackgroundChangeForm(forms.Form):
    ornament_image = forms.ImageField(label="Ornament Image")
    background_image = forms.ImageField(
        label="Reference Background Image", required=False)
    background_color = forms.CharField(
        label="Background Color (HEX or name)", required=False)
    prompt = forms.CharField(label="Prompt", widget=forms.Textarea(
        attrs={"rows": 2}), required=False)
