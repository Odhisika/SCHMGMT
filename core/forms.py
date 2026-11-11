from django import forms
from django.utils.translation import gettext_lazy as _
from datetime import timedelta
from .models import NewsAndEvents, Term, TERM, TermWeek, WEEK_ACTIVITY_TYPES

# Keep Semester as alias for backward compatibility
Semester = Term
SEMESTER = TERM


# news and events
class NewsAndEventsForm(forms.ModelForm):
    specific_user_ids = forms.CharField(
        required=False, 
        widget=forms.HiddenInput,
        help_text="Comma-separated user IDs"
    )

    class Meta:
        model = NewsAndEvents
        fields = (
            "title",
            "summary",
            "posted_as",
            "target_division",
            "target_role",
            # specific_users is handled manually via specific_user_ids to avoid rendering huge select
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control", "rows": 4})
        self.fields["posted_as"].widget.attrs.update({"class": "form-control"})
        self.fields["target_division"].widget.attrs.update({"class": "form-control"})
        self.fields["target_role"].widget.attrs.update({"class": "form-control"})

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            
            # Handle specific users
            user_ids_str = self.cleaned_data.get('specific_user_ids')
            if user_ids_str:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user_ids = [int(id_str) for id_str in user_ids_str.split(',') if id_str.strip().isdigit()]
                    users = User.objects.filter(id__in=user_ids)
                    instance.specific_users.set(users)
                except Exception as e:
                    # Log error or ignore
                    pass
            else:
                instance.specific_users.clear()
        return instance





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

    start_date = forms.DateField(
        widget=forms.TextInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
        required=False,
    )

    end_date = forms.DateField(
        widget=forms.TextInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
        required=False,
    )

    result_released = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={
                 "class": "form-check-input",
            }
        ),
        required=False,
        label="Publish Results?",
        help_text="Check this to allow students and parents to view their results for this term."
    )

    class Meta:
        model = Term
        fields = ["term", "year", "is_current_term", "start_date", "end_date", "next_term_begins", "result_released"]


class TermWeekForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.term = kwargs.pop("term", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = TermWeek
        fields = ["week_number", "start_date", "end_date", "activity_type", "title", "description", "is_active"]
        widgets = {
            "week_number": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "activity_type": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional custom title"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional description"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        week_number = cleaned.get("week_number")
        if bool(start_date) != bool(end_date):
            self.add_error("end_date", _("Enter both dates, or leave both blank to use the term's week dates."))
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", _("The end date must be on or after the start date."))
        if self.term and self.term.start_date and self.term.end_date and week_number:
            generated_start = self.term.start_date + timedelta(days=(week_number - 1) * 7)
            if generated_start > self.term.end_date:
                self.add_error("week_number", _("This week falls outside the term dates."))
        if self.term and start_date and self.term.start_date and start_date < self.term.start_date:
            self.add_error("start_date", _("The activity cannot start before the term."))
        if self.term and end_date and self.term.end_date and end_date > self.term.end_date:
            self.add_error("end_date", _("The activity cannot end after the term."))
        return cleaned


# Keep SemesterForm as alias for backward compatibility
SemesterForm = TermForm

