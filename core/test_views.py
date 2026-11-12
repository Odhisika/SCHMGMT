from datetime import timedelta

from django.db.models import Q
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import NewsAndEvents, Term, TermWeek
from core.testing import DemoDataTestCase
from school.models import School


class HomeViewTests(DemoDataTestCase):
    def assert_post_titles(self, response, expected):
        titles = {item.title for item in response.context["items"]}
        self.assertEqual(titles, set(expected))

    def test_school_admin_sees_every_post(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assert_post_titles(
            response,
            [
                "Welcome Back to School",
                "PTA General Meeting",
                "Examination Timetable Released",
            ],
        )

    def test_primary_student_only_sees_global_student_posts(self):
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assert_post_titles(response, ["Welcome Back to School"])

    def test_parent_sees_parent_posts(self):
        self.client.force_login(self.parent_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assert_post_titles(
            response, ["Welcome Back to School", "PTA General Meeting"]
        )

    def test_primary_teacher_sees_global_posts_only(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assert_post_titles(response, ["Welcome Back to School"])

    def test_sidebar_exposes_score_entry_to_admins_and_teachers(self):
        for user in (self.admin, self.teacher):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("home"))
                self.assertContains(response, reverse("manage_scores"))

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, reverse("manage_scores"))

    def test_sidebar_exposes_quiz_tools_to_admins_and_teachers(self):
        for user in (self.admin, self.teacher):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("home"))
                self.assertContains(response, reverse("teacher_quiz_report"))
                self.assertContains(response, reverse("quiz_marking"))

    def test_current_term_and_weeks_are_exposed_to_the_template(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.context["current_term"], self.current_term)
        self.assertEqual(response.context["term_weeks"].count(), 14)
        self.assertIsNotNone(response.context["current_week"])


class PostDetailTests(DemoDataTestCase):
    def test_detail_page_shows_the_full_announcement(self):
        long_summary = "Detailed announcement. " * 40 + "FINAL SENTENCE."
        post = NewsAndEvents.objects.create(
            title="Long Notice",
            summary=long_summary,
            posted_as="News",
            school=self.school,
            target_role="ALL",
        )
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("post_detail", args=[post.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["post"], post)
        self.assertContains(response, "FINAL SENTENCE.")
        self.assertContains(response, "Long Notice")

    def test_student_cannot_open_a_post_targeted_elsewhere(self):
        post = NewsAndEvents.objects.create(
            title="Parents Only",
            summary="This is for parents.",
            posted_as="News",
            school=self.school,
            target_role="PARENTS",
        )
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("post_detail", args=[post.pk]))

        self.assertEqual(response.status_code, 404)

    def test_school_admin_can_open_every_post_detail(self):
        post = NewsAndEvents.objects.create(
            title="Parents Only",
            summary="This is for parents.",
            posted_as="News",
            school=self.school,
            target_role="PARENTS",
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("post_detail", args=[post.pk]))

        self.assertEqual(response.status_code, 200)


class DashboardViewTests(DemoDataTestCase):
    def test_school_admin_can_view_the_dashboard(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("dashboard"))

        expected_lecturers = User.objects.filter(
            school=self.school, is_active=True
        ).filter(Q(is_lecturer=True) | Q(is_teacher=True))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["student_count"], 4)
        self.assertEqual(
            response.context["lecturer_count"], expected_lecturers.count()
        )
        self.assertEqual(response.context["males_count"], 2)
        self.assertEqual(response.context["females_count"], 2)

    def test_division_filter_limits_counts(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("dashboard"), {"division": "Primary"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["student_count"], 2)
        self.assertEqual(response.context["lecturer_count"], 2)
        self.assertEqual(response.context["selected_division"], "Primary")

    def test_teacher_is_denied_the_admin_dashboard_without_a_redirect_loop(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 302)
        # The dashboard is itself admin-only; bouncing back to it would loop.
        self.assertEqual(response.url, "/")


class SemesterViewTests(DemoDataTestCase):
    def setUp(self):
        self.client.force_login(self.teacher)

    def test_teacher_can_open_semester_list(self):
        response = self.client.get(reverse("semester_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.current_term, response.context["semesters"])

    def test_adding_a_current_term_unsets_the_previous_one(self):
        response = self.client.post(
            reverse("add_semester"),
            {
                "term": "Second",
                "year": "2027",
                "is_current_term": "True",
                "start_date": "2027-01-05",
                "end_date": "2027-04-05",
                "next_term_begins": "2027-04-26 00:00:00",
                "result_released": "",
            },
        )

        self.assertRedirects(response, reverse("semester_list"))
        new_term = Term.objects.get(year="2027", term="Second")
        self.assertEqual(new_term.school, self.school)
        self.assertTrue(new_term.is_current_term)
        self.current_term.refresh_from_db()
        self.assertFalse(self.current_term.is_current_term)

    def test_editing_a_term_to_not_current_does_not_clear_the_current_term(self):
        other = Term.objects.create(
            school=self.school, term="First", year="2025", is_current_term=False
        )

        response = self.client.post(
            reverse("edit_semester", args=[other.pk]),
            {
                "term": "First",
                "year": "2025",
                "is_current_term": "False",
                "start_date": "2024-09-01",
                "end_date": "2024-12-01",
                "next_term_begins": "2025-01-05 00:00:00",
                "result_released": "",
            },
        )

        self.assertRedirects(response, reverse("semester_list"))
        self.current_term.refresh_from_db()
        self.assertTrue(self.current_term.is_current_term)
        other.refresh_from_db()
        self.assertFalse(other.is_current_term)

    def test_current_semester_cannot_be_deleted(self):
        response = self.client.get(reverse("delete_semester", args=[self.current_term.pk]))

        self.assertRedirects(response, reverse("semester_list"))
        self.assertTrue(Term.objects.filter(pk=self.current_term.pk).exists())

    def test_non_current_semester_can_be_deleted(self):
        old_term = Term.objects.create(
            school=self.school, term="First", year="2020", is_current_term=False
        )

        response = self.client.get(reverse("delete_semester", args=[old_term.pk]))

        self.assertRedirects(response, reverse("semester_list"))
        self.assertFalse(Term.objects.filter(pk=old_term.pk).exists())

    def test_student_cannot_manage_terms(self):
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("semester_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")


class TermWeekViewTests(DemoDataTestCase):
    def setUp(self):
        self.client.force_login(self.teacher)
        self.term = Term.objects.create(
            school=self.school,
            term="First",
            year="2028",
            is_current_term=False,
            start_date=timezone.now().date() - timedelta(days=14),
            end_date=timezone.now().date(),
        )

    def test_list_shows_weeks_for_the_term(self):
        TermWeek.objects.create(term=self.term, week_number=2)
        TermWeek.objects.create(term=self.term, week_number=1)

        response = self.client.get(reverse("term_week_list", args=[self.term.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["weeks"].values_list("week_number", flat=True)),
            [1, 2],
        )

    def test_initialize_generates_weeks_from_term_dates(self):
        response = self.client.get(reverse("term_week_init", args=[self.term.pk]))

        self.assertRedirects(response, reverse("term_week_list", args=[self.term.pk]))
        self.assertEqual(self.term.weeks.count(), 3)
        self.assertTrue(
            all(week.activity_type == "normal_lesson" for week in self.term.weeks.all())
        )

    def test_initialize_is_refused_when_weeks_already_exist(self):
        TermWeek.objects.create(term=self.term, week_number=1)

        response = self.client.get(reverse("term_week_init", args=[self.term.pk]))

        self.assertRedirects(response, reverse("term_week_list", args=[self.term.pk]))
        self.assertEqual(self.term.weeks.count(), 1)

    def test_initialize_requires_term_dates(self):
        undated = Term.objects.create(
            school=self.school, term="Second", year="2028", is_current_term=False
        )

        response = self.client.get(reverse("term_week_init", args=[undated.pk]))

        self.assertRedirects(response, reverse("term_week_list", args=[undated.pk]))
        self.assertEqual(undated.weeks.count(), 0)

    def test_add_edit_and_delete_a_week(self):
        response = self.client.post(
            reverse("term_week_add", args=[self.term.pk]),
            {
                "week_number": 1,
                "activity_type": "normal_lesson",
                "title": "Orientation",
                "description": "Welcome week",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("term_week_list", args=[self.term.pk]))
        week = self.term.weeks.get(week_number=1)
        self.assertEqual(week.title, "Orientation")

        response = self.client.post(
            reverse("term_week_edit", args=[self.term.pk, week.pk]),
            {
                "week_number": 1,
                "activity_type": "sports",
                "title": "Sports Week",
                "description": "",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("term_week_list", args=[self.term.pk]))
        week.refresh_from_db()
        self.assertEqual(week.activity_type, "sports")

        response = self.client.get(
            reverse("term_week_delete", args=[self.term.pk, week.pk])
        )
        self.assertRedirects(response, reverse("term_week_list", args=[self.term.pk]))
        self.assertFalse(TermWeek.objects.filter(pk=week.pk).exists())


class TargetingApiTests(DemoDataTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_filter_students_by_division(self):
        response = self.client.get(
            reverse("get_users_for_targeting"),
            {"division": "Primary", "role": "STUDENTS"},
        )

        self.assertEqual(response.status_code, 200)
        result_ids = {row["id"] for row in response.json()["results"]}
        expected_ids = {
            student.student_id
            for student in self.demo.students[self.demo_levels[0]]
        }
        self.assertEqual(result_ids, expected_ids)

    def test_filter_teachers_by_division(self):
        response = self.client.get(
            reverse("get_users_for_targeting"),
            {"division": "Primary", "role": "TEACHERS"},
        )

        self.assertEqual(response.status_code, 200)
        result_ids = {row["id"] for row in response.json()["results"]}
        expected_ids = {self.teacher.id, self.class_teacher.id}
        self.assertEqual(result_ids, expected_ids)

    def test_search_query_narrows_results(self):
        response = self.client.get(
            reverse("get_users_for_targeting"),
            {"division": "ALL", "role": "ALL", "q": "parent"},
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        parent_count = User.objects.filter(
            school=self.school, is_parent=True
        ).count()
        self.assertEqual(len(results), parent_count)
        self.assertTrue(all("parent" in row["text"].lower() for row in results))


class PostManagementTests(DemoDataTestCase):
    def test_teacher_can_add_a_post_to_their_school(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("add_item"),
            {
                "title": "New Library Books",
                "summary": "The library has new titles.",
                "posted_as": "News",
                "target_role": "ALL",
                "target_division": "",
                "specific_user_ids": "",
            },
        )

        self.assertRedirects(response, reverse("home"))
        post = NewsAndEvents.objects.get(title="New Library Books")
        self.assertEqual(post.school, self.school)

    def test_teacher_can_edit_and_delete_a_post(self):
        self.client.force_login(self.teacher)
        post = NewsAndEvents.objects.filter(school=self.school).first()

        response = self.client.post(
            reverse("edit_post", args=[post.pk]),
            {
                "title": "Updated Title",
                "summary": "Updated summary",
                "posted_as": post.posted_as,
                "target_role": post.target_role,
                "target_division": post.target_division or "",
                "specific_user_ids": "",
            },
        )

        self.assertRedirects(response, reverse("home"))
        post.refresh_from_db()
        self.assertEqual(post.title, "Updated Title")

        response = self.client.get(reverse("delete_post", args=[post.pk]))

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(NewsAndEvents.objects.filter(pk=post.pk).exists())

    def test_student_cannot_edit_or_delete_posts(self):
        self.client.force_login(self.student_user)
        post = NewsAndEvents.objects.filter(school=self.school).first()

        edit_response = self.client.post(
            reverse("edit_post", args=[post.pk]),
            {"title": "Hacked", "posted_as": post.posted_as},
        )
        delete_response = self.client.get(reverse("delete_post", args=[post.pk]))

        for response in (edit_response, delete_response):
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, "/dashboard/")
        post.refresh_from_db()
        self.assertEqual(post.title, "Welcome Back to School")


class UniqueMessagesFilterTests(TestCase):
    class Message:
        def __init__(self, level, text):
            self.level = level
            self.text = text

        def __str__(self):
            return self.text

    def test_duplicate_messages_are_collapsed_in_order(self):
        from core.templatetags.custom_filters import unique_messages

        messages = [
            self.Message(40, "Access denied."),
            self.Message(40, "Access denied."),
            self.Message(25, "Scores saved."),
            self.Message(40, "Access denied."),
        ]

        result = unique_messages(messages)

        self.assertEqual([str(message) for message in result], [
            "Access denied.",
            "Scores saved.",
        ])

    def test_same_text_at_different_levels_is_kept(self):
        from core.templatetags.custom_filters import unique_messages

        messages = [
            self.Message(40, "Please review."),
            self.Message(25, "Please review."),
        ]

        self.assertEqual(len(unique_messages(messages)), 2)
