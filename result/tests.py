"""Tests for results, grading weights, positions and promotion workflows."""

from decimal import Decimal

from django.urls import reverse

from core.testing import DemoDataTestCase
from result.models import (
    BECEMockExam,
    BECEMockResult,
    PromotionRequest,
    Result,
    ResultEditRequest,
    TakenCourse,
)
from school.models import School


class TakenCourseScoringTests(DemoDataTestCase):
    def setUp(self):
        self.taken = TakenCourse.objects.get(
            student=self.student,
            course=self.primary_course,
            school=self.school,
        )

    def test_weighted_total_uses_school_grade_config(self):
        self.taken.classwork_score = Decimal("80.00")
        self.taken.midsem_score = Decimal("70.00")
        self.taken.assignment_score = Decimal("60.00")
        self.taken.attendance_score = Decimal("90.00")
        self.taken.exam_score = Decimal("50.00")
        self.taken.save()
        self.taken.refresh_from_db()

        # 80*10% + 70*15% + 60*15% + 90*10% + 50*50%
        self.assertEqual(self.taken.total, Decimal("61.50"))
        self.assertEqual(self.taken.class_score, Decimal("36.50"))
        self.assertEqual(self.taken.grade, "5")
        self.assertEqual(self.taken.comment, "Good")

    def test_legacy_fallback_when_school_has_no_grade_config(self):
        legacy_school = School.objects.create(name="Legacy Grading School")
        self.taken.school = legacy_school
        self.taken.midsem_score = Decimal("20.00")
        self.taken.quiz_score = Decimal("10.00")
        self.taken.assignment_score = Decimal("10.00")
        self.taken.exam_score = Decimal("30.00")
        self.taken.save()
        self.taken.refresh_from_db()

        self.assertEqual(self.taken.total, Decimal("70.00"))
        self.assertEqual(self.taken.class_score, Decimal("40.00"))
        self.assertEqual(self.taken.grade, "3")
        self.assertEqual(self.taken.comment, "Very Good")

    def test_get_total_matches_saved_total(self):
        self.assertEqual(self.taken.get_total(), self.taken.total)

    def test_grade_and_comment_boundaries(self):
        cases = [
            ("100", "1", "Excellent"),
            ("80", "1", "Excellent"),
            ("79.99", "2", "Excellent"),
            ("75", "2", "Excellent"),
            ("74.99", "3", "Very Good"),
            ("70", "3", "Very Good"),
            ("69.99", "4", "Very Good"),
            ("65", "4", "Very Good"),
            ("64.99", "5", "Good"),
            ("60", "5", "Good"),
            ("59.99", "6", "Good"),
            ("55", "6", "Good"),
            ("54.99", "7", "Credit"),
            ("50", "7", "Credit"),
            ("49.99", "8", "Pass"),
            ("45", "8", "Pass"),
            ("44.99", "9", "Fail"),
            ("0", "9", "Fail"),
        ]
        probe = TakenCourse()

        for total, grade, comment in cases:
            with self.subTest(total=total):
                probe.total = Decimal(total)
                self.assertEqual(probe.get_grade(), grade)
                probe.grade = grade
                self.assertEqual(probe.get_comment(), comment)

    def test_class_position_is_recalculated_from_total(self):
        results = list(
            TakenCourse.objects.filter(
                course=self.primary_course, school=self.school
            ).order_by("student__student__username")
        )
        low, high = results[0], results[1]

        low.exam_score = Decimal("10.00")
        low.classwork_score = low.midsem_score = low.assignment_score = Decimal("0.00")
        low.attendance_score = Decimal("0.00")
        low.save()
        high.exam_score = Decimal("100.00")
        high.classwork_score = high.midsem_score = high.assignment_score = Decimal("100.00")
        high.attendance_score = Decimal("100.00")
        high.save()

        low.refresh_from_db()
        high.refresh_from_db()

        self.assertEqual(high.class_position, 1)
        self.assertEqual(low.class_position, 2)

    def test_term_average_uses_current_term_courses(self):
        taken_courses = TakenCourse.objects.filter(
            student=self.student, course__term=self.current_term.term
        )
        expected = sum(tc.total for tc in taken_courses) / Decimal(taken_courses.count())

        self.assertEqual(self.taken.calculate_term_average(), round(expected, 2))


class ResultModelTests(DemoDataTestCase):
    def setUp(self):
        self.result = self.demo.results[0]

    def test_promoted_flag_is_derived_from_promotion_status(self):
        self.result.promotion_status = "AUTO_PASS"
        self.result.save()
        self.result.refresh_from_db()
        self.assertTrue(self.result.promoted)

        self.result.promotion_status = "MANUAL_FAIL"
        self.result.save()
        self.result.refresh_from_db()
        self.assertFalse(self.result.promoted)

    def test_attendance_percentage(self):
        self.result.days_present = 8
        self.result.total_attendance_days = 10
        self.assertEqual(self.result.attendance_percentage, 80.0)

        self.result.total_attendance_days = 0
        self.assertEqual(self.result.attendance_percentage, 0.0)

    def test_promotion_status_label_and_colour(self):
        expected = {
            "AUTO_PASS": ("Auto Passed", "success"),
            "MANUAL_PASS": ("Manually Promoted", "success"),
            "AUTO_FAIL": ("Auto Failed", "danger"),
            "MANUAL_FAIL": ("Manually Held Back", "danger"),
            "BORDERLINE": ("Borderline (Needs Review)", "warning"),
            "PENDING": ("Pending Evaluation", "secondary"),
        }
        for status, (label, colour) in expected.items():
            with self.subTest(status=status):
                self.result.promotion_status = status
                self.assertEqual(str(self.result.promotion_status_label), label)
                self.assertEqual(self.result.promotion_status_color, colour)

    def test_auto_evaluate_promotion_uses_school_policy(self):
        self.result.term_average = Decimal("72.00")
        self.result.auto_evaluate_promotion()
        self.result.refresh_from_db()
        self.assertEqual(self.result.promotion_status, "AUTO_PASS")
        self.assertTrue(self.result.promoted)

        self.result.term_average = Decimal("45.00")
        self.result.auto_evaluate_promotion()
        self.result.refresh_from_db()
        self.assertEqual(self.result.promotion_status, "BORDERLINE")
        self.assertFalse(self.result.promoted)

        self.result.term_average = Decimal("30.00")
        self.result.auto_evaluate_promotion()
        self.result.refresh_from_db()
        self.assertEqual(self.result.promotion_status, "AUTO_FAIL")
        self.assertFalse(self.result.promoted)

    def test_auto_evaluate_marks_missing_average_pending(self):
        self.result.term_average = None
        self.result.auto_evaluate_promotion()
        self.result.refresh_from_db()
        self.assertEqual(self.result.promotion_status, "PENDING")

    def test_overall_position_tracks_term_average(self):
        results = list(
            Result.objects.filter(
                term=self.current_term.term,
                session=self.result.session,
                level=self.result.level,
                school=self.school,
            ).order_by("student__student__username")
        )
        low, high = results[0], results[1]

        low.term_average = Decimal("10.00")
        low.save()
        high.term_average = Decimal("90.00")
        high.save()

        low.refresh_from_db()
        high.refresh_from_db()

        self.assertEqual(high.overall_position, 1)
        self.assertEqual(low.overall_position, 2)


class PromotionRequestTests(DemoDataTestCase):
    def test_approve_promotes_the_student_manually(self):
        request = PromotionRequest.objects.get(status="PENDING")

        request.approve(self.admin, notes="Approved after review")
        request.refresh_from_db()
        request.result.refresh_from_db()

        self.assertEqual(request.status, "APPROVED")
        self.assertEqual(request.reviewed_by, self.admin)
        self.assertEqual(request.admin_notes, "Approved after review")
        self.assertEqual(request.result.promotion_status, "MANUAL_PASS")
        self.assertTrue(request.result.promoted)

    def test_reject_leaves_result_unchanged(self):
        result = next(
            result
            for result in self.demo.results
            if not result.promotion_requests.filter(status="PENDING").exists()
        )
        original_status = result.promotion_status
        request = PromotionRequest.objects.create(
            student=result.student,
            result=result,
            request_type="HOLD_BACK",
            requested_by=self.teacher,
            reason="Attendance concerns",
            school=self.school,
        )

        request.reject(self.admin, notes="Insufficient evidence")
        request.refresh_from_db()
        result.refresh_from_db()

        self.assertEqual(request.status, "REJECTED")
        self.assertEqual(result.promotion_status, original_status)


class BECEMockResultTests(DemoDataTestCase):
    def test_grade_is_derived_from_score(self):
        exam = BECEMockExam.objects.create(
            name="First Mock",
            year="2026",
            date_started=self.current_term.start_date,
            date_finished=self.current_term.end_date,
            school=self.school,
        )
        course = self.demo.courses[self.demo_levels[1]][0]
        mock = BECEMockResult.objects.create(
            student=self.demo.students[self.demo_levels[1]][0],
            mock_exam=exam,
            course=course,
            score=Decimal("85.00"),
        )
        self.assertEqual(mock.grade, "1")

        mock.score = Decimal("44.00")
        mock.save()
        mock.refresh_from_db()
        self.assertEqual(mock.grade, "9")

    def test_result_edit_request_string(self):
        result_request = ResultEditRequest.objects.get(school=self.school)
        rendered = str(result_request)

        self.assertIn(str(result_request.course), rendered)
        self.assertIn(str(result_request.status), rendered)


class ResultViewTests(DemoDataTestCase):
    def test_manage_scores_requires_teacher_role(self):
        self.client.force_login(self.teacher)
        self.assertEqual(
            self.client.get(reverse("manage_scores")).status_code, 200
        )

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("manage_scores"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_enter_scores_renders_for_allocated_teacher(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("enter_scores", args=[self.primary_course.level]),
            {"subject": self.primary_course.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["course"], self.primary_course)

    def test_student_can_view_released_results_page(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("grade_results"))
        self.assertEqual(response.status_code, 200)

    def test_result_amendment_requests_render_for_roles(self):
        for user in (self.admin, self.teacher):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("result_amendment_requests"))
                self.assertEqual(response.status_code, 200)

    def test_promotion_page_requires_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("create_promotion")).status_code, 200
        )

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("create_promotion"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")
