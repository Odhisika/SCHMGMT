from django import forms
from django.db.models import Q
import django_filters

from school.division_utils import (
    get_division_choices,
    get_levels_for_division,
)

from .models import (
    STUDENT_STATUS_ACTIVE,
    STUDENT_STATUS_CHOICES,
    Student,
    SubClass,
    User,
)


class LecturerFilter(django_filters.FilterSet):
    username = django_filters.CharFilter(lookup_expr="exact", label="")
    name = django_filters.CharFilter(method="filter_by_name", label="")
    email = django_filters.CharFilter(lookup_expr="icontains", label="")

    class Meta:
        model = User
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Change html classes and placeholders
        self.filters["username"].field.widget.attrs.update(
            {"class": "au-input", "placeholder": "ID No."}
        )
        self.filters["name"].field.widget.attrs.update(
            {"class": "au-input", "placeholder": "Name"}
        )
        self.filters["email"].field.widget.attrs.update(
            {"class": "au-input", "placeholder": "Email"}
        )

    def filter_by_name(self, queryset, name, value):
        return queryset.filter(
            Q(first_name__icontains=value) | Q(last_name__icontains=value)
        )


class StudentFilter(django_filters.FilterSet):
    STATUS_CHOICES = (("ALL", "All statuses"),) + tuple(STUDENT_STATUS_CHOICES)

    # The division is selected from the tabs above this form, so it is carried
    # as a hidden value while the remaining filters stay visible.
    division = django_filters.ChoiceFilter(
        field_name="student__division",
        choices=get_division_choices(),  # replaced with school-specific choices in __init__
        label="",
        empty_label="All divisions",
        widget=forms.HiddenInput,
    )
    id_no = django_filters.CharFilter(
        field_name="student__username", lookup_expr="exact", label=""
    )
    name = django_filters.CharFilter(
        field_name="student__name", method="filter_by_name", label=""
    )
    email = django_filters.CharFilter(
        field_name="student__email", lookup_expr="icontains", label=""
    )
    program = django_filters.CharFilter(
        field_name="program__title", lookup_expr="icontains", label=""
    )
    status = django_filters.ChoiceFilter(
        choices=STATUS_CHOICES,
        method="filter_status",
        label="",
        empty_label="Active students",
    )
    sub_class = django_filters.ModelChoiceFilter(
        queryset=SubClass.objects.all(),
        field_name="sub_class",
        label="",
        empty_label="All sub-classes",
    )

    class Meta:
        model = Student
        fields = [
            "division",
            "id_no",
            "name",
            "email",
            "program",
            "sub_class",
            "status",
        ]

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)

        division_choices = get_division_choices(school)
        self.filters["division"].field.choices = division_choices
        valid_divisions = {value for value, _ in division_choices}

        if school is not None:
            sub_classes = SubClass.objects.filter(school=school, is_active=True)
            # Sub-classes only belong to one division's class levels. Narrow the
            # choices to the selected division so a Nursery roster can never be
            # filtered with a Primary or JHS sub-class.
            division = None
            if self.is_bound:
                division = self.data.get("division")
            else:
                division = self.form.initial.get("division")
            if division in valid_divisions:
                sub_classes = sub_classes.filter(
                    level__in=get_levels_for_division(division, school=school)
                )
            self.filters["sub_class"].queryset = sub_classes

        # Change html classes and placeholders
        self.filters["id_no"].field.widget.attrs.update(
            {"class": "form-control form-control-sm", "placeholder": "Student ID"}
        )
        self.filters["name"].field.widget.attrs.update(
            {"class": "form-control form-control-sm", "placeholder": "Search by name"}
        )
        self.filters["email"].field.widget.attrs.update(
            {"class": "form-control form-control-sm", "placeholder": "Search by email"}
        )
        self.filters["program"].field.widget.attrs.update(
            {"class": "form-control form-control-sm", "placeholder": "Program"}
        )
        self.filters["status"].field.widget.attrs.update(
            {"class": "form-select form-select-sm"}
        )
        self.filters["sub_class"].field.widget.attrs.update(
            {"class": "form-select form-select-sm"}
        )

    def filter_status(self, queryset, name, value):
        if value == "ALL":
            return queryset
        return queryset.filter(status=value)

    def filter_by_name(self, queryset, name, value):
        return queryset.filter(
            Q(student__first_name__icontains=value)
            | Q(student__last_name__icontains=value)
        )
