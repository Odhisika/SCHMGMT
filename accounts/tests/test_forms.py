from unittest.mock import patch

from django.test import TestCase

from accounts.forms import (
    EmailValidationOnForgotPassword,
    ParentAddForm,
    StaffAddForm,
    StudentAddForm,
)
from accounts.models import Parent, Student, User
from course.models import Program
from school.models import School

PASSWORD = "StrongPass123!"


class AccountFormTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Forms Academy")
        cls.program = Program.objects.create(
            title="Primary Section", school=cls.school, division="Primary"
        )

    def test_date_fields_use_the_native_date_picker(self):
        for form_class in (StaffAddForm, StudentAddForm):
            with self.subTest(form=form_class.__name__):
                form = form_class(school=self.school)
                rendered = str(form["date_of_birth"])
                self.assertIn('type="date"', rendered)
                self.assertIn('name="date_of_birth"', rendered)


class StaffAddFormTests(AccountFormTestBase):
    def test_creates_teacher_in_the_current_school(self):
        form = StaffAddForm(
            data={
                "username": "new.teacher",
                "first_name": "New",
                "last_name": "Teacher",
                "gender": "M",
                "division": "Primary",
                "address": "Accra",
                "phone": "0240000000",
                "email": "new.teacher@example.test",
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.school, self.school)
        self.assertTrue(user.is_teacher)
        self.assertTrue(user.is_lecturer)
        self.assertEqual(user.division, "Primary")
        self.assertEqual(user.department, self.program)
        self.assertEqual(user.department.school, self.school)
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.check_password(form.temporary_password))

    def test_generates_credentials_when_username_is_blank(self):
        form = StaffAddForm(
            data={
                "first_name": "Generated",
                "last_name": "Teacher",
                "gender": "F",
                "division": "JHS",
                "address": "Kumasi",
                "phone": "0240000001",
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertTrue(user.username.startswith("TEA-"))
        self.assertTrue(user.has_usable_password())
        self.assertEqual(user.department.division, "JHS")
        self.assertEqual(user.email, "")
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.check_password(form.temporary_password))

    @patch("accounts.forms.send_new_account_email")
    def test_sends_generated_credentials_by_email_when_available(
        self, send_email
    ):
        form = StaffAddForm(
            data={
                "username": "new.teacher",
                "first_name": "New",
                "last_name": "Teacher",
                "gender": "M",
                "division": "Primary",
                "address": "Accra",
                "phone": "0240000000",
                "email": "new.teacher@example.test",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        send_email.assert_called_once_with(user, form.temporary_password)
        self.assertFalse(user.check_password(PASSWORD))
        self.assertTrue(user.must_change_password)


class StudentAddFormTests(AccountFormTestBase):
    def test_generated_student_id_uses_school_and_division_format(self):
        form = StudentAddForm(
            data={
                "first_name": "Generated",
                "last_name": "Primary",
                "gender": "F",
                "level": "Primary 1",
                "program": self.program.pk,
                "address": "Tema",
                "phone": "0240000002",
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.username, f"S{self.school.pk}-PRI-{user.date_joined.year}-0001")
        self.assertEqual(user.admission_number, user.username)

    def test_student_can_be_created_without_email_with_temporary_password(self):
        form = StudentAddForm(
            data={
                "username": "no.email.student",
                "first_name": "No",
                "last_name": "Email",
                "gender": "F",
                "level": "Primary 1",
                "program": self.program.pk,
                "address": "Tema",
                "phone": "0240000002",
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.email, "")
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.check_password(form.temporary_password))

    def test_creates_student_profile_in_the_current_school(self):
        form = StudentAddForm(
            data={
                "username": "new.student",
                "first_name": "New",
                "last_name": "Student",
                "gender": "F",
                "level": "Primary 1",
                "program": self.program.pk,
                "address": "Tema",
                "phone": "0240000002",
                "email": "new.student@example.test",
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.school, self.school)
        self.assertTrue(user.is_student)
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.check_password(form.temporary_password))
        student = Student.objects.get(student=user)
        self.assertEqual(student.level, "Primary 1")
        self.assertEqual(student.program, self.program)

    @patch("accounts.forms.send_new_account_email")
    def test_sends_generated_credentials_by_email_when_available(
        self, send_email
    ):
        form = StudentAddForm(
            data={
                "username": "new.student",
                "first_name": "New",
                "last_name": "Student",
                "gender": "F",
                "level": "Primary 1",
                "program": self.program.pk,
                "address": "Tema",
                "phone": "0240000002",
                "email": "new.student@example.test",
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        send_email.assert_called_once_with(user, form.temporary_password)

    def test_program_queryset_is_scoped_to_the_school(self):
        other_school = School.objects.create(name="Other Academy")
        other_program = Program.objects.create(
            title="Other Section", school=other_school
        )

        form = StudentAddForm(school=self.school)

        self.assertIn(self.program, form.fields["program"].queryset)
        self.assertNotIn(other_program, form.fields["program"].queryset)

    def test_rejects_other_schools_program(self):
        other_school = School.objects.create(name="Another Academy")
        other_program = Program.objects.create(
            title="Another Section", school=other_school
        )

        form = StudentAddForm(
            data={
                "username": "bad.program",
                "first_name": "Bad",
                "last_name": "Program",
                "gender": "M",
                "level": "Primary 1",
                "program": other_program.pk,
                "address": "Accra",
                "phone": "0240000003",
                "email": "bad.program@example.test",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
            school=self.school,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("program", form.errors)


class ParentAddFormTests(AccountFormTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.student_user = User.objects.create_user(
            username="parent.student",
            password=PASSWORD,
            school=cls.school,
            is_student=True,
        )
        cls.student = Student.objects.create(
            student=cls.student_user, level="Primary 1", program=cls.program
        )

    def test_creates_parent_account_linked_to_student(self):
        form = ParentAddForm(
            data={
                "username": "new.parent",
                "first_name": "New",
                "last_name": "Parent",
                "address": "Accra",
                "phone": "0240000004",
                "email": "new.parent@example.test",
                "student": self.student.pk,
                "relation_ship": "Mother",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        parent = form.save()

        self.assertIsInstance(parent, Parent)
        self.assertEqual(parent.user.school, self.school)
        self.assertTrue(parent.user.is_parent)
        self.assertEqual(parent.student, self.student)
        self.assertEqual(parent.relation_ship, "Mother")

    def test_student_choices_are_scoped_to_the_school(self):
        other_school = School.objects.create(name="Distant Academy")
        other_user = User.objects.create_user(
            username="other.student",
            password=PASSWORD,
            school=other_school,
            is_student=True,
        )
        other_student = Student.objects.create(student=other_user, level="JHS 1")

        form = ParentAddForm(school=self.school)

        self.assertIn(self.student, form.fields["student"].queryset)
        self.assertNotIn(other_student, form.fields["student"].queryset)

    def test_creates_parent_without_email_or_password(self):
        form = ParentAddForm(
            data={
                "first_name": "No",
                "last_name": "Email",
                "address": "Accra",
                "phone": "0240000005",
                "student": self.student.pk,
                "relation_ship": "Mother",
            },
            school=self.school,
        )

        self.assertTrue(form.is_valid(), form.errors)
        parent = form.save()

        self.assertTrue(parent.user.username.startswith("PAR-"))
        self.assertFalse(parent.user.email)
        self.assertTrue(parent.user.must_change_password)
        self.assertTrue(parent.user.check_password(form.temporary_password))
        self.assertEqual(parent.first_name, "No")


class PasswordResetFormTests(AccountFormTestBase):
    def test_known_active_email_is_accepted(self):
        User.objects.create_user(
            username="known", email="known@example.test", password=PASSWORD
        )
        form = EmailValidationOnForgotPassword(data={"email": "known@example.test"})

        self.assertTrue(form.is_valid(), form.errors)

    def test_unknown_email_is_rejected(self):
        form = EmailValidationOnForgotPassword(data={"email": "missing@example.test"})

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
