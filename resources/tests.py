"""Tests for learning-resource files, videos and access control."""

from django.urls import reverse

from core.models import ActivityLog
from core.testing import DemoDataTestCase
from course.models import Course
from resources.models import CourseFile, CourseVideo


class ResourceModelTests(DemoDataTestCase):
    def setUp(self):
        self.course_file = CourseFile.objects.get(course=self.primary_course)
        self.course_video = CourseVideo.objects.get(course=self.primary_course)

    def test_file_extension_short_names(self):
        self.assertEqual(self.course_file.get_extension_short(), "pdf")

        self.course_file.file = "course_resources/files/demo/handout.docx"
        self.assertEqual(self.course_file.get_extension_short(), "word")

    def test_file_download_url(self):
        self.assertEqual(
            self.course_file.get_absolute_url(),
            reverse(
                "resources:file_download",
                kwargs={
                    "course_slug": self.primary_course.slug,
                    "file_id": self.course_file.pk,
                },
            ),
        )

    def test_video_slug_and_url(self):
        self.assertTrue(self.course_video.slug)
        self.assertEqual(
            self.course_video.get_absolute_url(),
            reverse(
                "resources:video_detail",
                kwargs={
                    "course_slug": self.primary_course.slug,
                    "video_slug": self.course_video.slug,
                },
            ),
        )

    def test_video_view_counter_increments(self):
        starting_views = self.course_video.views

        self.course_video.increment_views()
        self.course_video.refresh_from_db()

        self.assertEqual(self.course_video.views, starting_views + 1)

    def test_upload_and_delete_are_logged(self):
        before = ActivityLog.objects.count()
        file = CourseFile.objects.create(
            title="Logged File",
            course=self.primary_course,
            file="course_resources/files/demo/logged.pdf",
            school=self.school,
            uploaded_by=self.teacher,
        )
        self.assertGreater(ActivityLog.objects.count(), before)

        before_delete = ActivityLog.objects.count()
        file.delete()
        self.assertGreater(ActivityLog.objects.count(), before_delete)


class ResourceViewTests(DemoDataTestCase):
    def test_overview_renders_for_each_role(self):
        for user in (self.admin, self.teacher, self.student_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("resources:overview"))
                self.assertEqual(response.status_code, 200)

    def test_resource_list_renders_for_enrolled_student(self):
        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse(
                "resources:resource_list",
                kwargs={"course_slug": self.primary_course.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["course"], self.primary_course)
        self.assertIn(
            self.primary_course,
            [item.course for item in response.context["files"]],
        )

    def test_student_cannot_open_resources_for_unenrolled_course(self):
        elective = Course.objects.create(
            title="Unrelated Elective",
            code="ELECTIVE-1",
            program=self.demo.programs["Primary"],
            level="Primary 2",
            term=self.current_term.term,
            is_core_subject=False,
            is_elective=True,
            school=self.school,
        )
        self.client.force_login(self.student_user)

        response = self.client.get(
            reverse(
                "resources:resource_list",
                kwargs={"course_slug": elective.slug},
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_video_detail_increments_views(self):
        video = CourseVideo.objects.get(course=self.primary_course)
        starting_views = video.views
        self.client.force_login(self.student_user)

        response = self.client.get(
            reverse(
                "resources:video_detail",
                kwargs={
                    "course_slug": self.primary_course.slug,
                    "video_slug": video.slug,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        video.refresh_from_db()
        self.assertEqual(video.views, starting_views + 1)
