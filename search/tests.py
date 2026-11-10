"""Tests for the global search view."""

from django.urls import reverse

from core.testing import DemoDataTestCase


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
