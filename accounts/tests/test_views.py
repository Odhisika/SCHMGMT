from django.urls import reverse
from unittest.mock import patch
from io import BytesIO
from openpyxl import Workbook
from openpyxl import load_workbook
from docx import Document
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import (
    ClassTransfer,
    Parent,
    PasswordResetAudit,
    Student,
    SubClass,
    User,
)
from accounts.tests.test_forms import PASSWORD
from core.testing import DemoDataTestCase
from school.models import School


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


class StudentImportExportTests(DemoDataTestCase):
    def test_admin_can_export_student_list_as_excel_and_word(self):
        self.client.force_login(self.admin)

        listing = self.client.get(reverse("student_list"))
        self.assertContains(listing, 'download="students.xlsx"')
        self.assertContains(listing, 'download="students.docx"')
        self.assertContains(listing, reverse("student_import"))

        for extension in ("xlsx", "docx"):
            response = self.client.get(reverse("student_export", args=[extension]))
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment; filename=", response["Content-Disposition"])
            self.assertGreater(len(response.content), 1000)
            if extension == "xlsx":
                exported = load_workbook(BytesIO(response.content), read_only=True)
                headings = list(next(exported.active.iter_rows(values_only=True)))
                self.assertIn("Class / Level", headings)
                self.assertIn("Guardian phone", headings)
                self.assertIn("Status", headings)
            else:
                document = Document(BytesIO(response.content))
                self.assertTrue(
                    any(
                        "Class / Level" in row.cells[0].text
                        for table in document.tables
                        for row in table.rows
                    )
                )

    def test_student_import_template_contains_student_profile_columns(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("student_import_template"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        import_page = self.client.get(reverse("student_import"))
        self.assertContains(import_page, 'download="student_import_template.xlsx"')
        headers = list(next(load_workbook(BytesIO(response.content), read_only=True).active.iter_rows(values_only=True)))
        self.assertIn("first_name", headers)
        self.assertIn("level", headers)
        self.assertIn("guardian_phone", headers)
        self.assertIn("bece_index_number", headers)
        self.assertNotIn("bank_account_number", headers)

    def test_excel_import_creates_student_account_with_generated_credentials(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "username", "first_name", "last_name", "gender", "date_of_birth",
            "phone", "address", "level", "program", "sub_class", "house",
            "status", "guardian_name", "guardian_phone", "admission_number",
        ])
        sheet.append([
            "", "Esi", "Boateng", "F", "2012-05-14", "0200000000", "Accra",
            "Primary 1", self.student.program.title, "", "Red House", "Active",
            "Kofi Boateng", "0240000000", "ADM-2026-01",
        ])
        output = BytesIO()
        workbook.save(output)
        upload = SimpleUploadedFile(
            "students.xlsx", output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("student_import"), {"workbook": upload})

        self.assertRedirects(response, reverse("student_list"))
        imported_user = User.objects.get(first_name="Esi", last_name="Boateng", school=self.school)
        self.assertTrue(imported_user.is_student)
        self.assertTrue(imported_user.must_change_password)
        self.assertTrue(imported_user.username)
        self.assertEqual(imported_user.admission_number, "ADM-2026-01")
        self.assertEqual(imported_user.division, "Primary")
        self.assertEqual(imported_user.guardian_phone, "0240000000")
        imported_student = Student.objects.get(student=imported_user)
        self.assertEqual(imported_student.level, "Primary 1")
        self.assertEqual(imported_student.program, self.student.program)
        self.assertEqual(imported_student.status, "ACTIVE")

    def test_excel_import_reports_errors_without_creating_accounts(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["first_name", "last_name", "level", "program"])
        sheet.append(["ImportFail", "Testcase", "Primary 1", "Missing Programme"])
        output = BytesIO()
        workbook.save(output)
        upload = SimpleUploadedFile(
            "students.xlsx", output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("student_import"), {"workbook": upload})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("does not exist in this school" in error for error in response.context["errors"]))
        self.assertFalse(User.objects.filter(first_name="ImportFail", last_name="Testcase").exists())


class StudentDivisionFilterViewTests(DemoDataTestCase):
    def test_division_selector_precedes_the_filter_form(self):
        self.client.force_login(self.admin)

        html = self.client.get(reverse("student_list")).content.decode()

        self.assertLess(html.index("studentDivisionTabs"), html.index('name="name"'))
        self.assertIn('name="division"', html)
        self.assertIn("All divisions", html)
        self.assertIn("Nursery/Pre-School", html)
        self.assertIn("Only sub-classes for the selected division are listed.", html)

    def test_selected_division_limits_sub_classes_and_results(self):
        primary_arm = SubClass.objects.create(
            school=self.school, level="Primary 1", name="A"
        )
        nursery_arm = SubClass.objects.create(
            school=self.school, level="Nursery 1", name="B"
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("student_list"), {"division": "Primary"})

        choices = response.context["filter"].filters["sub_class"].queryset
        self.assertIn(primary_arm, choices)
        self.assertNotIn(nursery_arm, choices)
        self.assertEqual(response.context["active_division"], "Primary")
        self.assertIn(self.demo.students["Primary 1"][0], response.context["active_students"])
        self.assertNotIn(self.demo.students["JHS 1"][0], response.context["active_students"])

    def test_switching_division_drops_the_stale_sub_class_filter(self):
        arm = SubClass.objects.create(school=self.school, level="Primary 1", name="A")
        self.client.force_login(self.admin)

        response = self.client.get(reverse("student_list"), {
            "division": "Primary", "sub_class": arm.pk, "name": "Ama",
        })
        nursery_tab = next(
            tab for tab in response.context["division_tabs"] if tab["key"] == "Nursery"
        )

        self.assertIn("division=Nursery", nursery_tab["url"])
        self.assertIn("name=Ama", nursery_tab["url"])
        self.assertNotIn("sub_class", nursery_tab["url"])

    def test_unknown_division_falls_back_to_all_divisions(self):
        nursery_arm = SubClass.objects.create(
            school=self.school, level="Nursery 1", name="B"
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("student_list"), {"division": "Unknown"})

        self.assertEqual(response.context["active_division"], "")
        self.assertIn(
            nursery_arm,
            response.context["filter"].filters["sub_class"].queryset,
        )


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

    def test_class_list_has_division_selector_and_plain_cards(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("class_list"))
        html = response.content.decode()

        self.assertIn("classDivisionTabs", html)
        self.assertIn("All divisions", html)
        self.assertIn("Nursery/Pre-School", html)
        self.assertIn("plain-level-card", html)
        self.assertLess(html.index("classDivisionTabs"), html.index("plain-level-card"))
        self.assertEqual(
            [code for code, _ in response.context["active_levels"]],
            [code for code, _ in response.context["levels"]],
        )

    def test_selecting_a_division_limits_class_cards(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("class_list"), {"division": "Primary"})
        html = response.content.decode()

        codes = [code for code, _ in response.context["active_levels"]]
        self.assertTrue(codes)
        self.assertTrue(all(code.startswith("Primary") for code in codes))
        self.assertNotIn("JHS 1", codes)
        self.assertEqual(response.context["active_division"], "Primary")
        self.assertIn("?division=JHS", html)

    def test_teacher_division_tabs_are_limited_to_their_division(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("class_list"))

        keys = [tab["key"] for tab in response.context["division_tabs"]]
        self.assertEqual(response.context["active_division"], "Primary")
        self.assertIn("Primary", keys)
        self.assertNotIn("JHS", keys)

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


class SubClassManagementViewTests(DemoDataTestCase):
    def setUp(self):
        self.level = "Primary 1"
        self.url_create = reverse("sub_class_create", args=[self.level])
        self.url_bulk = reverse("sub_class_bulk_create", args=[self.level])

    def test_class_list_links_to_the_sub_class_manager(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("class_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'{reverse("class_detail", args=[self.level])}?tab=subclasses',
        )
        self.assertNotContains(response, reverse("sub_class_bulk_create", args=[self.level]))

    def test_sub_class_tab_can_be_opened_directly(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("class_detail", args=[self.level]), {"tab": "subclasses"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_tab"], "subclasses")
        self.assertContains(
            response,
            'class="tab-pane fade show active" id="subclasses"',
        )

    def test_admin_can_create_a_single_sub_class(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url_create,
            {"name": "A", "capacity": 30, "class_teacher": self.teacher.pk},
        )

        self.assertRedirects(
            response, reverse("class_detail", args=[self.level]) + "?tab=subclasses"
        )
        sub_class = SubClass.objects.get(
            school=self.school, level=self.level, name="A"
        )
        self.assertEqual(sub_class.capacity, 30)
        self.assertEqual(sub_class.class_teacher, self.teacher)

    def test_feedback_is_shown_on_the_class_page(self):
        self.client.force_login(self.admin)

        response = self.client.post(self.url_create, {"name": "A"}, follow=True)

        self.assertContains(response, "added to Primary 1")

    def test_duplicate_sub_class_name_is_rejected(self):
        SubClass.objects.create(school=self.school, level=self.level, name="A")
        self.client.force_login(self.admin)

        response = self.client.post(self.url_create, {"name": "a"})

        self.assertRedirects(
            response, reverse("class_detail", args=[self.level]) + "?tab=subclasses"
        )
        self.assertEqual(
            SubClass.objects.filter(school=self.school, level=self.level).count(), 1
        )

    def test_bulk_create_uses_the_next_available_letters(self):
        SubClass.objects.create(school=self.school, level=self.level, name="A")
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url_bulk,
            {"count": 3, "scheme": "letters", "capacity": 25},
        )

        self.assertRedirects(
            response, reverse("class_detail", args=[self.level]) + "?tab=subclasses"
        )
        names = list(
            SubClass.objects.filter(school=self.school, level=self.level)
            .order_by("display_order", "name")
            .values_list("name", flat=True)
        )
        self.assertEqual(names, ["A", "B", "C", "D"])
        self.assertTrue(
            all(
                item.capacity == 25
                for item in SubClass.objects.filter(
                    school=self.school, level=self.level, name__in=["B", "C", "D"]
                )
            )
        )

    def test_bulk_create_can_use_numbers(self):
        self.client.force_login(self.admin)

        self.client.post(
            self.url_bulk, {"count": 2, "scheme": "numbers", "capacity": ""}
        )

        names = set(
            SubClass.objects.filter(school=self.school, level=self.level).values_list(
                "name", flat=True
            )
        )
        self.assertEqual(names, {"1", "2"})

    def test_teacher_cannot_create_sub_classes(self):
        self.client.force_login(self.teacher)

        self.client.post(self.url_create, {"name": "A"})

        self.assertFalse(
            SubClass.objects.filter(school=self.school, level=self.level).exists()
        )

    def test_roster_can_be_filtered_by_sub_class(self):
        sub_class = SubClass.objects.create(
            school=self.school, level=self.level, name="A"
        )
        first, second = self.demo.students[self.level]
        first.sub_class = sub_class
        first.save(update_fields=["sub_class"])

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("class_detail", args=[self.level]),
            {"sub_class": sub_class.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(first, response.context["students"])
        self.assertNotIn(second, response.context["students"])
        self.assertEqual(response.context["selected_sub_class"], sub_class)
        self.assertEqual(response.context["sub_class_counts"][sub_class.pk], 1)

    def test_student_list_can_be_filtered_by_sub_class(self):
        sub_class = SubClass.objects.create(
            school=self.school, level=self.level, name="A"
        )
        first, second = self.demo.students[self.level]
        first.sub_class = sub_class
        first.save(update_fields=["sub_class"])

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("student_list"), {"sub_class": sub_class.pk}
        )

        self.assertEqual(response.status_code, 200)
        listed = list(response.context["primary_students"])
        self.assertIn(first, listed)
        self.assertNotIn(second, listed)
        self.assertIn(
            sub_class,
            response.context["filter"].filters["sub_class"].queryset,
        )

    def test_class_page_shows_sub_class_capacity(self):
        SubClass.objects.create(
            school=self.school, level=self.level, name="A", capacity=30
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse("class_detail", args=[self.level]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0 / 30")

    def test_deleting_a_sub_class_unassigns_its_students(self):
        sub_class = SubClass.objects.create(
            school=self.school, level=self.level, name="A"
        )
        student = self.demo.students[self.level][0]
        student.sub_class = sub_class
        student.save(update_fields=["sub_class"])

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("sub_class_delete", args=[sub_class.pk])
        )

        self.assertRedirects(
            response, reverse("class_detail", args=[self.level]) + "?tab=subclasses"
        )
        student.refresh_from_db()
        self.assertIsNone(student.sub_class)
        self.assertFalse(SubClass.objects.filter(pk=sub_class.pk).exists())

    def test_changing_a_students_level_clears_an_incompatible_sub_class(self):
        sub_class = SubClass.objects.create(
            school=self.school, level=self.level, name="A"
        )
        student = self.demo.students[self.level][0]
        student.sub_class = sub_class

        student.level = "JHS 1"
        student.save()

        student.refresh_from_db()
        self.assertIsNone(student.sub_class)
        self.assertEqual(student.class_label, "JHS 1")


class StudentTransferViewTests(DemoDataTestCase):
    def setUp(self):
        self.level = "Primary 1"
        self.student = self.demo.students[self.level][0]
        self.arm_a = SubClass.objects.create(
            school=self.school, level=self.level, name="A"
        )
        self.arm_b = SubClass.objects.create(
            school=self.school, level=self.level, name="B"
        )
        self.student.sub_class = self.arm_a
        self.student.save(update_fields=["sub_class"])
        self.url = reverse("student_transfer", args=[self.student.pk])

    def test_admin_can_transfer_a_student_to_another_sub_class(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url,
            {
                "to_level": self.level,
                "to_sub_class": self.arm_b.pk,
                "note": "Balancing class sizes",
            },
        )

        self.assertRedirects(
            response,
            reverse("class_detail", args=[self.level]) + f"?sub_class={self.arm_b.pk}",
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.level, self.level)
        self.assertEqual(self.student.sub_class, self.arm_b)

        transfer = ClassTransfer.objects.get(student=self.student)
        self.assertEqual(transfer.from_label, "Primary 1 A")
        self.assertEqual(transfer.to_label, "Primary 1 B")
        self.assertEqual(transfer.transferred_by, self.admin)
        self.assertEqual(transfer.note, "Balancing class sizes")

    def test_transfer_confirmation_is_shown_on_the_target_page(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url,
            {"to_level": self.level, "to_sub_class": self.arm_b.pk},
            follow=True,
        )

        self.assertContains(
            response, "Transferred", msg_prefix="Transfer feedback missing"
        )

    def test_admin_can_transfer_a_student_to_another_class(self):
        target = SubClass.objects.create(
            school=self.school, level="JHS 1", name="C"
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url,
            {"to_level": "JHS 1", "to_sub_class": target.pk},
        )

        self.assertRedirects(
            response,
            reverse("class_detail", args=["JHS 1"]) + f"?sub_class={target.pk}",
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.level, "JHS 1")
        self.assertEqual(self.student.sub_class, target)

    def test_transfer_rejects_a_sub_class_from_another_level(self):
        target = SubClass.objects.create(
            school=self.school, level="JHS 1", name="D"
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url,
            {"to_level": self.level, "to_sub_class": target.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("to_sub_class", response.context["form"].errors)
        self.assertFalse(ClassTransfer.objects.filter(student=self.student).exists())
        self.student.refresh_from_db()
        self.assertEqual(self.student.sub_class, self.arm_a)

    def test_transfer_rejects_the_current_assignment(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url,
            {"to_level": self.level, "to_sub_class": self.arm_a.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("to_sub_class", response.context["form"].errors)
        self.assertFalse(ClassTransfer.objects.filter(student=self.student).exists())

    def test_teacher_cannot_transfer_students(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            self.url,
            {"to_level": self.level, "to_sub_class": self.arm_b.pk},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ClassTransfer.objects.filter(student=self.student).exists())
        self.student.refresh_from_db()
        self.assertEqual(self.student.sub_class, self.arm_a)

    def test_transfer_chain_is_shown_on_the_student_profile(self):
        self.client.force_login(self.admin)
        third_arm = SubClass.objects.create(
            school=self.school, level=self.level, name="C"
        )
        self.client.post(
            self.url,
            {"to_level": self.level, "to_sub_class": self.arm_b.pk},
        )
        self.client.post(
            self.url,
            {"to_level": self.level, "to_sub_class": third_arm.pk},
        )

        response = self.client.get(
            reverse("profile_single", args=[self.student.student_id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primary 1 A → Primary 1 B → Primary 1 C")
        self.assertContains(response, "Sub-class Transfers")

    def test_roster_offers_transfer_in_the_actions_menu(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("class_detail", args=[self.level]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fa-ellipsis-vertical")
        self.assertContains(response, 'data-bs-popper-config=\'{"strategy":"fixed"}\'')
        self.assertContains(response, self.url)
        self.assertContains(response, "Transfer sub-class")

    def test_history_survives_deleting_the_sub_class(self):
        self.client.force_login(self.admin)
        self.client.post(
            self.url,
            {"to_level": self.level, "to_sub_class": self.arm_b.pk},
        )
        self.arm_a.delete()
        self.arm_b.delete()

        transfer = ClassTransfer.objects.get(student=self.student)

        self.assertEqual(transfer.from_label, "Primary 1 A")
        self.assertEqual(transfer.to_label, "Primary 1 B")


class SchoolAdminManagementTests(DemoDataTestCase):
    def test_admin_can_open_administrator_pages(self):
        self.client.force_login(self.admin)

        for url_name in ("school_admin_list", "school_admin_add"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    @patch("accounts.forms.send_new_account_email")
    def test_admin_creates_another_admin_with_one_time_password(self, send_email):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("school_admin_add"),
            {
                "username": "added.admin",
                "first_name": "Added",
                "last_name": "Administrator",
                "email": "added.admin@example.test",
                "phone": "0240000200",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "added.admin")
        self.assertEqual(
            response["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0"
        )
        new_admin = User.objects.get(username="added.admin")
        temporary_password = response.context["temporary_password"]
        self.assertTrue(new_admin.is_school_admin)
        self.assertTrue(new_admin.is_staff)
        self.assertFalse(new_admin.is_superuser)
        self.assertEqual(new_admin.school, self.school)
        self.assertTrue(new_admin.must_change_password)
        self.assertTrue(new_admin.check_password(temporary_password))
        send_email.assert_called_once_with(new_admin, temporary_password)

    @patch("accounts.forms.send_new_account_email")
    def test_created_admin_is_scoped_to_current_school(self, send_email):
        other_school = School.objects.create(name="Other School")
        self.client.force_login(self.admin)

        self.client.post(
            reverse("school_admin_add"),
            {
                "school": other_school.pk,
                "first_name": "Generated",
                "last_name": "Administrator",
            },
        )

        new_admin = User.objects.filter(is_school_admin=True).exclude(pk=self.admin.pk).get()
        self.assertTrue(new_admin.username.startswith("ADM-"))
        self.assertEqual(new_admin.school, self.school)

    @patch("accounts.forms.send_new_account_email")
    def test_created_admin_can_sign_in_with_generated_credentials(self, send_email):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("school_admin_add"),
            {"first_name": "Credential", "last_name": "Administrator"},
        )
        temporary_password = response.context["temporary_password"]
        new_admin = User.objects.filter(is_school_admin=True).exclude(pk=self.admin.pk).get()

        self.client.logout()
        login = self.client.post(
            reverse("login"),
            {"username": new_admin.username, "password": temporary_password},
        )

        self.assertRedirects(login, reverse("change_password"))

    def test_teacher_cannot_manage_school_admins(self):
        self.client.force_login(self.teacher)

        for url_name in ("school_admin_list", "school_admin_add"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, "/dashboard/")

    def test_list_shows_only_current_schools_administrators(self):
        other_school = School.objects.create(name="Other School")
        outsider = User.objects.create_user(
            username="outsider.admin",
            password="StrongPass123!",
            is_school_admin=True,
            school=other_school,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("school_admin_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.admin.username)
        self.assertNotContains(response, outsider.username)
