"""Tests for attendance sessions, records and term summaries."""

from datetime import date, timedelta

from django.urls import reverse

from attendance.models import (
    ABSENT,
    LATE,
    PRESENT,
    Attendance,
    AttendanceSession,
    AttendanceSummary,
)
from core.testing import DemoDataTestCase


class AttendanceSessionModelTests(DemoDataTestCase):
    def test_session_counts_records_for_its_level_and_date(self):
        session = AttendanceSession.objects.filter(
            school=self.school, level=self.student.level
        ).first()

        self.assertEqual(session.total_students, 2)
        self.assertEqual(session.present_count, 1)
        self.assertEqual(session.absent_count, 1)
        self.assertIn(self.student.level, str(session))

    def test_attendance_string_contains_status(self):
        record = Attendance.objects.filter(student=self.student).first()
        self.assertIn(record.status, str(record))


class AttendanceSummaryModelTests(DemoDataTestCase):
    def setUp(self):
        self.second_student = self.demo.students[self.demo_levels[0]][1]

    def _summary(self, student):
        return AttendanceSummary.objects.get(
            student=student,
            term=self.current_term,
            school=self.school,
        )

    def test_attendance_percentage_for_absent_student(self):
        summary = self._summary(self.student)

        self.assertEqual(summary.days_absent, 3)
        self.assertEqual(summary.days_present, 0)
        self.assertEqual(summary.attendance_percentage, 0.0)

    def test_attendance_percentage_for_present_student(self):
        summary = self._summary(self.second_student)

        self.assertEqual(summary.days_present, 3)
        self.assertEqual(summary.total_school_days, 3)
        self.assertEqual(summary.attendance_percentage, 100.0)

    def test_percentage_is_zero_without_school_days(self):
        summary = self._summary(self.student)
        summary.total_school_days = 0
        self.assertEqual(summary.attendance_percentage, 0.0)

    def _widen_current_term(self):
        dates = list(
            Attendance.objects.filter(student=self.student).values_list(
                "date", flat=True
            )
        )
        self.current_term.start_date = min(dates) - timedelta(days=1)
        self.current_term.end_date = max(dates) + timedelta(days=1)
        self.current_term.save(update_fields=["start_date", "end_date"])

    def test_update_summary_recalculates_all_statuses(self):
        self._widen_current_term()
        summary = self._summary(self.student)
        record = Attendance.objects.filter(student=self.student).first()
        record.status = PRESENT
        record.save()

        summary.update_summary()
        summary.refresh_from_db()

        self.assertEqual(summary.days_present, 1)
        self.assertEqual(summary.days_absent, 2)
        self.assertEqual(summary.days_late, 0)
        self.assertEqual(summary.days_excused, 0)
        self.assertEqual(summary.total_school_days, 3)

    def test_update_summary_counts_late_and_excused(self):
        self._widen_current_term()
        summary = self._summary(self.student)
        records = list(Attendance.objects.filter(student=self.student).order_by("date"))
        records[0].status = LATE
        records[0].save()
        records[1].status = "Excused"
        records[1].save()
        records[2].status = PRESENT
        records[2].save()

        summary.update_summary()
        summary.refresh_from_db()

        self.assertEqual(summary.days_present, 1)
        self.assertEqual(summary.days_late, 1)
        self.assertEqual(summary.days_excused, 1)
        self.assertEqual(summary.days_absent, 0)


class AttendanceViewTests(DemoDataTestCase):
    def test_teacher_can_open_dashboard_and_marking_page(self):
        self.client.force_login(self.teacher)

        self.assertEqual(
            self.client.get(reverse("attendance:dashboard")).status_code, 200
        )
        response = self.client.get(
            reverse("attendance:mark_attendance", args=[self.student.level])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["level"], self.student.level)

    def test_student_cannot_open_teacher_dashboard(self):
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("attendance:dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_student_and_parent_can_view_own_attendance(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("attendance:student_view"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["student"], self.student)

        self.client.force_login(self.parent_user)
        response = self.client.get(reverse("attendance:parent_view"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["student"], self.student)

    def test_parent_view_redirects_non_parents(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("attendance:parent_view"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_teacher_can_mark_attendance_via_post(self):
        self.client.force_login(self.teacher)
        target_date = date.today()

        response = self.client.post(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {
                f"status_{self.student.pk}": PRESENT,
                f"remarks_{self.student.pk}": "Arrived on time",
                "date": target_date.isoformat(),
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        record = Attendance.objects.get(
            student=self.student, date=target_date, school=self.school
        )
        self.assertEqual(record.status, PRESENT)
        self.assertEqual(record.remarks, "Arrived on time")

    def test_class_teacher_cannot_mark_class_without_allocated_course(self):
        """Class teachers only mark classes where they have a course."""
        self.client.force_login(self.class_teacher)
        self.assertEqual(self.class_teacher.assigned_level, self.demo_levels[0])

        response = self.client.get(
            reverse("attendance:mark_attendance", args=["Primary 2"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["level"], "Primary 2")
        self.assertFalse(response.context["can_mark"])

    def test_other_teacher_cannot_mark_a_claimed_register(self):
        """The first teacher to mark a class/date owns that register."""
        session = (
            AttendanceSession.objects.filter(
                school=self.school, level=self.student.level
            )
            .select_related("marked_by")
            .order_by("-date")
            .first()
        )
        self.assertIsNotNone(session)
        self.assertNotEqual(session.marked_by_id, self.teacher.pk)

        # Demo sessions can fall just before the current term start; widen the
        # term so this test exercises the register lock, not the date policy.
        self.current_term.start_date = session.date - timedelta(days=1)
        self.current_term.save(update_fields=["start_date"])

        before = Attendance.objects.get(
            student=self.student, date=session.date, school=self.school
        )

        self.client.force_login(self.teacher)
        page = self.client.get(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {"date": session.date.isoformat()},
        )
        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["can_mark"])
        self.assertIn("already been marked", page.context["read_only_reason"])

        response = self.client.post(
            reverse("attendance:save_attendance_ajax"),
            {
                "student_id": self.student.pk,
                "status": PRESENT,
                "level": self.student.level,
                "date": session.date.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 403)

        post_response = self.client.post(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {
                f"status_{self.student.pk}": PRESENT,
                "date": session.date.isoformat(),
            },
        )
        self.assertEqual(post_response.status_code, 403)

        after = Attendance.objects.get(pk=before.pk)
        self.assertEqual(after.status, before.status)

    def test_session_owner_can_continue_marking_their_register(self):
        session = (
            AttendanceSession.objects.filter(
                school=self.school, level=self.student.level
            )
            .select_related("marked_by")
            .order_by("-date")
            .first()
        )
        self.current_term.start_date = session.date - timedelta(days=1)
        self.current_term.save(update_fields=["start_date"])
        self.client.force_login(session.marked_by)

        response = self.client.post(
            reverse("attendance:save_attendance_ajax"),
            {
                "student_id": self.student.pk,
                "status": PRESENT,
                "level": self.student.level,
                "date": session.date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        record = Attendance.objects.get(
            student=self.student, date=session.date, school=self.school
        )
        self.assertEqual(record.status, PRESENT)

    def test_admin_can_view_but_cannot_mark_attendance(self):
        session = (
            AttendanceSession.objects.filter(
                school=self.school, level=self.student.level
            )
            .order_by("-date")
            .first()
        )
        self.client.force_login(self.admin)

        dashboard = self.client.get(reverse("attendance:dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["marking_levels"], [])

        page = self.client.get(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {"date": session.date.isoformat()},
        )
        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["can_mark"])
        self.assertIn("cannot mark", page.context["read_only_reason"])

        response = self.client.post(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {
                f"status_{self.student.pk}": PRESENT,
                "date": session.date.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 403)

        ajax_response = self.client.post(
            reverse("attendance:save_attendance_ajax"),
            {
                "student_id": self.student.pk,
                "status": PRESENT,
                "level": self.student.level,
                "date": session.date.isoformat(),
            },
        )
        self.assertEqual(ajax_response.status_code, 403)
        self.assertEqual(
            self.client.get(reverse("attendance:reports")).status_code, 200
        )

    def test_teacher_without_allocated_course_cannot_mark(self):
        jhs_student = self.demo.students["JHS 1"][0]
        self.client.force_login(self.demo.dep_head)

        page = self.client.get(
            reverse("attendance:mark_attendance", args=["JHS 1"])
        )
        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["can_mark"])

        response = self.client.post(
            reverse("attendance:save_attendance_ajax"),
            {
                "student_id": jhs_student.pk,
                "status": PRESENT,
                "level": "JHS 1",
                "date": date.today().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_backfill_a_recent_past_date(self):
        target = date.today() - timedelta(days=7)
        while target.weekday() >= 5:
            target -= timedelta(days=1)

        # Keep the date inside the current term so a class teacher is allowed
        # to fill in a register that was missed.
        self.current_term.start_date = target - timedelta(days=1)
        self.current_term.save(update_fields=["start_date"])
        Attendance.objects.filter(
            student=self.student, date=target, school=self.school
        ).delete()

        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {"date": target.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_late"])
        self.assertEqual(response.context["attendance_date"], target)
        self.assertEqual(response.context["attendance_term"], self.current_term)

        post_response = self.client.post(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {
                f"status_{self.student.pk}": LATE,
                f"remarks_{self.student.pk}": "Register filled after the fact",
                "date": target.isoformat(),
            },
        )

        self.assertEqual(post_response.status_code, 302)
        record = Attendance.objects.get(
            student=self.student, date=target, school=self.school
        )
        self.assertEqual(record.status, LATE)
        session = AttendanceSession.objects.get(
            school=self.school, level=self.student.level, date=target
        )
        self.assertEqual(session.term, self.current_term)
        self.assertTrue(session.was_marked_late)

    def test_future_attendance_is_rejected(self):
        self.client.force_login(self.teacher)
        future = date.today() + timedelta(days=1)

        response = self.client.get(
            reverse("attendance:mark_attendance", args=[self.student.level]),
            {"date": future.isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("attendance:dashboard"))

        ajax_response = self.client.post(
            reverse("attendance:save_attendance_ajax"),
            {
                "student_id": self.student.pk,
                "status": PRESENT,
                "level": self.student.level,
                "date": future.isoformat(),
            },
        )
        self.assertEqual(ajax_response.status_code, 400)
        self.assertFalse(
            Attendance.objects.filter(
                student=self.student, date=future, school=self.school
            ).exists()
        )

    def test_dashboard_backfill_form_redirects_to_marking_page(self):
        self.client.force_login(self.teacher)
        target = date.today()

        response = self.client.get(
            reverse("attendance:dashboard"),
            {"level": self.student.level, "date": target.isoformat()},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('attendance:mark_attendance', args=[self.student.level])}"
            f"?date={target.isoformat()}",
        )
