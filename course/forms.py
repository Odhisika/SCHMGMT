from django import forms
from accounts.models import User
from .models import Program, Course, CourseAllocation, Upload, UploadVideo


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
        super(CourseAllocationForm, self).__init__(*args, **kwargs)
        if request:
            teachers = User.objects.filter(is_lecturer=True, school=request.school)
            self.fields["teacher"].queryset = teachers
            self.fields["courses"].queryset = Course.objects.filter(
                school=request.school
            ).order_by("program", "level")

            # Update teacher labels to show department
            teacher_choices = []
            for t in teachers:
                dept_label = f" [{t.department.title}]" if t.department else ""
                teacher_choices.append((t.id, f"{t.get_full_name}{dept_label}"))
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
