from django import forms
from django.forms.widgets import RadioSelect, Textarea
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import gettext_lazy as _
from django.forms.models import inlineformset_factory
from .models import Question, Quiz, MCQuestion, Choice


class QuestionForm(forms.Form):
    def __init__(self, question, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        choice_list = [x for x in question.get_choices_list()]
        self.fields["answers"] = forms.ChoiceField(
            choices=choice_list, widget=RadioSelect
        )


class EssayForm(forms.Form):
    def __init__(self, question, *args, **kwargs):
        super(EssayForm, self).__init__(*args, **kwargs)
        self.fields["answers"] = forms.CharField(
            widget=Textarea(attrs={"style": "width:100%"})
        )


class TrueFalseForm(forms.Form):
    """Form for True/False questions"""
    def __init__(self, question, *args, **kwargs):
        super(TrueFalseForm, self).__init__(*args, **kwargs)
        self.fields["answers"] = forms.ChoiceField(
            choices=question.get_choices_list(),
            widget=RadioSelect
        )


class FillInTheBlankForm(forms.Form):
    """Form for Fill in the Blank questions"""
    def __init__(self, question, *args, **kwargs):
        super(FillInTheBlankForm, self).__init__(*args, **kwargs)
        self.fields["answers"] = forms.CharField(
            max_length=200,
            widget=forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": _("Enter your answer here...")
            })
        )


TIME_LIMIT_CHOICES = [
    ('', _('No time limit')),
    (15, _('15 minutes')),
    (30, _('30 minutes')),
    (45, _('45 minutes')),
    (60, _('1 hour')),
    (90, _('1.5 hours')),
    (120, _('2 hours')),
    (180, _('3 hours')),
]


class QuizAddForm(forms.ModelForm):
    time_limit_minutes = forms.TypedChoiceField(
        choices=TIME_LIMIT_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
        label=_('Time Limit'),
        help_text=_('How long students have to complete the quiz.'),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.all().select_subclasses(),
        required=False,
        label=_("Questions"),
        widget=FilteredSelectMultiple(verbose_name=_("Questions"), is_stacked=False),
    )

    class Meta:
        model = Quiz
        fields = [
            'category', 'title', 'description', 'pass_mark',
            'random_order', 'answers_at_end', 'exam_paper', 'single_attempt',
            'max_attempts', 'draft', 'time_limit_minutes',
            'available_from', 'available_until',
            'allow_review_after_submission', 'show_correct_answers_after',
        ]
        widgets = {
            'available_from': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'available_until': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'show_correct_answers_after': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'pass_mark': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Support ISO datetime-local format for HTML5 inputs
        for field_name in ('available_from', 'available_until', 'show_correct_answers_after'):
            self.fields[field_name].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
            self.fields[field_name].required = False

        # Populate questions from existing instance
        if self.instance.pk:
            self.fields["questions"].initial = (
                self.instance.question_set.all().select_subclasses()
            )
            # Pre-fill datetime-local values
            for field_name in ('available_from', 'available_until', 'show_correct_answers_after'):
                value = getattr(self.instance, field_name, None)
                if value:
                    self.initial[field_name] = value.strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        cleaned_data = super().clean()
        available_from = cleaned_data.get('available_from')
        available_until = cleaned_data.get('available_until')
        show_correct_after = cleaned_data.get('show_correct_answers_after')

        if available_from and available_until:
            if available_until <= available_from:
                self.add_error('available_until', _('Close date must be after the open date.'))

        if show_correct_after and available_until:
            if show_correct_after < available_until:
                self.add_error(
                    'show_correct_answers_after',
                    _('Correct answers should be revealed after the quiz closes, not before.')
                )

        return cleaned_data

    def save(self, commit=True):
        quiz = super().save(commit=False)
        quiz.save()
        quiz.question_set.set(self.cleaned_data.get("questions", []))
        self.save_m2m()
        return quiz


class MCQuestionForm(forms.ModelForm):
    class Meta:
        model = MCQuestion
        exclude = ()


class MCQuestionFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """
        Custom validation for the formset to ensure:
        1. At least two choices are provided and not marked for deletion.
        2. At least one of the choices is marked as correct.
        """
        super().clean()

        # Collect non-deleted forms
        valid_forms = [
            form for form in self.forms if not form.cleaned_data.get("DELETE", True)
        ]

        valid_choices = [
            "choice_text" in form.cleaned_data.keys() for form in valid_forms
        ]
        if not all(valid_choices):
            raise forms.ValidationError("You must add a valid choice name.")

        # If all forms are deleted, raise a validation error
        if len(valid_forms) < 2:
            raise forms.ValidationError("You must provide at least two choices.")

        # Check if at least one of the valid forms is marked as correct
        correct_choices = [
            form.cleaned_data.get("correct", False) for form in valid_forms
        ]

        if not any(correct_choices):
            raise forms.ValidationError("One choice must be marked as correct.")

        if correct_choices.count(True) > 1:
            raise forms.ValidationError("Only one choice must be marked as correct.")


MCQuestionFormSet = inlineformset_factory(
    MCQuestion,
    Choice,
    form=MCQuestionForm,
    formset=MCQuestionFormSet,
    fields=["choice_text", "correct"],
    can_delete=True,
    extra=5,
)
