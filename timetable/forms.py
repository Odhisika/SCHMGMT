from django import forms
from .models import Period, TimetableEntry
from django.utils.translation import gettext_lazy as _


class PeriodForm(forms.ModelForm):
    """Form for creating and editing periods"""
    
    class Meta:
        model = Period
        fields = ['division', 'name', 'period_type', 'start_time', 'end_time', 'order']
        widgets = {
            'division': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Period 1'}),
            'period_type': forms.Select(attrs={'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '1, 2, 3...'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        division = cleaned_data.get('division')
        order = cleaned_data.get('order')
        
        # If school is set (passed from view), check uniqueness
        if self.school and division is not None and order is not None:
            duplicates = Period.objects.filter(
                school=self.school,
                division=division,
                order=order
            )
            
            # Exclude current instance if editing
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
                
            if duplicates.exists():
                raise forms.ValidationError(
                    f"Period order {order} already exists for {division or 'Global'} division."
                )
        
        return cleaned_data


class TimetableEntryForm(forms.ModelForm):
    """Form for creating and editing timetable entries"""
    
    class Meta:
        model = TimetableEntry
        fields = ['level', 'day_of_week', 'period', 'subject', 'teacher', 'classroom', 'notes']
        widgets = {
            'level': forms.Select(attrs={'class': 'form-control', 'onchange': 'filterPeriodsByLevel(this.value)'}),
            'day_of_week': forms.Select(attrs={'class': 'form-control'}),
            'period': forms.Select(attrs={'class': 'form-control'}),
            'subject': forms.Select(attrs={'class': 'form-control'}),
            'teacher': forms.Select(attrs={'class': 'form-control'}),
            'classroom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Room A'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes'}),
        }
    
    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        level_code = kwargs.pop('level_code', None)
        super().__init__(*args, **kwargs)
        
        if school:
            # Filter periods and subjects by school
            periods_qs = Period.objects.filter(school=school)
            
            # If level is known, filter periods by that level's division
            # This handles initial loads and pre-filled forms
            target_level = level_code or self.initial.get('level') or (self.instance.level if self.instance.pk else None)
            
            if target_level:
                from accounts.utils import get_division_for_level
                division = get_division_for_level(target_level)
                if division:
                    # Filter periods for this division OR global periods (if any)
                    periods_qs = periods_qs.filter(division=division)
                
                # Filter subjects to only those available for this level
                from course.models import Course
                self.fields['subject'].queryset = Course.objects.filter(school=school, level=target_level)
                
                # Filter teachers by division
                if division:
                    self.fields['teacher'].queryset = self.fields['teacher'].queryset.filter(division=division)
            else:
                self.fields['subject'].queryset = self.fields['subject'].queryset.filter(school=school)
            
            self.fields['period'].queryset = periods_qs.filter(period_type='LESSON')
            self.fields['teacher'].queryset = self.fields['teacher'].queryset.filter(
                school=school, 
                is_lecturer=True
            )
    
    def clean(self):
        cleaned_data = super().clean()
        school = self.school if hasattr(self, 'school') else None
        
        # If school not in self, try to get from instance or initial (context dependent)
        if not school and self.instance.pk:
            school = self.instance.school
            
        subject = cleaned_data.get('subject')
        day_of_week = cleaned_data.get('day_of_week')
        level = cleaned_data.get('level')
        period = cleaned_data.get('period')
        
        # Standard validation for duplicates
        if subject and day_of_week and level and school:
            # Check if this subject is already scheduled for this class on this day
            # Exclude current instance if editing
            duplicates = TimetableEntry.objects.filter(
                school=school,
                level=level,
                day_of_week=day_of_week,
                subject=subject,
                term__is_current_term=True  # Assuming we only care about current term
            )
            
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
                
            if duplicates.exists():
                raise forms.ValidationError(
                    f"{subject} is already scheduled for {level} on {dict(TimetableEntry.DAYS_OF_WEEK).get(day_of_week)}."
                )
        
        return cleaned_data
