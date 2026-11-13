"""Model tests for multi-tenant school configuration."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from school.models import GradeWeightConfig, PromotionPolicy, School, StudentIDSequence
from accounts.utils import generate_student_id


class SchoolModelTests(TestCase):
    def test_slug_and_subdomain_are_generated_from_name(self):
        school = School.objects.create(name="Testville Academy")

        self.assertEqual(school.slug, "testville-academy")
        self.assertEqual(school.subdomain, "testville-academy")

    def test_unique_identifier_avoids_collisions(self):
        first = School.objects.create(name="Collision School")
        second = School.objects.create(name="Another School")

        generated = second._generate_unique_identifier("Collision School", "slug")

        self.assertEqual(first.slug, "collision-school")
        self.assertEqual(generated, "collision-school-2")

    def test_user_count_helpers_only_count_active_school_users(self):
        school = School.objects.create(name="Counted School")
        User.objects.create_user(
            username="counted_admin",
            password="password",
            school=school,
            is_school_admin=True,
        )
        User.objects.create_user(
            username="counted_teacher",
            password="password",
            school=school,
            is_lecturer=True,
        )
        User.objects.create_user(
            username="counted_student",
            password="password",
            school=school,
            is_student=True,
        )
        User.objects.create_user(
            username="inactive_student",
            password="password",
            school=school,
            is_student=True,
            is_active=False,
        )

        self.assertEqual(school.get_active_users_count(), 3)
        self.assertEqual(school.get_student_count(), 1)
        self.assertEqual(school.get_teacher_count(), 1)
        self.assertEqual(school.get_admin_count(), 1)


class StudentIDSequenceTests(TestCase):
    def test_each_school_division_starts_at_one_and_increments_independently(self):
        first_school = School.objects.create(name="First ID School")
        second_school = School.objects.create(name="Second ID School")
        year = timezone.localdate().year

        self.assertEqual(
            generate_student_id(first_school, "Primary"),
            f"S{first_school.pk}-PRI-{year}-0001",
        )
        self.assertEqual(
            generate_student_id(first_school, "Primary"),
            f"S{first_school.pk}-PRI-{year}-0002",
        )
        self.assertEqual(
            generate_student_id(first_school, "JHS"),
            f"S{first_school.pk}-JHS-{year}-0001",
        )
        self.assertEqual(
            generate_student_id(second_school, "Primary"),
            f"S{second_school.pk}-PRI-{year}-0001",
        )
        self.assertEqual(StudentIDSequence.objects.count(), 3)

    def test_school_can_choose_prefix_and_id_pattern(self):
        school = School.objects.create(
            name="Custom ID School",
            student_id_primary_prefix="PUPIL",
            student_id_primary_pattern="DIVISION_SEQUENCE",
        )

        self.assertEqual(generate_student_id(school, "Primary"), "PUPIL-0001")


class GradeWeightConfigTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Weighted School")
        self.config = GradeWeightConfig.objects.create(
            school=self.school,
            use_classwork=True,
            use_class_test=True,
            use_assignment=True,
            use_attendance=True,
            use_project=False,
            classwork_weight=10,
            class_test_weight=15,
            assignment_weight=15,
            attendance_weight=10,
            project_weight=0,
            exam_weight=50,
        )

    def test_active_weight_total_and_validity(self):
        self.assertEqual(self.config.get_active_weights_total(), 100)
        self.assertTrue(self.config.is_valid_config())

        self.config.use_project = True
        self.config.project_weight = 5
        self.assertEqual(self.config.get_active_weights_total(), 105)
        self.assertFalse(self.config.is_valid_config())

    def test_disabled_components_do_not_contribute(self):
        self.config.use_attendance = False
        self.assertEqual(self.config.get_active_weights_total(), 90)

    def test_calculate_total_scales_each_component(self):
        total = self.config.calculate_total(
            classwork=80,
            class_test=70,
            assignment=60,
            attendance=90,
            project=100,
            exam=50,
        )

        # 8 + 10.5 + 9 + 9 + 0 + 25
        self.assertEqual(total, 61.5)

    def test_inactive_project_is_ignored_in_calculation(self):
        self.assertEqual(
            self.config.calculate_total(project=100, exam=0),
            0.0,
        )

    def test_normalize_score_converts_raw_marks_to_percentage(self):
        cases = [
            ("10", 10, Decimal("100.00")),
            ("5", 10, Decimal("50.00")),
            ("15", 20, Decimal("75.00")),
            ("25", 50, Decimal("50.00")),
            ("0", 10, Decimal("0.00")),
            ("10", 0, Decimal("0.00")),
        ]
        for raw, maximum, expected in cases:
            with self.subTest(raw=raw, maximum=maximum):
                self.assertEqual(
                    GradeWeightConfig.normalize_score(raw, maximum), expected
                )


class PromotionPolicyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Promoting School")
        self.policy = PromotionPolicy.objects.create(
            school=self.school,
            promotion_cut_off=Decimal("50.00"),
            failure_cut_off=Decimal("40.00"),
        )

    def test_evaluate_returns_correct_status(self):
        cases = {
            Decimal("75.00"): "AUTO_PASS",
            Decimal("50.00"): "AUTO_PASS",
            Decimal("45.00"): "BORDERLINE",
            Decimal("40.00"): "BORDERLINE",
            Decimal("39.99"): "AUTO_FAIL",
        }
        for score, expected in cases.items():
            with self.subTest(score=score):
                self.assertEqual(self.policy.evaluate(score), expected)

    def test_evaluate_accepts_float_and_string_scores(self):
        self.assertEqual(self.policy.evaluate(55.0), "AUTO_PASS")
        self.assertEqual(self.policy.evaluate("30.0"), "AUTO_FAIL")
