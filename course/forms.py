from django import forms
from accounts.models import User
from core.models import Term
from .models import Program, Course, CourseAllocation, Upload, UploadVideo, LessonNote


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})


class CourseAddForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["code"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})
        self.fields["program"].widget.attrs.update({"class": "form-control"})
        self.fields["level"].widget.attrs.update({"class": "form-control"})
        self.fields["term"].widget.attrs.update({"class": "form-control"})


class CourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.none(),
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "browser-default checkbox"}
        ),
        required=True,
    )
    teacher = forms.ModelChoiceField(
        queryset=User.objects.none(),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="Lecturer",
    )

    class Meta:
        model = CourseAllocation
        fields = ["teacher", "courses"]

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        division_filter = kwargs.pop("division_filter", None)
        super(CourseAllocationForm, self).__init__(*args, **kwargs)
        
        if request:
            teachers = User.objects.filter(is_lecturer=True, school=request.school)
            courses = Course.objects.filter(school=request.school).order_by("program", "level")
            
            # Apply Division Filter if present
            if division_filter:
                from accounts.utils import get_levels_for_division
                # Filter teachers by division
                teachers = teachers.filter(division=division_filter)
                
                # Filter courses by levels in that division
                division_levels = get_levels_for_division(division_filter)
                courses = courses.filter(level__in=division_levels)

            self.fields["teacher"].queryset = teachers
            self.fields["courses"].queryset = courses

            # Update teacher labels to show department and division
            teacher_choices = []
            for t in teachers:
                info = []
                if t.department: info.append(t.department.title)
                if t.division: info.append(t.division)
                info_str = f" [{', '.join(info)}]" if info else ""
                
                teacher_choices.append((t.id, f"{t.get_full_name}{info_str}"))
            self.fields["teacher"].choices = [("", "---------")] + teacher_choices
        else:
            self.fields["teacher"].queryset = User.objects.filter(is_lecturer=True)
            self.fields["courses"].queryset = Course.objects.all().order_by("level")


class EditCourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    teacher = forms.ModelChoiceField(
        queryset=User.objects.none(),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="Lecturer",
    )

    class Meta:
        model = CourseAllocation
        fields = ["teacher", "courses"]

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super(EditCourseAllocationForm, self).__init__(*args, **kwargs)
        if request:
            teachers = User.objects.filter(is_lecturer=True, school=request.school)
            self.fields["teacher"].queryset = teachers
            courses_qs = Course.objects.filter(school=request.school).order_by(
                "program", "level"
            )

            # If we are editing, filter courses by the teacher's department
            if self.instance and self.instance.teacher.department:
                courses_qs = courses_qs.filter(program=self.instance.teacher.department)

            self.fields["courses"].queryset = courses_qs

            # Update teacher labels to show department
            teacher_choices = []
            for t in teachers:
                dept_label = f" [{t.department.title}]" if t.department else ""
                teacher_choices.append((t.id, f"{t.get_full_name}{dept_label}"))
            self.fields["teacher"].choices = [("", "---------")] + teacher_choices
        else:
            self.fields["teacher"].queryset = User.objects.filter(is_lecturer=True)
            self.fields["courses"].queryset = Course.objects.all().order_by("level")


# Upload files to specific course
class UploadFormFile(forms.ModelForm):
    class Meta:
        model = Upload
        fields = (
            "title",
            "file",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})


# Upload video to specific course
class UploadFormVideo(forms.ModelForm):
    class Meta:
        model = UploadVideo
        fields = (
            "title",
            "video",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["video"].widget.attrs.update({"class": "form-control"})


# Lesson Note Form
class LessonNoteForm(forms.ModelForm):
    class Meta:
        model = LessonNote
        fields = [
            'course', 'term', 'week_number', 'title', 'topic',
            'objectives', 'content', 'methodology', 'assessment',
            'resources_needed', 'homework', 'attachment'
        ]
        widgets = {
            'objectives': forms.Textarea(attrs={'rows': 3}),
            'content': forms.Textarea(attrs={'rows': 4}),
            'methodology': forms.Textarea(attrs={'rows': 3}),
            'assessment': forms.Textarea(attrs={'rows': 2}),
            'resources_needed': forms.Textarea(attrs={'rows': 2}),
            'homework': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Apply form-control class to all fields
        for field_name, field in self.fields.items():
            if field_name == 'attachment':
                field.widget.attrs.update({'class': 'form-control-file'})
            else:
                field.widget.attrs.update({'class': 'form-control'})
        
        # Filter courses based on user's allocated courses and division
        if user:
            # Get courses allocated to this teacher
            allocated_course_ids = CourseAllocation.objects.filter(
                teacher=user
            ).values_list('courses__id', flat=True)
            
            # Filter by division if not admin
            if not (user.is_superuser or user.is_school_admin):
                self.fields['course'].queryset = Course.objects.filter(
                    id__in=allocated_course_ids,
                    level__in=user.get_division_levels()
                ).order_by('level', 'title')
            else:
                self.fields['course'].queryset = Course.objects.filter(
                    id__in=allocated_course_ids
                ).order_by('level', 'title')
        
        # Filter to current and future terms
        self.fields['term'].queryset = Term.objects.all().order_by('-is_current_term', '-term')


class LessonNoteAdminReviewForm(forms.ModelForm):
    """Form for admin to review and approve/reject lesson notes"""
    class Meta:
        model = LessonNote
        fields = ['status', 'admin_comments']
        widgets = {
            'admin_comments': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only allow APPROVED or REJECTED status
        self.fields['status'].choices = [
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Needs Revision'),
        ]
        self.fields['status'].widget.attrs.update({'class': 'form-control'})
        self.fields['admin_comments'].widget.attrs.update({'class': 'form-control'})
        self.fields['admin_comments'].required = True
