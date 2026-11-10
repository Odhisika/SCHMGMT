from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import ActivityLog, House, NewsAndEvents, Term, TermWeek
from school.models import School


class NewsAndEventsManagerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Search Academy")
        self.news = NewsAndEvents.objects.create(
            title="Sports Day",
            summary="Annual inter-house sports competition",
            posted_as="News",
            school=self.school,
        )
        self.event = NewsAndEvents.objects.create(
            title="Parents Meeting",
            summary="Termly PTA meeting",
            posted_as="Event",
            school=self.school,
        )

    def test_search_matches_title_summary_and_type(self):
        self.assertEqual(list(NewsAndEvents.objects.search("Sports Day")), [self.news])
        self.assertEqual(
            list(NewsAndEvents.objects.search("inter-house")), [self.news]
        )
        self.assertEqual(list(NewsAndEvents.objects.search("Event")), [self.event])

    def test_search_is_distinct_and_case_insensitive(self):
        self.assertEqual(
            list(NewsAndEvents.objects.search("parents meeting")), [self.event]
        )

    def test_get_by_id_returns_matching_object_or_none(self):
        self.assertEqual(NewsAndEvents.objects.get_by_id(self.news.pk), self.news)
        self.assertIsNone(NewsAndEvents.objects.get_by_id(999999))

    def test_str_uses_title(self):
        self.assertEqual(str(self.news), "Sports Day")


class TermAndWeekTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Term Academy")
        self.term = Term.objects.create(
            term="First", year="2026", school=self.school, is_current_term=True
        )

    def test_term_string_and_alias(self):
        self.assertEqual(str(self.term), "First - 2026")
        from core.models import Semester

        self.assertIs(Semester, Term)

    def test_term_weeks_are_ordered_by_week_number(self):
        TermWeek.objects.create(term=self.term, week_number=2)
        TermWeek.objects.create(term=self.term, week_number=1)
        self.assertEqual(
            list(self.term.weeks.values_list("week_number", flat=True)), [1, 2]
        )

    def test_term_week_string_mentions_activity(self):
        week = TermWeek.objects.create(
            term=self.term, week_number=7, activity_type="mid_term"
        )
        self.assertIn("Week 7", str(week))
        self.assertIn("Mid-Term", str(week))

    def test_duplicate_term_week_is_rejected(self):
        TermWeek.objects.create(term=self.term, week_number=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TermWeek.objects.create(term=self.term, week_number=1)


class HouseAndActivityLogTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="House Academy")

    def test_house_string_and_unique_constraint(self):
        house = House.objects.create(name="Red House", school=self.school, points=10)
        self.assertEqual(str(house), "Red House")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                House.objects.create(name="Red House", school=self.school)

    def test_activity_log_string_contains_message(self):
        log = ActivityLog.objects.create(message="Something happened")
        self.assertIn("Something happened", str(log))
