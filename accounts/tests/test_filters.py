from django.test import TestCase
from accounts.filters import LecturerFilter, StudentFilter
from accounts.models import Student, SubClass, User
from course.models import Program
from school.models import School


class LecturerFilterTestCase(TestCase):
    def setUp(self):
        User.objects.create(
            username="user1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )
        User.objects.create(
            username="user2",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
        )
        User.objects.create(
            username="user3",
            first_name="Alice",
            last_name="Smith",
            email="alice@example.com",
        )

    def test_username_filter(self):
        filter_set = LecturerFilter(data={"username": "user1"})
        self.assertEqual(len(filter_set.qs), 1)

    def test_name_filter(self):
        filter_set = LecturerFilter(data={"name": "John"})
        self.assertEqual(len(filter_set.qs), 1)

    def test_email_filter(self):
        filter_set = LecturerFilter(data={"email": "example.com"})
        self.assertEqual(
            len(filter_set.qs), 3
        )  # All users should be returned since all have email addresses with "example.com"

    def test_combined_filters(self):
        filter_set = LecturerFilter(data={"name": "Doe", "email": "example.com"})
        self.assertEqual(
            len(filter_set.qs), 2
        )  # Both John Doe and Jane Doe should be returned

        filter_set = LecturerFilter(data={"name": "Alice", "email": "example.com"})
        self.assertEqual(
            len(filter_set.qs), 1
        )  # 1 user matches Alice with "example.com" in the email

    def test_no_filters(self):
        filter_set = LecturerFilter(data={})
        self.assertEqual(
            len(filter_set.qs), 3
        )  # All users should be returned since no filters are applied


class StudentFilterTestCase(TestCase):
    def setUp(self):
        program1 = Program.objects.create(
            title="Computer Science", summary="Program for computer science students"
        )
        program2 = Program.objects.create(
            title="Mathematics", summary="Program for mathematics students"
        )
        program3 = Program.objects.create(
            title="Computer Engineering",
            summary="Program for computer engineering students",
        )

        Student.objects.create(
            student=User.objects.create(
                username="student1",
                first_name="John",
                last_name="Doe",
                email="john@example.com",
            ),
            program=program1,
        )
        Student.objects.create(
            student=User.objects.create(
                username="student2",
                first_name="Jane",
                last_name="Williams",
                email="jane@example.com",
            ),
            program=program2,
        )
        Student.objects.create(
            student=User.objects.create(
                username="student3",
                first_name="Alice",
                last_name="Smith",
                email="alice@example.com",
            ),
            program=program3,
        )

    def test_name_filter(self):
        filtered_students = StudentFilter(
            data={"name": "John"}, queryset=Student.objects.all()
        ).qs
        self.assertEqual(filtered_students.count(), 1)

    def test_email_filter(self):
        filter_set = StudentFilter(data={"email": "example.com"})
        self.assertEqual(
            len(filter_set.qs), 3
        )  # All students should be returned since all have email addresses with "example.com"

    def test_program_filter(self):
        filter_set = StudentFilter(data={"program__title": "Computer Science"})
        self.assertEqual(len(filter_set.qs), 3)

    def test_sub_class_filter(self):
        school = School.objects.create(name="Filter School")
        sub_class = SubClass.objects.create(
            school=school, level="Primary 1", name="A"
        )
        student = Student.objects.get(student__username="student1")
        student.level = "Primary 1"
        student.sub_class = sub_class
        student.save()

        filter_set = StudentFilter(
            data={"sub_class": sub_class.pk},
            queryset=Student.objects.all(),
            school=school,
        )

        self.assertEqual(list(filter_set.qs), [student])

    def test_sub_class_choices_are_scoped_to_the_school(self):
        school = School.objects.create(name="Filter School")
        other_school = School.objects.create(name="Other Filter School")
        own_sub_class = SubClass.objects.create(
            school=school, level="Primary 1", name="A"
        )
        other_sub_class = SubClass.objects.create(
            school=other_school, level="Primary 1", name="A"
        )

        filter_set = StudentFilter(school=school)
        choices = filter_set.filters["sub_class"].queryset

        self.assertIn(own_sub_class, choices)
        self.assertNotIn(other_sub_class, choices)

    def test_sub_class_choices_are_scoped_to_the_selected_division(self):
        school = School.objects.create(name="Division School")
        primary = SubClass.objects.create(school=school, level="Primary 1", name="A")
        nursery = SubClass.objects.create(school=school, level="Nursery 1", name="B")
        jhs = SubClass.objects.create(school=school, level="JHS 1", name="C")

        primary_choices = StudentFilter(
            data={"division": "Primary"}, school=school
        ).filters["sub_class"].queryset
        self.assertIn(primary, primary_choices)
        self.assertNotIn(nursery, primary_choices)
        self.assertNotIn(jhs, primary_choices)

        nursery_choices = StudentFilter(
            data={"division": "Nursery"}, school=school
        ).filters["sub_class"].queryset
        self.assertIn(nursery, nursery_choices)
        self.assertNotIn(primary, nursery_choices)

        all_choices = StudentFilter(school=school).filters["sub_class"].queryset
        self.assertEqual(set(all_choices), {primary, nursery, jhs})
