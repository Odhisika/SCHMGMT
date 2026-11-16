"""Tests for the global search view."""

from django.urls import reverse

from core.testing import DemoDataTestCase
from course.models import Program
from school.models import School


class SearchViewTests(DemoDataTestCase):
    def test_search_returns_matching_courses_and_programs(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("query"), {"q": self.primary_course.title})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["query"], self.primary_course.title)
        self.assertGreaterEqual(response.context["count"], 1)
        self.assertIn(self.primary_course, response.context["object_list"])

    def test_search_can_match_programs(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("query"), {"q": "Primary Section"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.demo.programs["Primary"], response.context["object_list"])

    def test_search_without_query_is_empty(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("query"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count"], 0)
        self.assertEqual(list(response.context["object_list"]), [])

    def test_search_with_no_matches(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("query"), {"q": "zzzz-no-such-record"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count"], 0)

    def test_search_finds_students_by_name_for_administrators(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("query"), {"q": self.student_user.username}
        )

        self.assertEqual(response.status_code, 200)
        match = next(
            result
            for result in response.context["results"]
            if result.obj == self.student_user
        )
        self.assertEqual(match.kind, "Student")
        self.assertEqual(
            match.url,
            reverse("profile_single", kwargs={"user_id": self.student_user.pk}),
        )

    def test_search_matches_full_person_names(self):
        """A first + last name query must find the person."""
        self.client.force_login(self.admin)

        full_name = f"{self.student_user.first_name} {self.student_user.last_name}"
        response = self.client.get(reverse("query"), {"q": full_name})

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            self.student_user,
            [result.obj for result in response.context["results"]],
        )

    def test_search_matches_reordered_multiple_words(self):
        """Every word should be matched independently, in any order."""
        self.client.force_login(self.admin)

        quiz = self.demo.quizzes[0]
        reordered = " ".join(reversed(quiz.title.split()))
        response = self.client.get(reverse("query"), {"q": reordered})

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            quiz,
            [result.obj for result in response.context["results"]],
        )

    def test_search_finds_classes_by_division(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("query"), {"q": "Primary"})

        self.assertEqual(response.status_code, 200)
        class_titles = [
            result.title
            for result in response.context["results"]
            if result.kind == "Class"
        ]
        self.assertIn(self.demo_levels[0], class_titles)
        self.assertNotIn("JHS 1", class_titles)

    def test_search_results_are_scoped_to_the_current_school(self):
        other_school = School.objects.create(name="Other Search School")
        Program.objects.create(
            title="Out of School Programme", school=other_school
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("query"), {"q": "Out of School Programme"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count"], 0)
        self.assertEqual(list(response.context["object_list"]), [])

    def test_regular_teacher_does_not_see_people_results(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse("query"), {"q": self.student_user.username}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            self.student_user,
            [result.obj for result in response.context["results"]],
        )
