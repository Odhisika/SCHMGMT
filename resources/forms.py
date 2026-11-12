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
    """Form for uploading course resource videos.

    A local video file or a YouTube link is required, but not both. The
    YouTube link takes priority when both are supplied so teachers can move a
    large upload to YouTube without deleting the original file first.
    """
    
    class Meta:
        model = CourseVideo
        fields = ['title', 'video', 'youtube_url', 'thumbnail', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Enter video title (e.g., Introduction to Algebra)')
            }),
            'video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/*,.mp4,.mkv,.wmv,.3gp,.f4v,.avi,.mp3,.webm'
            }),
            'youtube_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': _('https://www.youtube.com/watch?v=... or https://youtu.be/...'),
                'inputmode': 'url',
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
            'video': _('Video File'),
            'youtube_url': _('YouTube Link'),
            'thumbnail': _('Thumbnail Image (Optional)'),
            'description': _('Description'),
        }
        help_texts = {
            'video': _('Allowed formats: MP4, MKV, WMV, 3GP, F4V, AVI, MP3, WEBM'),
            'youtube_url': _('Paste a YouTube or YouTube Shorts link. Used instead of a local video file.'),
            'thumbnail': _('Upload a thumbnail image for the video preview'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make optional fields
        self.fields['video'].required = False
        self.fields['youtube_url'].required = False
        self.fields['thumbnail'].required = False
        self.fields['description'].required = False

    def clean(self):
        cleaned = super().clean()
        has_local_video = bool(
            cleaned.get('video') or (self.instance.pk and self.instance.video)
        )
        has_youtube = bool(
            cleaned.get('youtube_url') or (self.instance.pk and self.instance.youtube_url)
        )

        if not has_local_video and not has_youtube:
            raise forms.ValidationError(
                _('Select a video file or paste a YouTube link.')
            )

        youtube_url = cleaned.get('youtube_url')
        if youtube_url:
            probe = CourseVideo(youtube_url=youtube_url)
            if not probe.get_youtube_id():
                self.add_error(
                    'youtube_url',
                    _('Enter a valid YouTube link (for example https://youtu.be/VIDEO_ID).'),
                )

        return cleaned
