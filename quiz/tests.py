"""Tests for quiz configuration, sitting/attempt behaviour and grading."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.urls import reverse
from django.utils.timezone import now

from core.testing import DemoDataTestCase
from quiz.models import (
    Assignment,
    AssignmentSubmission,
    Choice,
    EssayQuestion,
    FillInTheBlankQuestion,
    MCQuestion,
    Quiz,
    Sitting,
    TrueFalseQuestion,
)


class QuizModelTests(DemoDataTestCase):
    def setUp(self):
        self.quiz = self.demo.quizzes[0]
        self.course = self.quiz.course

    def test_slug_url_and_max_score(self):
        self.assertTrue(self.quiz.slug)
        self.assertEqual(self.quiz.get_max_score, 5)
        self.assertEqual(
            self.quiz.get_absolute_url(),
            reverse("quiz_index", kwargs={"slug": self.course.slug}),
        )

    def test_multiple_attempts_are_detected(self):
        self.assertTrue(self.quiz.allows_multiple_attempts())
        self.assertFalse(self.quiz.single_attempt)

    def test_single_attempt_enforces_exam_paper_and_one_try(self):
        self.quiz.single_attempt = True
        self.quiz.max_attempts = 5
        self.quiz.save()

        self.assertTrue(self.quiz.exam_paper)
        self.assertEqual(self.quiz.max_attempts, 1)
        self.assertFalse(self.quiz.allows_multiple_attempts())

    def test_invalid_pass_mark_is_rejected(self):
        quiz = Quiz(
            course=self.course,
            title="Invalid Quiz",
            pass_mark=101,
        )

        with self.assertRaises(ValidationError):
            quiz.save()

    def test_availability_window(self):
        self.assertTrue(self.quiz.is_available())

        self.quiz.available_from = now() + timedelta(days=1)
        self.quiz.save()
        self.assertFalse(self.quiz.is_available())
        self.assertIsNotNone(self.quiz.time_until_available())

        self.quiz.available_from = now() - timedelta(days=2)
        self.quiz.available_until = now() - timedelta(days=1)
        self.quiz.save()
        self.assertFalse(self.quiz.is_available())
        self.assertTrue(self.quiz.is_expired())
        self.assertIsNone(self.quiz.time_until_expires())

    def test_search_matches_title_and_description(self):
        self.assertIn(self.quiz, Quiz.objects.search(self.quiz.title))
        self.assertIn(self.quiz, Quiz.objects.search("Auto-seeded quiz"))

    def test_best_score_returns_highest_completed_sitting(self):
        low = Sitting.objects.new_sitting(self.student_user, self.quiz, self.course)
        low.add_to_score(2)
        low.mark_quiz_complete()
        high = Sitting.objects.new_sitting(self.student_user, self.quiz, self.course)
        high.add_to_score(4)
        high.mark_quiz_complete()

        self.assertEqual(
            self.quiz.get_best_score_for_user(self.student_user).pk, high.pk
        )


class SittingTests(DemoDataTestCase):
    def setUp(self):
        self.quiz = self.demo.quizzes[0]
        self.course = self.quiz.course
        self.sitting = Sitting.objects.new_sitting(
            self.student_user, self.quiz, self.course
        )

    def test_new_sitting_initialises_question_order_and_timer(self):
        self.assertEqual(self.sitting.attempt_number, 1)
        self.assertEqual(self.sitting.get_max_score, 5)
        self.assertEqual(len(self.sitting._question_ids()), 5)
        self.assertFalse(self.sitting.complete)
        self.assertEqual(self.sitting.time_remaining_seconds, 20 * 60)
        self.assertLessEqual(self.sitting.get_time_remaining(), 1200)
        self.assertGreater(self.sitting.get_time_remaining(), 1100)

    def test_scoring_percentage_and_pass_message(self):
        self.sitting.add_to_score(3)
        self.sitting.refresh_from_db()

        self.assertEqual(self.sitting.get_current_score, 3)
        self.assertEqual(self.sitting.get_percent_correct, 60)
        self.assertTrue(self.sitting.check_if_passed)
        self.assertIn("passed", str(self.sitting.result_message))

    def test_failing_score_message(self):
        self.sitting.add_to_score(1)
        self.sitting.refresh_from_db()

        self.assertEqual(self.sitting.get_percent_correct, 20)
        self.assertFalse(self.sitting.check_if_passed)
        self.assertIn("failed", str(self.sitting.result_message))

    def test_user_sitting_reuses_open_attempt_and_honours_max_attempts(self):
        first = Sitting.objects.user_sitting(
            self.student_user, self.quiz, self.course
        )
        self.assertEqual(first.pk, self.sitting.pk)
        self.assertEqual(
            Sitting.objects.user_sitting(
                self.student_user, self.quiz, self.course
            ).pk,
            self.sitting.pk,
        )

        first.mark_quiz_complete()
        second = Sitting.objects.user_sitting(
            self.student_user, self.quiz, self.course
        )
        self.assertNotEqual(second.pk, first.pk)
        self.assertEqual(second.attempt_number, 2)

        second.mark_quiz_complete()
        self.assertFalse(
            Sitting.objects.user_sitting(self.student_user, self.quiz, self.course)
        )

    def test_user_answers_and_progress(self):
        question = self.sitting.get_first_question()
        choice = question.get_choices().first()

        self.sitting.add_user_answer(question, str(choice.id))
        self.sitting.refresh_from_db()

        self.assertEqual(self.sitting.get_answered_questions(), [question.id])
        self.assertEqual(self.sitting.progress(), (1, 5))
        self.assertEqual(
            self.sitting.get_question_by_position(0).pk, question.pk
        )
        self.assertEqual(
            self.sitting.questions_with_user_answers[question], str(choice.id)
        )

    def test_remove_first_question_advances_the_queue(self):
        first_id = self.sitting.get_first_question().pk
        self.sitting.remove_first_question()
        self.sitting.refresh_from_db()

        self.assertNotEqual(self.sitting.get_first_question().pk, first_id)
        self.assertTrue(self.sitting.has_next_question())

    def test_incorrect_questions_can_be_added_and_removed(self):
        question = self.sitting.get_first_question()

        self.sitting.add_incorrect_question(question)
        self.assertIn(question.id, self.sitting.get_incorrect_questions)

        # Removing before completion also adjusts the score.
        self.sitting.remove_incorrect_question(question)
        self.assertNotIn(question.id, self.sitting.get_incorrect_questions)

    def test_empty_quiz_cannot_start_a_sitting(self):
        empty_quiz = Quiz.objects.create(
            course=self.course, title="Empty Quiz", pass_mark=50
        )

        with self.assertRaises(ImproperlyConfigured):
            Sitting.objects.new_sitting(self.student_user, empty_quiz, self.course)


class QuestionTypeTests(DemoDataTestCase):
    def test_multiple_choice_grading(self):
        question = MCQuestion.objects.create(content="2 + 2 = ?", choice_order="content")
        correct = Choice.objects.create(
            question=question, choice_text="4", correct=True
        )
        wrong = Choice.objects.create(
            question=question, choice_text="5", correct=False
        )

        self.assertTrue(question.check_if_correct(str(correct.id)))
        self.assertFalse(question.check_if_correct(str(wrong.id)))
        self.assertFalse(question.check_if_correct("not-a-number"))
        self.assertEqual(question.answer_choice_to_string(correct.id), "4")
        self.assertEqual(len(question.get_choices_list()), 2)

    def test_true_false_grading(self):
        question = TrueFalseQuestion.objects.create(
            content="The sky is blue.", correct_answer=True
        )

        self.assertTrue(question.check_if_correct("1"))
        self.assertFalse(question.check_if_correct("0"))
        self.assertFalse(question.check_if_correct("invalid"))
        self.assertEqual(question.answer_choice_to_string("1"), "True")
        self.assertEqual(len(question.get_choices()), 2)

    def test_fill_in_the_blank_grading(self):
        question = FillInTheBlankQuestion.objects.create(
            content="Capital of Ghana: ____", correct_answer="Accra"
        )

        self.assertTrue(question.check_if_correct("  accra "))
        self.assertFalse(question.check_if_correct(""))
        self.assertEqual(question.get_answers(), "Accra")

        question.case_sensitive = True
        question.save()
        self.assertFalse(question.check_if_correct("accra"))
        self.assertTrue(question.check_if_correct("Accra"))

    def test_essay_questions_require_manual_grading(self):
        question = EssayQuestion.objects.create(content="Discuss photosynthesis.")

        self.assertFalse(question.check_if_correct("anything"))
        self.assertFalse(question.get_answers())


class AssignmentTests(DemoDataTestCase):
    def setUp(self):
        self.assignment = Assignment.objects.get(quiz=self.demo.quizzes[0])
        self.course = self.demo.quizzes[0].course

    def test_due_date_checks(self):
        self.assertFalse(self.assignment.is_overdue())

        self.assignment.due_date = now() - timedelta(days=1)
        self.assignment.save()
        self.assertTrue(self.assignment.is_overdue())

    def test_submission_late_and_graded_flags(self):
        self.assignment.due_date = now() - timedelta(days=1)
        self.assignment.save()
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student_user,
            submitted_file="assignment_submissions/demo.pdf",
            submission_text="My work",
        )

        self.assertTrue(submission.is_late())
        self.assertFalse(submission.is_graded())

        submission.grade = Decimal("88.00")
        submission.save()
        self.assertTrue(submission.is_graded())

    def test_on_time_submission_is_not_late(self):
        self.assignment.due_date = now() + timedelta(days=1)
        self.assignment.save()
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student_user,
            submitted_file="assignment_submissions/demo.pdf",
        )

        self.assertFalse(submission.is_late())


class QuizViewTests(DemoDataTestCase):
    def test_quiz_list_renders_for_enrolled_student_and_teacher(self):
        url = reverse("quiz_index", kwargs={"slug": self.primary_course.slug})

        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_quiz_progress_page_renders(self):
        self.client.force_login(self.student_user)
        self.assertEqual(
            self.client.get(reverse("quiz_progress")).status_code, 200
        )

    def test_student_outside_allocation_cannot_open_quiz_list(self):
        self.client.force_login(self.student_user)
        url = reverse("quiz_index", kwargs={"slug": self.jhs_course.slug})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_question_workspace_is_available_to_teachers_and_admins(self):
        quiz = self.demo.quizzes[0]
        url = reverse(
            "quiz_questions",
            kwargs={"slug": quiz.course.slug, "quiz_id": quiz.pk},
        )

        for user in (self.teacher, self.admin, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["quiz"], quiz)

    def test_teacher_can_add_true_false_and_fill_blank_questions(self):
        quiz = self.demo.quizzes[0]
        self.client.force_login(self.teacher)

        tf_response = self.client.post(
            reverse(
                "question_create",
                kwargs={
                    "slug": quiz.course.slug,
                    "quiz_id": quiz.pk,
                    "qtype": "truefalse",
                },
            ),
            {
                "content": "The sky is blue.",
                "explanation": "",
                "correct_answer": "on",
            },
        )
        self.assertRedirects(
            tf_response,
            reverse(
                "quiz_questions",
                kwargs={"slug": quiz.course.slug, "quiz_id": quiz.pk},
            ),
        )

        fill_response = self.client.post(
            reverse(
                "question_create",
                kwargs={
                    "slug": quiz.course.slug,
                    "quiz_id": quiz.pk,
                    "qtype": "fillblank",
                },
            ),
            {
                "content": "Capital of Ghana: ____",
                "explanation": "",
                "correct_answer": "Accra",
            },
        )
        self.assertRedirects(
            fill_response,
            reverse(
                "quiz_questions",
                kwargs={"slug": quiz.course.slug, "quiz_id": quiz.pk},
            ),
        )

        self.assertTrue(
            TrueFalseQuestion.objects.filter(
                content="The sky is blue.", quiz=quiz
            ).exists()
        )
        self.assertTrue(
            FillInTheBlankQuestion.objects.filter(
                content="Capital of Ghana: ____", quiz=quiz
            ).exists()
        )

    def test_teacher_can_delete_a_question_from_a_quiz(self):
        quiz = self.demo.quizzes[0]
        question = TrueFalseQuestion.objects.create(
            content="Temporary question", correct_answer=True
        )
        question.quiz.add(quiz)
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse(
                "question_delete",
                kwargs={
                    "slug": quiz.course.slug,
                    "quiz_id": quiz.pk,
                    "pk": question.pk,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "quiz_questions",
                kwargs={"slug": quiz.course.slug, "quiz_id": quiz.pk},
            ),
        )
        self.assertFalse(TrueFalseQuestion.objects.filter(pk=question.pk).exists())

    def test_teacher_outside_division_cannot_manage_questions(self):
        quiz = self.demo.quizzes[1]
        self.client.force_login(self.teacher)

        response = self.client.get(
            reverse(
                "quiz_questions",
                kwargs={"slug": quiz.course.slug, "quiz_id": quiz.pk},
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_school_admin_can_open_the_marking_list(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("quiz_marking"))

        self.assertEqual(response.status_code, 200)
