from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import ListView

from accounts.models import User
from accounts.utils import get_division_for_level
from core.models import NewsAndEvents
from core.search import build_search_query, tokenize_query
from course.models import Course, Program
from quiz.models import Quiz


@dataclass
class SearchResult:
    """A single, template-friendly search result."""

    kind: str
    title: str
    description: str
    url: str
    icon: str
    obj: object | None = None


class SearchView(LoginRequiredMixin, ListView):
    template_name = "search/search_view.html"
    paginate_by = 20

    def get_queryset(self):
        request = self.request
        query = (request.GET.get("q") or "").strip()
        self.results = []
        self.count = 0

        if not query:
            return NewsAndEvents.objects.none()

        school = getattr(request, "school", None)
        self.results = self._collect_results(query, school)
        self.count = len(self.results)

        # Keep ``object_list`` as the matching model instances for backwards
        # compatibility with callers that don't need the richer result data.
        return [result.obj for result in self.results if result.obj is not None]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["count"] = self.count or 0
        context["query"] = (self.request.GET.get("q") or "").strip()
        context["results"] = getattr(self, "results", [])
        return context

    # ------------------------------------------------------------------
    # Result builders
    # ------------------------------------------------------------------
    def _collect_results(self, query, school):
        results = []
        results.extend(self._people_results(query, school))
        results.extend(self._class_results(query))
        results.extend(self._program_results(query, school))
        results.extend(self._course_results(query, school))
        results.extend(self._quiz_results(query, school))
        results.extend(self._news_results(query, school))
        return results

    def _people_results(self, query, school):
        """Students and staff, visible to administrators only."""
        user = self.request.user
        if not school or not (user.is_superuser or user.is_school_admin):
            return []

        matches = (
            User.objects.filter(school=school, is_active=True)
            .filter(
                build_search_query(
                    query,
                    [
                        "first_name",
                        "last_name",
                        "other_names",
                        "username",
                        "email",
                        "phone",
                        "staff_id",
                        "admission_number",
                        "student__level",
                        "student__program__title",
                        "department__title",
                    ],
                )
            )
            .select_related("student")
            .order_by("first_name", "last_name")[:20]
        )

        results = []
        for member in matches:
            details = [member.username]
            student = getattr(member, "student", None)
            if student and student.level:
                details.append(student.level)
            elif member.division:
                details.append(member.division)
            if member.email:
                details.append(member.email)

            results.append(
                SearchResult(
                    kind=member.get_user_role,
                    title=member.get_full_name,
                    description=" · ".join(details),
                    url=reverse("profile_single", kwargs={"user_id": member.pk}),
                    icon="fa-user",
                    obj=member,
                )
            )
        return results

    def _class_results(self, query):
        """Class/level shortcuts for teachers and administrators."""
        user = self.request.user
        if not (
            user.is_superuser
            or user.is_school_admin
            or user.is_teacher
            or user.is_lecturer
        ):
            return []

        needle_tokens = [token.lower() for token in tokenize_query(query)]
        if not needle_tokens:
            return []

        division_labels = dict(settings.DIVISION_CHOICES)
        results = []
        for level_code, level_label in settings.LEVEL_CHOICES:
            if not user.can_access_level(level_code):
                continue
            division = get_division_for_level(level_code) or ""
            division_label = division_labels.get(division, "")
            haystack = " ".join(
                [str(level_code), str(level_label), str(division), str(division_label)]
            ).lower()
            if not all(token in haystack for token in needle_tokens):
                continue
            results.append(
                SearchResult(
                    kind=_("Class"),
                    title=str(level_label),
                    description=division_label or _("Class workspace"),
                    url=reverse("class_detail", kwargs={"level_code": level_code}),
                    icon="fa-chalkboard",
                )
            )
        return results

    def _program_results(self, query, school):
        programs = Program.objects.filter(
            build_search_query(query, ["title", "summary", "division"])
        )
        if school:
            programs = programs.filter(school=school)
        return [
            SearchResult(
                kind=_("Program"),
                title=program.title,
                description=program.summary or _("Academic programme"),
                url=program.get_absolute_url(),
                icon="fa-layer-group",
                obj=program,
            )
            for program in programs[:10]
        ]

    def _course_results(self, query, school):
        courses = Course.objects.filter(
            build_search_query(
                query,
                [
                    "title",
                    "summary",
                    "code",
                    "slug",
                    "program__title",
                    "level",
                    "term",
                ],
            )
        ).select_related("program")
        if school:
            courses = courses.filter(school=school)
        return [
            SearchResult(
                kind=_("Subject"),
                title=str(course),
                description=course.summary
                or _("%(program)s · %(level)s")
                % {"program": course.program, "level": course.level},
                url=course.get_absolute_url(),
                icon="fa-book",
                obj=course,
            )
            for course in courses[:10]
        ]

    def _quiz_results(self, query, school):
        quizzes = Quiz.objects.filter(
            build_search_query(
                query,
                [
                    "title",
                    "description",
                    "category",
                    "slug",
                    "course__title",
                    "course__level",
                    "course__program__title",
                ],
            )
        ).select_related("course")
        if school:
            quizzes = quizzes.filter(course__school=school)
        return [
            SearchResult(
                kind=_("Quiz"),
                title=quiz.title,
                description=quiz.description
                or _("%(course)s quiz") % {"course": quiz.course},
                url=quiz.get_absolute_url(),
                icon="fa-circle-question",
                obj=quiz,
            )
            for quiz in quizzes[:10]
        ]

    def _news_results(self, query, school):
        items = NewsAndEvents.objects.filter(
            build_search_query(query, ["title", "summary", "posted_as"])
        )
        if school:
            items = items.filter(school=school)
        results = []
        for item in items[:10]:
            results.append(
                SearchResult(
                    kind=item.get_posted_as_display(),
                    title=item.title,
                    description=item.summary or _("School announcement"),
                    url=reverse("post_detail", kwargs={"pk": item.pk}),
                    icon="fa-newspaper"
                    if item.posted_as == "News"
                    else "fa-calendar-day",
                    obj=item,
                )
            )
        return results
