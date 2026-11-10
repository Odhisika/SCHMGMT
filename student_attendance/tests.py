"""Tests for the student_attendance app models."""

from datetime import date, timedelta

from core.testing import DemoDataTestCase
from student_attendance.models import AttendanceRecord, AttendanceSession


class StudentAttendanceModelTests(DemoDataTestCase):
    def setUp(self):
        self.session = AttendanceSession.objects.create(
            school=self.school,
            term=self.current_term,
            level=self.student.level,
            date=date.today() + timedelta(days=1),
            marked_by=self.teacher,
            notes="Test session",
        )
        self.second_student = self.demo.students[self.demo_levels[0]][1]
        self.third_student = self.demo.students[self.demo_levels[1]][1]

    def _record(self, student, status):
        return AttendanceRecord.objects.create(
            session=self.session,
            student=student,
            status=status,
        )

    def test_session_counts_by_status(self):
        self._record(self.student, "PRESENT")
        self._record(self.second_student, "ABSENT")
        self._record(self.third_student, "LATE")

        self.assertEqual(self.session.total_students, 3)
        self.assertEqual(self.session.present_count, 1)
        self.assertEqual(self.session.absent_count, 1)
        self.assertEqual(self.session.late_count, 1)

    def test_record_string_contains_status_label(self):
        record = self._record(self.student, "EXCUSED")

        self.assertIn("Excused", str(record))
        self.assertEqual(record.get_status_display(), "Excused")

    def test_session_string_contains_level_and_date(self):
        rendered = str(self.session)

        self.assertIn("Primary 1", rendered)
        self.assertIn(str(self.session.date), rendered)
