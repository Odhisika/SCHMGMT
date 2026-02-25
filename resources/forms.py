from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CourseFile, CourseVideo


class CourseFileForm(forms.ModelForm):
    """Form for uploading course resource files"""
    
    class Meta:
        model = CourseFile
        fields = ['title', 'file', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Enter file title (e.g., Chapter 1 Notes)')
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.rar,.7zip'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Brief description of this file (optional)')
            }),
        }
        labels = {
            'title': _('File Title'),
            'file': _('Select File'),
            'description': _('Description'),
        }
        help_texts = {
            'file': _('Allowed formats: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, ZIP, RAR, 7ZIP'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make description optional
        self.fields['description'].required = False


class CourseVideoForm(forms.ModelForm):
    """Form for uploading course resource videos"""
    
    class Meta:
        model = CourseVideo
        fields = ['title', 'video', 'thumbnail', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Enter video title (e.g., Introduction to Algebra)')
            }),
            'video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/*,.mp4,.mkv,.wmv,.3gp,.f4v,.avi,.mp3,.webm'
            }),
            'thumbnail': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Brief description of this video (optional)')
            }),
        }
        labels = {
            'title': _('Video Title'),
            'video': _('Select Video'),
            'thumbnail': _('Thumbnail Image (Optional)'),
            'description': _('Description'),
        }
        help_texts = {
            'video': _('Allowed formats: MP4, MKV, WMV, 3GP, F4V, AVI, MP3, WEBM'),
            'thumbnail': _('Upload a thumbnail image for the video preview'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make optional fields
        self.fields['thumbnail'].required = False
        self.fields['description'].required = False
