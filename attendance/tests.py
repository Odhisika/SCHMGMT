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
