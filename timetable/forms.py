from django import forms
from .models import Period, TimetableEntry
from django.utils.translation import gettext_lazy as _


class PeriodForm(forms.ModelForm):
    """Form for creating and editing periods"""
    
    class Meta:
        model = Period
        fields = ['name', 'period_type', 'start_time', 'end_time', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Period 1'}),
            'period_type': forms.Select(attrs={'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '1, 2, 3...'}),
        }


class TimetableEntryForm(forms.ModelForm):
    """Form for creating and editing timetable entries"""
    
    class Meta:
        model = TimetableEntry
        fields = ['level', 'day_of_week', 'period', 'subject', 'teacher', 'classroom', 'notes']
        widgets = {
            'level': forms.Select(attrs={'class': 'form-control'}),
            'day_of_week': forms.Select(attrs={'class': 'form-control'}),
            'period': forms.Select(attrs={'class': 'form-control'}),
            'subject': forms.Select(attrs={'class': 'form-control'}),
            'teacher': forms.Select(attrs={'class': 'form-control'}),
            'classroom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Room A'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes'}),
        }
    
    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        
        if school:
            # Filter periods and subjects by school
            self.fields['period'].queryset = Period.objects.filter(school=school, period_type='LESSON')
            self.fields['subject'].queryset = self.fields['subject'].queryset.filter(school=school)
            self.fields['teacher'].queryset = self.fields['teacher'].queryset.filter(
                school=school, 
                is_lecturer=True
            )
