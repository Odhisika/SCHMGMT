from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import Student, User
from attendance.models import Attendance, AttendanceSession, AttendanceSummary
from core.demo_data import DEMO_PASSWORD, DEMO_SCHOOL_SLUG, build_demo_data
from core.models import House, NewsAndEvents, Term, TermWeek
from core.testing import DemoDataTestCase
from course.models import Course, Program
from fees.models import (
    FeeItem,
    FeeStructure,
    Payment,
    SchoolBankAccount,
    StudentFeeAssignment,
    StudentPaymentReference,
)
from quiz.models import Assignment, Quiz
from resources.models import CourseFile, CourseVideo
from result.models import (
    BECEMockExam,
    PromotionRequest,
    Result,
    ResultEditRequest,
    TakenCourse,
)
from school.models import GradeWeightConfig, PromotionPolicy, School
from timetable.models import Period, TimetableEntry


class DemoDataIntegrityTests(DemoDataTestCase):
    """The builder produces the complete relational graph tests rely on."""

    def test_core_entities_are_created(self):
        self.assertEqual(self.demo.school.slug, DEMO_SCHOOL_SLUG)
        self.assertEqual(School.objects.count(), 1)
        self.assertTrue(GradeWeightConfig.objects.filter(school=self.school).exists())
        self.assertTrue(PromotionPolicy.objects.filter(school=self.school).exists())

        self.assertEqual(Term.objects.filter(school=self.school).count(), 3)
        self.assertEqual(
            TermWeek.objects.filter(term=self.current_term).count(), 14
        )
        self.assertEqual(House.objects.filter(school=self.school).count(), 4)
        self.assertEqual(Program.objects.filter(school=self.school).count(), 4)

    def test_users_cover_every_role(self):
        self.assertTrue(self.superuser.is_superuser)
        self.assertIsNone(self.superuser.school)

        self.assertTrue(self.admin.is_school_admin)
        self.assertEqual(self.admin.school, self.school)

        self.assertTrue(self.teacher.is_teacher)
        self.assertTrue(self.teacher.is_lecturer)
        self.assertTrue(self.class_teacher.is_class_teacher)
        self.assertTrue(self.demo.dep_head.is_dep_head)
        self.assertTrue(self.parent_user.is_parent)
        self.assertTrue(self.student_user.is_student)

        self.assertEqual(User.objects.filter(is_student=True).count(), 4)
        self.assertEqual(User.objects.filter(is_parent=True).count(), 2)

    def test_login_credentials_work_for_seeded_users(self):
        self.assertTrue(
            self.client.login(username="admin", password=DEMO_PASSWORD)
        )
        self.client.logout()
        self.assertTrue(
            self.client.login(username="student.primary1.1", password=DEMO_PASSWORD)
        )

    def test_courses_and_enrollments(self):
        self.assertEqual(Course.objects.filter(school=self.school).count(), 10)
        self.assertEqual(
            list(self.demo.courses[self.demo_levels[0]][0].code.split("-")),
            ["ENG", "PRIMARY1"],
        )
        self.assertEqual(TakenCourse.objects.filter(school=self.school).count(), 20)
        self.assertEqual(Result.objects.filter(school=self.school).count(), 4)
        self.assertTrue(all(result.term_average is not None for result in self.demo.results))

    def test_attendance_sessions_records_and_summaries(self):
        self.assertEqual(
            AttendanceSession.objects.filter(school=self.school).count(), 6
        )
        self.assertEqual(Attendance.objects.filter(school=self.school).count(), 12)
        summaries = AttendanceSummary.objects.filter(school=self.school)
        self.assertEqual(summaries.count(), 4)
        for summary in summaries:
            self.assertEqual(summary.total_school_days, 3)
            self.assertEqual(
                summary.days_present + summary.days_absent + summary.days_late,
                3,
            )

    def test_timetable_periods_and_entries(self):
        self.assertEqual(Period.objects.filter(school=self.school).count(), 24)
        self.assertEqual(
            TimetableEntry.objects.filter(school=self.school).count(), 60
        )

    def test_fees_assignments_payments_and_accounts(self):
        self.assertEqual(FeeStructure.objects.filter(school=self.school).count(), 2)
        self.assertEqual(FeeItem.objects.filter(fee_structure__school=self.school).count(), 12)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(student__student__school=self.school).count(),
            4,
        )
        self.assertEqual(Payment.objects.filter(school=self.school).count(), 4)
        self.assertEqual(SchoolBankAccount.objects.filter(school=self.school).count(), 2)
        self.assertEqual(StudentPaymentReference.objects.count(), 4)

        for structure in FeeStructure.objects.filter(school=self.school):
            item_total = sum(item.amount for item in structure.items.all())
            self.assertEqual(structure.amount, item_total)

    def test_learning_resources_quizzes_and_workflows(self):
        self.assertEqual(Quiz.objects.count(), 2)
        self.assertEqual(Assignment.objects.count(), 2)
        self.assertEqual(CourseFile.objects.filter(school=self.school).count(), 2)
        self.assertEqual(CourseVideo.objects.filter(school=self.school).count(), 2)
        self.assertEqual(NewsAndEvents.objects.filter(school=self.school).count(), 3)
        self.assertEqual(ResultEditRequest.objects.filter(school=self.school).count(), 1)
        self.assertEqual(PromotionRequest.objects.filter(school=self.school).count(), 1)
        # BECE mocks only exist for the final JHS class, which is not in this slice.
        self.assertEqual(BECEMockExam.objects.count(), 0)

    def test_student_links_and_houses(self):
        for level, students in self.demo.students.items():
            self.assertEqual(len(students), 2)
            for student in students:
                self.assertIsInstance(student, Student)
                self.assertEqual(student.student.school, self.school)
                self.assertIn(student.house, [h.name for h in House.objects.all()])
                # Auto-created by accounts.signals.
                self.assertTrue(student.attendance_summaries.exists())


class DemoDataToggleTests(TestCase):
    """Optional slices can be disabled for lighter fixtures."""

    @classmethod
    def setUpTestData(cls):
        cls.demo = build_demo_data(
            levels=["Primary 1"],
            students_per_level=1,
            attendance_days=1,
            timetable=False,
            quizzes=False,
            resources=False,
            seed=7,
        )

    def test_optional_slices_are_skipped(self):
        self.assertEqual(Period.objects.count(), 0)
        self.assertEqual(TimetableEntry.objects.count(), 0)
        self.assertEqual(Quiz.objects.count(), 0)
        self.assertEqual(CourseFile.objects.count(), 0)
        self.assertEqual(CourseVideo.objects.count(), 0)
        self.assertEqual(Course.objects.count(), 5)
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(Attendance.objects.count(), 1)
        # No JHS levels were requested, so no BECE mock data.
        self.assertEqual(BECEMockExam.objects.count(), 0)


class SeedCommandTests(DemoDataTestCase):
    def test_refuses_to_seed_over_existing_demo_school(self):
        before = {
            "schools": School.objects.count(),
            "users": User.objects.count(),
            "courses": Course.objects.count(),
        }
        stderr = StringIO()

        call_command("seed_demo_data", stdout=StringIO(), stderr=stderr)

        self.assertIn("already exists", stderr.getvalue())
        self.assertEqual(School.objects.count(), before["schools"])
        self.assertEqual(User.objects.count(), before["users"])
        self.assertEqual(Course.objects.count(), before["courses"])
