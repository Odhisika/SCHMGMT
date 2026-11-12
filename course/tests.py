"""Tests for the course app: programs, courses and lesson notes."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import ActivityLog
from core.testing import DemoDataTestCase
from course.models import (
    Course,
    CourseAllocation,
    LessonNote,
    Program,
    SubjectTemplate,
    Upload,
    UploadVideo,
)


class ProgramAndCourseModelTests(DemoDataTestCase):
    def test_program_search_matches_title_and_summary(self):
        title_match = Program.objects.search("Primary Section")
        summary_match = Program.objects.search("academic division")

        self.assertIn(self.demo.programs["Primary"], title_match)
        self.assertTrue(summary_match.exists())

    def test_program_get_absolute_url(self):
        program = self.demo.programs["Primary"]
        self.assertEqual(
            program.get_absolute_url(),
            reverse("program_detail", kwargs={"pk": program.pk}),
        )

    def test_course_search_matches_title_code_and_slug(self):
        course = self.primary_course

        for term in (course.title, course.code, course.slug):
            with self.subTest(term=term):
                self.assertIn(course, Course.objects.search(term))

    def test_course_slug_is_generated_and_stable(self):
        course = self.primary_course
        self.assertTrue(course.slug)
        original_slug = course.slug
        course.summary = "Updated summary"
        course.save()
        self.assertEqual(course.slug, original_slug)

    def test_course_current_term_flags(self):
        self.assertTrue(self.primary_course.is_current_term)
        self.assertTrue(self.primary_course.is_current_semester)

        other_term = self.demo.terms["First"]
        course = Course.objects.create(
            title="Old Subject",
            code="OLD-1",
            program=self.demo.programs["Primary"],
            level="Primary 1",
            term=other_term.term,
            school=self.school,
        )
        self.assertFalse(course.is_current_term)
        self.assertEqual(course.semester, other_term.term)

    def test_course_save_and_delete_are_logged(self):
        before = ActivityLog.objects.count()
        course = Course.objects.create(
            title="Activity Logged Course",
            code="LOG-1",
            program=self.demo.programs["Primary"],
            level="Primary 1",
            term=self.current_term.term,
            school=self.school,
        )
        self.assertGreater(ActivityLog.objects.count(), before)

        before_delete = ActivityLog.objects.count()
        course.delete()
        self.assertGreater(ActivityLog.objects.count(), before_delete)

    def test_subject_template_create_course(self):
        template = SubjectTemplate.objects.create(
            title="Creative Arts",
            code_prefix="ART",
            level="Primary 1",
            division="Primary",
            school=self.school,
        )

        course = template.create_course(
            self.demo.programs["Primary"], self.current_term.term
        )

        self.assertEqual(course.code, "ARTPRI")
        self.assertEqual(course.title, "Creative Arts")
        self.assertEqual(course.school, self.school)
        self.assertTrue(course.is_core_subject)

    def test_course_allocation_legacy_lecturer_property(self):
        allocation = CourseAllocation.objects.filter(teacher=self.teacher).first()
        self.assertIsNotNone(allocation)
        self.assertEqual(allocation.lecturer, self.teacher)
        self.assertIn(self.primary_course, allocation.courses.all())


class CourseResourceModelTests(DemoDataTestCase):
    def test_upload_extension_short_names(self):
        mappings = {
            "notes.docx": "word",
            "notes.pdf": "pdf",
            "marks.xlsx": "excel",
            "slides.pptx": "powerpoint",
            "archive.zip": "archive",
            "data.txt": "file",
        }
        for filename, expected in mappings.items():
            with self.subTest(filename=filename):
                upload = Upload(title="Resource", course=self.primary_course, file=filename)
                self.assertEqual(upload.get_extension_short(), expected)

    def test_upload_video_slug_and_url(self):
        video = UploadVideo.objects.create(
            title="Fractions Lesson",
            course=self.primary_course,
            video="course_videos/fractions.mp4",
        )

        self.assertTrue(video.slug)
        self.assertEqual(
            video.get_absolute_url(),
            reverse(
                "video_single",
                kwargs={"slug": self.primary_course.slug, "video_slug": video.slug},
            ),
        )


class LessonNoteModelTests(DemoDataTestCase):
    def test_draft_lesson_note_can_be_edited_and_submitted(self):
        note = LessonNote.objects.get(teacher=self.class_teacher, week_number=2)

        self.assertEqual(note.status, "DRAFT")
        self.assertTrue(note.can_edit())
        self.assertTrue(note.can_submit())
        self.assertEqual(note.get_status_display_class(), "secondary")

    def test_submitted_lesson_note_is_read_only(self):
        note = LessonNote.objects.get(teacher=self.class_teacher, week_number=1)

        self.assertEqual(note.status, "SUBMITTED")
        self.assertFalse(note.can_edit())
        self.assertFalse(note.can_submit())
        self.assertEqual(note.get_status_display_class(), "info")


class CourseViewTests(DemoDataTestCase):
    def test_program_listing_requires_teacher_role(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("programs"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("programs"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_program_detail_is_scoped_to_school(self):
        program = self.demo.programs["Primary"]
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("program_detail", args=[program.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["program"], program)

    def test_course_detail_renders_for_enrolled_student(self):
        self.client.force_login(self.student_user)

        response = self.client.get(
            reverse("course_detail", kwargs={"slug": self.primary_course.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["course"], self.primary_course)

    def test_lesson_note_workflow_submit_and_delete(self):
        self.client.force_login(self.class_teacher)
        draft = LessonNote.objects.get(teacher=self.class_teacher, week_number=2)

        response = self.client.get(reverse("lesson_note_list"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("lesson_note_submit", args=[draft.pk]))
        self.assertRedirects(
            response, reverse("lesson_note_detail", args=[draft.pk])
        )
        draft.refresh_from_db()
        self.assertEqual(draft.status, "SUBMITTED")

        # A submitted note can no longer be deleted.
        response = self.client.post(reverse("lesson_note_delete", args=[draft.pk]))
        self.assertRedirects(
            response, reverse("lesson_note_detail", args=[draft.pk])
        )
        self.assertTrue(LessonNote.objects.filter(pk=draft.pk).exists())

    def test_student_cannot_open_lesson_notes(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("lesson_note_list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")
