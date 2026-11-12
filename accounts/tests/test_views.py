from django.urls import reverse
from io import BytesIO
from openpyxl import Workbook
from openpyxl import load_workbook
from docx import Document
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Parent, PasswordResetAudit, Student, User
from accounts.tests.test_forms import PASSWORD
from core.testing import DemoDataTestCase


class ProfileSecurityViewTests(DemoDataTestCase):
    def test_admin_password_reset_issues_one_time_temporary_credential(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("reset_user_password", args=[self.student_user.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0")
        self.student_user.refresh_from_db()
        temporary_password = response.context["temporary_password"]
        self.assertTrue(self.student_user.must_change_password)
        self.assertTrue(self.student_user.check_password(temporary_password))
        self.assertTrue(
            PasswordResetAudit.objects.filter(
                target_username=self.student_user.username,
                performed_by_username=self.admin.username,
            ).exists()
        )

    def test_profile_renders_for_every_role(self):
        for user in (
            self.admin,
            self.teacher,
            self.student_user,
            self.parent_user,
            self.superuser,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("profile"))
                self.assertEqual(response.status_code, 200)

    def test_admin_can_open_another_users_profile(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("profile_single", args=[self.student_user.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user"], self.student_user)
        self.assertEqual(response.context["user_type"], "Student")

    def test_opening_own_profile_redirects_to_profile_view(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("profile_single", args=[self.admin.pk]))

        self.assertRedirects(response, reverse("profile"))

    def test_teacher_cannot_open_the_admin_profile_viewer(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("profile_single", args=[self.student_user.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")


class StaffManagementWorkflowTests(DemoDataTestCase):
    def test_admin_can_export_teacher_list_as_excel_and_word(self):
        self.client.force_login(self.admin)

        listing = self.client.get(reverse("lecturer_list"))
        self.assertContains(listing, 'download="teachers_staff.xlsx"')
        self.assertContains(listing, 'download="teachers_staff.docx"')
        self.assertContains(listing, 'Change division/class')
        self.assertNotContains(listing, 'target="_blank" href="/en/accounts/create_lecturers_pdf_list/')

        for extension in ("xlsx", "docx"):
            response = self.client.get(reverse("staff_export", args=["teachers", extension]))
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment; filename=", response["Content-Disposition"])
            self.assertGreater(len(response.content), 1000)
            if extension == "xlsx":
                exported = load_workbook(BytesIO(response.content), read_only=True)
                self.assertIn("Ghana Card number", list(exported.active.values)[0])
                self.assertIn("SSNIT number", list(exported.active.values)[0])
            else:
                document = Document(BytesIO(response.content))
                self.assertTrue(any("Ghana Card number" in row.cells[0].text for table in document.tables for row in table.rows))

        pdf_response = self.client.get(reverse("lecturer_list_pdf"))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("attachment; filename=", pdf_response["Content-Disposition"])

    def test_admin_can_promote_non_teaching_staff_to_teacher(self):
        staff_member = User.objects.create_user(
            username="nonteacher", password=PASSWORD, school=self.school,
            first_name="Nana", last_name="Mensah", is_non_teaching_staff=True,
            non_teaching_position="LIBRARIAN",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("staff_promote", args=[staff_member.pk]), {
            "division": "Primary", "assigned_level": "Primary 1", "is_class_teacher": "on",
        })

        self.assertRedirects(response, reverse("lecturer_list"))
        staff_member.refresh_from_db()
        self.assertTrue(staff_member.is_teacher)
        self.assertTrue(staff_member.is_lecturer)
        self.assertFalse(staff_member.is_non_teaching_staff)
        self.assertEqual(staff_member.division, "Primary")
        self.assertEqual(staff_member.assigned_level, "Primary 1")
        self.assertTrue(staff_member.is_class_teacher)
        self.assertEqual(staff_member.department.division, "Primary")

    def test_admin_can_transfer_teacher_to_another_division_and_class(self):
        self.client.force_login(self.admin)

        edit_url = reverse("staff_edit", args=[self.teacher.pk])
        self.assertContains(self.client.get(reverse("lecturer_list")), f'{edit_url}?assignment=1')
        response = self.client.post(edit_url + "?assignment=1", {
            "division": "JHS", "assigned_level": "JHS 1", "is_class_teacher": "on",
        })

        self.assertRedirects(response, reverse("lecturer_list"))
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.division, "JHS")
        self.assertEqual(self.teacher.assigned_level, "JHS 1")
        self.assertTrue(self.teacher.is_class_teacher)
        self.assertEqual(self.teacher.department.division, "JHS")

    def test_excel_import_creates_staff_accounts_with_temporary_password_reset(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "staff_type", "username", "first_name", "last_name", "email", "phone",
            "address", "gender", "division", "assigned_level", "designation",
            "work_unit", "employment_type", "non_teaching_position", "staff_id",
        ])
        sheet.append([
            "teacher", "imported.teacher", "Esi", "Boateng", "", "0200000000",
            "Accra", "F", "Primary", "Primary 1", "Teacher", "Primary",
            "PERMANENT", "", "GES-101",
        ])
        output = BytesIO()
        workbook.save(output)
        upload = SimpleUploadedFile(
            "staff.xlsx", output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("staff_import"), {"workbook": upload})

        self.assertRedirects(response, reverse("non_teaching_staff_list"))
        imported = User.objects.get(username="imported.teacher", school=self.school)
        self.assertTrue(imported.is_teacher)
        self.assertTrue(imported.must_change_password)
        self.assertEqual(imported.division, "Primary")

    def test_staff_import_template_contains_all_staff_profile_columns(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("staff_import_template"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        import_page = self.client.get(reverse("staff_import"))
        self.assertContains(import_page, 'download="staff_import_template.xlsx"')
        sheet = load_workbook(BytesIO(response.content), read_only=True).active
        headers = list(next(sheet.iter_rows(values_only=True)))
        self.assertIn("date_of_birth", headers)
        self.assertIn("ghana_card_number", headers)
        self.assertIn("bank_account_number", headers)
        self.assertIn("emergency_contact_phone", headers)

class ProfileViewTests(DemoDataTestCase):
    def test_profile_single_scopes_users_to_the_current_school(self):
        other_school_user = User.objects.create_user(
            username="outsider",
            password=PASSWORD,
            school=None,
            is_student=True,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("profile_single", args=[other_school_user.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_profile_update_ignores_restricted_fields_for_non_admins(self):
        self.client.force_login(self.teacher)
        original_name = self.teacher.first_name
        original_phone = self.teacher.phone

        response = self.client.post(
            reverse("edit_profile"),
            {
                "first_name": "Changed",
                "last_name": self.teacher.last_name,
                "gender": self.teacher.gender or "M",
                "email": self.teacher.email,
                "phone": "+233200099999",
                "address": "New Address",
                "department": self.teacher.department_id or "",
                "picture": "",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.phone, original_phone)
        # Non-admins cannot change their name through this form.
        self.assertEqual(self.teacher.first_name, original_name)

    def test_admin_can_update_their_own_profile(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("edit_profile"),
            {
                "first_name": "Updated",
                "last_name": "Admin",
                "gender": "F",
                "email": self.admin.email,
                "phone": "+233200088888",
                "address": "Admin Street",
                "department": self.admin.department_id or "",
                "picture": "",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.first_name, "Updated")
        self.assertEqual(self.admin.phone, "+233200088888")

    def test_change_password(self):
        self.teacher.must_change_password = True
        self.teacher.save(update_fields=["must_change_password"])
        self.client.force_login(self.teacher)

        forced_change = self.client.get(reverse("profile"))
        self.assertRedirects(forced_change, reverse("change_password"))

        response = self.client.post(
            reverse("change_password"),
            {
                "old_password": "DemoPass123!",
                "new_password1": "BrandNewPass123!",
                "new_password2": "BrandNewPass123!",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.check_password("BrandNewPass123!"))
        self.assertFalse(self.teacher.must_change_password)


class StaffAndStudentManagementViewTests(DemoDataTestCase):
    def test_admin_can_save_separate_student_id_formats(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin_panel"),
            {
                "action": "save_student_id_formats",
                "student_id_nursery_prefix": "NURS",
                "student_id_nursery_pattern": "DIVISION_SEQUENCE",
                "student_id_primary_prefix": "PRI",
                "student_id_primary_pattern": "SCHOOL_DIVISION_YEAR_SEQUENCE",
                "student_id_jhs_prefix": "JUN",
                "student_id_jhs_pattern": "SCHOOL_DIVISION_SEQUENCE",
            },
        )

        self.assertRedirects(response, reverse("admin_panel"))
        self.school.refresh_from_db()
        self.assertEqual(self.school.student_id_nursery_prefix, "NURS")
        self.assertEqual(self.school.student_id_nursery_pattern, "DIVISION_SEQUENCE")
        self.assertEqual(self.school.student_id_primary_prefix, "PRI")
        self.assertEqual(self.school.student_id_jhs_prefix, "JUN")

    def test_lecturer_list_is_admin_only(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("lecturer_list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.teacher, response.context["primary_teachers"])

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("lecturer_list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_student_list_is_admin_only_and_filters_by_name(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("student_list"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            reverse("student_list"), {"name": self.student_user.first_name}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.student, response.context["filter"].qs)

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_list"))
        self.assertEqual(response.status_code, 302)

    def test_add_lecturer_creates_account_in_school(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("add_lecturer"),
            {
                "username": "added.teacher",
                "first_name": "Added",
                "last_name": "Teacher",
                "gender": "F",
                "department": "JHS",
                "division": "JHS",
                "address": "Accra",
                "phone": "0240000100",
                "email": "added.teacher@example.test",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "added.teacher")
        user = User.objects.get(username="added.teacher")
        self.assertTrue(user.is_teacher)
        self.assertTrue(user.is_lecturer)
        self.assertEqual(user.school, self.school)
        self.assertEqual(user.division, "JHS")

    def test_add_student_creates_profile_and_redirects_to_class(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("add_student"),
            {
                "username": "added.student",
                "first_name": "Added",
                "last_name": "Student",
                "gender": "M",
                "level": "Primary 1",
                "program": self.demo.programs["Primary"].pk,
                "address": "Tema",
                "phone": "0240000101",
                "email": "added.student@example.test",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "added.student")
        user = User.objects.get(username="added.student")
        self.assertEqual(user.school, self.school)
        self.assertTrue(user.is_student)
        self.assertTrue(Student.objects.filter(student=user, level="Primary 1").exists())

    def test_edit_student_updates_profile(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("student_edit", args=[self.student_user.pk]),
            {
                "first_name": "Edited",
                "last_name": "Learner",
                "gender": "F",
                "email": "edited@example.test",
                "phone": "0240000102",
                "address": "Cape Coast",
                "department": self.demo.programs["Primary"].pk,
                "picture": "",
            },
        )

        self.assertRedirects(response, reverse("student_list"))
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.first_name, "Edited")
        self.assertEqual(self.student_user.email, "edited@example.test")

    def test_delete_student_removes_user(self):
        self.client.force_login(self.admin)
        target = self.demo.students["JHS 1"][0]

        response = self.client.get(reverse("student_delete", args=[target.pk]))

        self.assertRedirects(response, reverse("student_list"))
        self.assertFalse(Student.objects.filter(pk=target.pk).exists())
        self.assertFalse(User.objects.filter(pk=target.student_id).exists())

    def test_add_parent_creates_linked_parent_account(self):
        self.client.force_login(self.admin)
        student = self.demo.students[self.demo_levels[0]][1]
        # Every seeded student already has a guardian, so free this one up.
        Parent.objects.filter(student=student).delete()

        response = self.client.post(
            reverse("add_parent"),
            {
                "username": "added.parent",
                "first_name": "Added",
                "last_name": "Parent",
                "address": "Accra",
                "phone": "0240000103",
                "email": "added.parent@example.test",
                "student": student.pk,
                "relation_ship": "Father",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        parent = Parent.objects.get(user__username="added.parent")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "added.parent")
        self.assertEqual(parent.user.school, self.school)
        self.assertEqual(parent.student, student)

    def test_validate_username_endpoint(self):
        self.client.force_login(self.admin)

        taken = self.client.get(
            reverse("validate_username"), {"username": self.teacher.username}
        )
        free = self.client.get(
            reverse("validate_username"), {"username": "totally.free.username"}
        )

        self.assertTrue(taken.json()["is_taken"])
        self.assertFalse(free.json()["is_taken"])


class ClassWorkspaceViewTests(DemoDataTestCase):
    def test_admin_sees_all_classes(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("class_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["levels"]), len(self._level_choices()))

    @staticmethod
    def _level_choices():
        from django.conf import settings

        return settings.LEVEL_CHOICES

    def test_teacher_only_sees_their_division_classes(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("class_list"))

        self.assertEqual(response.status_code, 200)
        levels = [code for code, _ in response.context["levels"]]
        self.assertTrue(levels)
        self.assertTrue(all(code.startswith("Primary") for code in levels))
        self.assertNotIn("JHS 1", levels)

    def test_teacher_can_open_a_class_in_their_division(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("class_detail", args=["Primary 1"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["level_code"], "Primary 1")
        self.assertIn(self.student, response.context["students"])

    def test_teacher_cannot_open_a_class_from_another_division(self):
        self.client.force_login(self.jhs_teacher)

        response = self.client.get(
            reverse("class_detail", args=["Primary 1"])
        )

        self.assertRedirects(response, reverse("class_list"))

    def test_admin_can_open_any_class(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("class_detail", args=["JHS 1"]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.demo.students["JHS 1"][0], response.context["students"])
