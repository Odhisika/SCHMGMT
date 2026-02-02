from django import forms
from .models import NewsAndEvents, Term, TERM

# Keep Semester as alias for backward compatibility
Semester = Term
SEMESTER = TERM


# news and events
class NewsAndEventsForm(forms.ModelForm):
    class Meta:
        model = NewsAndEvents
        fields = (
            "title",
            "summary",
            "posted_as",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})
        self.fields["posted_as"].widget.attrs.update({"class": "form-control"})





class TermForm(forms.ModelForm):
    term = forms.CharField(
        widget=forms.Select(
            choices=TERM,
            attrs={
                "class": "browser-default custom-select",
            },
        ),
        label="term",
    )
    year = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g., 2024",
            }
        ),
        label="Academic Year",
        max_length=4,
    )
    is_current_term = forms.CharField(
        widget=forms.Select(
            choices=((True, "Yes"), (False, "No")),
            attrs={
                "class": "browser-default custom-select",
            },
        ),
        label="is current term ?",
    )

    next_term_begins = forms.DateTimeField(
        widget=forms.TextInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
        required=True,
    )

    class Meta:
        model = Term
        fields = ["term", "year", "is_current_term", "next_term_begins"]


# Keep SemesterForm as alias for backward compatibility
SemesterForm = TermForm

