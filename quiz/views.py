from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from accounts.decorators import lecturer_required
from accounts.models import User
from .forms import (
    EssayForm,
    EssayQuestionForm,
    FillInTheBlankForm,
    FillInTheBlankQuestionForm,
    MCQuestionForm,
    MCQuestionFormSet,
    QuestionForm,
    QuizAddForm,
    TrueFalseForm,
    TrueFalseQuestionForm,
)
from .models import (
    Course,
    EssayQuestion,
    TrueFalseQuestion,
    FillInTheBlankQuestion,
    MCQuestion,
    Progress,
    Question,
    Quiz,
    Sitting,
)


# ########################################################
# Quiz Views
# ########################################################


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizCreateView(CreateView):
    model = Quiz
    form_class = QuizAddForm
    template_name = "quiz/quiz_form.html"

    def get_initial(self):
        initial = super().get_initial()
        course = get_object_or_404(Course, slug=self.kwargs["slug"])
        
        # Access check: Ensure teacher can create quizzes for this course
        if not (self.request.user.is_superuser or self.request.user.is_school_admin):
            if not self.request.user.can_access_level(course.level):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("You cannot create quizzes for courses outside your division.")
        
        initial["course"] = course
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = get_object_or_404(Course, slug=self.kwargs["slug"])
        return context

    def form_valid(self, form):
        course = get_object_or_404(Course, slug=self.kwargs["slug"])
        
        # Double-check division access before saving
        if not (self.request.user.is_superuser or self.request.user.is_school_admin):
            if not self.request.user.can_access_level(course.level):
                messages.error(self.request, "You cannot create quizzes for courses outside your division.")
                return redirect('home')
        
        form.instance.course = course
        with transaction.atomic():
            self.object = form.save()
            return redirect(
                "mc_create", slug=self.kwargs["slug"], quiz_id=self.object.id
            )


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizUpdateView(UpdateView):
    model = Quiz
    form_class = QuizAddForm
    template_name = "quiz/quiz_form.html"

    def get_object(self, queryset=None):
        return get_object_or_404(Quiz, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = get_object_or_404(Course, slug=self.kwargs["slug"])
        return context

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save()
            return redirect("quiz_index", self.kwargs["slug"])


@login_required
@lecturer_required
def quiz_delete(request, slug, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    quiz.delete()
    messages.success(request, "Quiz successfully deleted.")
    return redirect("quiz_index", slug=slug)


@login_required
@lecturer_required
def quiz_toggle_draft(request, pk):
    """AJAX endpoint to toggle quiz draft status."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    quiz = get_object_or_404(Quiz, pk=pk)
    was_draft = quiz.draft
    quiz.draft = not quiz.draft
    quiz.save(update_fields=['draft'])

    if was_draft and not quiz.draft:
        from core.notifications import notify
        from result.models import TakenCourse
        student_ids = TakenCourse.objects.filter(
            course=quiz.course, school=quiz.course.school
        ).values_list("student__student_id", flat=True).distinct()
        for student in User.objects.filter(
            pk__in=student_ids, school=quiz.course.school, is_active=True
        ):
            notify(
                school=quiz.course.school,
                recipient=student,
                title=f"New quiz: {quiz.title}",
                message=f"A quiz is available for {quiz.course.title}.",
                link=f"/quiz/{quiz.course.pk}/{quiz.slug}/take/",
                actor=request.user,
            )
    
    return JsonResponse({
        'draft': quiz.draft,
        'status': 'draft' if quiz.draft else _get_quiz_status(quiz),
        'label': 'Draft' if quiz.draft else ('Scheduled' if quiz.available_from and now() < quiz.available_from else 'Live'),
    })


def _get_quiz_status(quiz):
    """Helper: compute display status string for a quiz."""
    if quiz.draft:
        return 'draft'
    if quiz.available_from and now() < quiz.available_from:
        return 'upcoming'
    if quiz.is_expired():
        return 'closed'
    return 'active'


@login_required
def quiz_list(request, slug):
    course = get_object_or_404(Course, slug=slug)
    
    # Access control
    can_access = False
    if request.user.is_superuser or request.user.is_school_admin:
        can_access = True
    elif request.user.is_teacher or request.user.is_lecturer:
        if request.user.can_access_level(course.level):
            can_access = True
    elif request.user.is_student:
        from result.models import TakenCourse
        if TakenCourse.objects.filter(student__student=request.user, course=course).exists():
            can_access = True
    
    if not can_access:
        messages.error(request, "You do not have permission to view quizzes for this course.")
        return redirect('home')
    
    quizzes = Quiz.objects.filter(course=course).order_by("-timestamp")
    
    # Students: hide draft quizzes entirely
    if request.user.is_student:
        quizzes = quizzes.filter(draft=False)
    
    # Get student's completed sittings for this course
    completed_sitting_ids = set()
    if request.user.is_student:
        completed_sitting_ids = set(
            Sitting.objects.filter(
                user=request.user, course=course, complete=True
            ).values_list('quiz_id', flat=True)
        )
    
    quiz_list_data = []
    for quiz in quizzes:
        is_available = quiz.is_available()
        is_expired = quiz.is_expired()
        has_completed = quiz.pk in completed_sitting_ids
        status = _get_quiz_status(quiz)
        
        # Get student's best sitting for this quiz if they've completed attempts
        best_sitting = None
        if request.user.is_student and has_completed:
            best_sitting = quiz.get_best_score_for_user(request.user)

        quiz_list_data.append({
            'quiz': quiz,
            'is_available': is_available,
            'is_expired': is_expired,
            'has_completed': has_completed,
            'best_sitting': best_sitting,
            'attempts_left': quiz.max_attempts - Sitting.objects.filter(user=request.user, quiz=quiz, complete=True).count() if request.user.is_student else None,
            'time_until_available': quiz.time_until_available(),
            'time_until_expires': quiz.time_until_expires(),
            'status': status,
        })
    
    return render(
        request, "quiz/quiz_list.html", {
            "quiz_list": quiz_list_data,
            "course": course
        }
    )


@login_required
def quiz_review(request, pk, slug):
    """Read-only review view for expired quizzes or completed attempts."""
    quiz = get_object_or_404(Quiz, slug=slug)
    course = get_object_or_404(Course, pk=pk)

    # Only allow review if quiz is expired OR student has completed it
    sitting = Sitting.objects.filter(
        user=request.user, quiz=quiz, course=course, complete=True
    ).first()

    if not quiz.is_expired() and not sitting:
        # Quiz still active — redirect to take it
        if quiz.is_available():
            return redirect("quiz_take", pk=pk, slug=slug)
        messages.warning(request, "This quiz is not yet available for review.")
        return redirect("quiz_index", slug=course.slug)

    # Determine whether to show correct answers
    show_answers = False
    if quiz.show_correct_answers_after:
        show_answers = now() >= quiz.show_correct_answers_after
    elif quiz.allow_review_after_submission and sitting:
        show_answers = True

    questions_with_answers = []
    if sitting:
        questions_with_answers = sitting.get_questions(with_answers=True)
    else:
        # No attempt — show questions without answers
        questions_with_answers = quiz.get_questions()

    return render(request, "quiz/quiz_review.html", {
        "quiz": quiz,
        "course": course,
        "sitting": sitting,
        "questions": questions_with_answers,
        "show_answers": show_answers,
        "has_attempt": bool(sitting),
    })


@login_required
def quiz_attempt_history(request, slug):
    """Student's quiz attempt history for a course."""
    course = get_object_or_404(Course, slug=slug)
    
    sittings = Sitting.objects.filter(
        user=request.user,
        course=course,
        complete=True,
    ).select_related('quiz').order_by('-end')
    
    return render(request, "quiz/quiz_history.html", {
        "course": course,
        "sittings": sittings,
    })


@login_required
@lecturer_required
def quiz_results(request, slug, pk):
    """
    Teacher view: Shows all student scores for a specific quiz.
    Groups multiple attempts per student and shows best score.
    """
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, pk=pk)

    # All completed sittings for this quiz
    all_sittings = Sitting.objects.filter(
        quiz=quiz, course=course, complete=True
    ).select_related('user').order_by('user__username', 'attempt_number')

    # Build per-student summary: best score + all attempts
    from collections import defaultdict
    student_map = defaultdict(list)
    for sitting in all_sittings:
        student_map[sitting.user].append(sitting)

    student_results = []
    for user, sittings_list in student_map.items():
        best = max(sittings_list, key=lambda s: s.current_score)
        student_results.append({
            'student': user,
            'best_sitting': best,
            'all_attempts': sittings_list,
            'attempts_count': len(sittings_list),
            'passed': best.check_if_passed,
        })

    # Students who haven't attempted
    from django.contrib.auth import get_user_model
    User = get_user_model()
    attempted_ids = set(student_map.keys())

    return render(request, "quiz/quiz_results.html", {
        "course": course,
        "quiz": quiz,
        "student_results": student_results,
        "total_students": len(student_results),
        "passed_count": sum(1 for r in student_results if r['passed']),
    })


@login_required
@lecturer_required
def teacher_quiz_report(request):
    """
    Teacher view: Complete quiz score report across all assigned subjects.
    Shows every student's best quiz score for every quiz in their subjects.
    Groups results by Course/Level for better terminal reporting.
    """
    from course.models import CourseAllocation

    if request.user.is_superuser or request.user.is_school_admin:
        # Admin: see all quizzes across the school
        quizzes = Quiz.objects.filter(
            course__school=request.school
        ).select_related('course').order_by('course__level', 'course__title', 'title')
    else:
        # Teacher: see only quizzes for their assigned courses
        allocations = CourseAllocation.objects.filter(
            teacher=request.user
        ).values_list('courses', flat=True)
        quizzes = Quiz.objects.filter(
            course__in=allocations,
        ).select_related('course').order_by('course__level', 'course__title', 'title')

    # Build report: Grouped by Course
    from collections import defaultdict
    report_data = defaultdict(list)
    
    for quiz in quizzes:
        # All completed sittings for this quiz
        all_sittings = Sitting.objects.filter(
            quiz=quiz, complete=True
        ).select_related('user').order_by('user__first_name')

        if not all_sittings.exists():
            continue

        student_map = defaultdict(list)
        for s in all_sittings:
            student_map[s.user].append(s)

        student_rows = []
        for user, attempts in student_map.items():
            best = max(attempts, key=lambda s: s.current_score)
            student_rows.append({
                'student': user,
                'best_sitting': best,
                'attempts': len(attempts),
            })

        quiz_data = {
            'quiz': quiz,
            'student_rows': sorted(student_rows, key=lambda x: x['student'].get_full_name()),
            'total': len(student_rows),
            'passed': sum(1 for r in student_rows if r['best_sitting'].check_if_passed),
        }
        report_data[quiz.course].append(quiz_data)

    # Convert defaultdict to sorted list for template
    sorted_report = []
    for course in sorted(report_data.keys(), key=lambda c: (c.level, c.title)):
        sorted_report.append({
            'course': course,
            'quizzes': report_data[course]
        })

    return render(request, "quiz/teacher_quiz_report.html", {
        "report": sorted_report,
        "total_courses": len(sorted_report),
    })


# ########################################################
# Question Management Views
# ########################################################


# Question types that can be added from the quiz workspace. Multiple-choice
# questions are handled separately because they need an inline choice formset.
QUESTION_TYPE_FORMS = {
    "truefalse": (TrueFalseQuestionForm, _("True/False")),
    "fillblank": (FillInTheBlankQuestionForm, _("Fill in the Blank")),
    "essay": (EssayQuestionForm, _("Essay")),
}


def _get_manageable_quiz(request, slug, quiz_id):
    """Return the course/quiz pair, enforcing course-level access."""
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, pk=quiz_id, course=course)

    if not (request.user.is_superuser or request.user.is_school_admin):
        if not request.user.can_access_level(course.level):
            raise PermissionDenied(
                "You cannot manage quizzes for courses outside your division."
            )
    return course, quiz


@login_required
@lecturer_required
def quiz_questions(request, slug, quiz_id):
    """Workspace for viewing and adding all questions in a quiz."""
    course, quiz = _get_manageable_quiz(request, slug, quiz_id)
    questions = list(quiz.get_questions())

    for question in questions:
        class_name = question.__class__.__name__
        question.type_label = {
            "MCQuestion": _("Multiple Choice"),
            "TrueFalseQuestion": _("True/False"),
            "FillInTheBlankQuestion": _("Fill in the Blank"),
            "EssayQuestion": _("Essay"),
        }.get(class_name, _("Question"))
        question.can_edit_here = class_name in {
            "TrueFalseQuestion",
            "FillInTheBlankQuestion",
            "EssayQuestion",
        }
        question.is_mc = class_name == "MCQuestion"
        question.is_truefalse = class_name == "TrueFalseQuestion"
        question.is_fillblank = class_name == "FillInTheBlankQuestion"
        question.is_essay = class_name == "EssayQuestion"
        if question.is_mc:
            question.choices = list(question.get_choices())

    return render(request, "quiz/quiz_questions.html", {
        "course": course,
        "quiz": quiz,
        "questions": questions,
    })


@login_required
@lecturer_required
def question_create(request, slug, quiz_id, qtype):
    """Create a true/false, fill-in-the-blank or essay question."""
    if qtype not in QUESTION_TYPE_FORMS:
        raise Http404("Unknown question type.")

    course, quiz = _get_manageable_quiz(request, slug, quiz_id)
    form_class, type_label = QUESTION_TYPE_FORMS[qtype]

    form = form_class(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        question = form.save()
        question.quiz.add(quiz)
        messages.success(request, f"{type_label} question added to {quiz.title}.")
        if "another" in request.POST:
            return redirect(
                "question_create",
                slug=course.slug,
                quiz_id=quiz.pk,
                qtype=qtype,
            )
        return redirect("quiz_questions", slug=course.slug, quiz_id=quiz.pk)

    return render(request, "quiz/question_form.html", {
        "course": course,
        "quiz": quiz,
        "form": form,
        "type_label": type_label,
        "qtype": qtype,
    })


@login_required
@lecturer_required
def question_edit(request, slug, quiz_id, pk):
    """Edit a non-multiple-choice question."""
    course, quiz = _get_manageable_quiz(request, slug, quiz_id)
    base_question = get_object_or_404(Question, pk=pk, quiz=quiz)
    question = Question.objects.get_subclass(pk=base_question.pk)

    qtype = {
        "TrueFalseQuestion": "truefalse",
        "FillInTheBlankQuestion": "fillblank",
        "EssayQuestion": "essay",
    }.get(question.__class__.__name__)

    if qtype is None:
        messages.info(
            request,
            "Multiple-choice questions can be edited from the admin site.",
        )
        return redirect("quiz_questions", slug=course.slug, quiz_id=quiz.pk)

    form_class, type_label = QUESTION_TYPE_FORMS[qtype]
    form = form_class(request.POST or None, request.FILES or None, instance=question)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{type_label} question updated.")
        return redirect("quiz_questions", slug=course.slug, quiz_id=quiz.pk)

    return render(request, "quiz/question_form.html", {
        "course": course,
        "quiz": quiz,
        "form": form,
        "type_label": type_label,
        "qtype": qtype,
        "question": question,
    })


@login_required
@lecturer_required
def question_delete(request, slug, quiz_id, pk):
    """Remove a question from a quiz after confirmation."""
    course, quiz = _get_manageable_quiz(request, slug, quiz_id)
    question = get_object_or_404(Question, pk=pk, quiz=quiz)

    if request.method == "POST":
        question.delete()
        messages.success(request, "Question deleted.")
    return redirect("quiz_questions", slug=course.slug, quiz_id=quiz.pk)


# ########################################################
# Multiple Choice Question Views
# ########################################################


@method_decorator([login_required, lecturer_required], name="dispatch")
class MCQuestionCreate(CreateView):
    model = MCQuestion
    form_class = MCQuestionForm
    template_name = "quiz/mcquestion_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = get_object_or_404(Course, slug=self.kwargs["slug"])
        context["quiz_obj"] = get_object_or_404(Quiz, id=self.kwargs["quiz_id"])
        context["quiz_questions_count"] = Question.objects.filter(
            quiz=self.kwargs["quiz_id"]
        ).count()
        if self.request.method == "POST":
            context["formset"] = MCQuestionFormSet(self.request.POST)
        else:
            context["formset"] = MCQuestionFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["formset"]
        if formset.is_valid():
            with transaction.atomic():
                self.object = form.save(commit=False)
                self.object.save()
                quiz = get_object_or_404(Quiz, id=self.kwargs["quiz_id"])
                self.object.quiz.add(quiz)
                formset.instance = self.object
                formset.save()

                if "another" in self.request.POST:
                    return redirect(
                        "mc_create",
                        slug=self.kwargs["slug"],
                        quiz_id=self.kwargs["quiz_id"],
                    )
                return redirect(
                    "quiz_questions",
                    slug=self.kwargs["slug"],
                    quiz_id=self.kwargs["quiz_id"],
                )
        else:
            return self.form_invalid(form)


# ########################################################
# Quiz Progress and Marking Views
# ########################################################


@method_decorator([login_required], name="dispatch")
class QuizUserProgressView(TemplateView):
    template_name = "quiz/progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        progress, _ = Progress.objects.get_or_create(user=self.request.user)
        context["cat_scores"] = progress.list_all_cat_scores
        context["exams"] = progress.show_exams()
        context["exams_counter"] = context["exams"].count()
        return context


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizMarkingList(ListView):
    model = Sitting
    template_name = "quiz/quiz_marking_list.html"

    def get_queryset(self):
        queryset = Sitting.objects.filter(
            complete=True,
            course__school=self.request.school,
        )
        if not (
            self.request.user.is_superuser
            or self.request.user.is_school_admin
        ):
            queryset = queryset.filter(
                quiz__course__allocated_course__teacher__pk=self.request.user.id
            )
        quiz_filter = self.request.GET.get("quiz_filter")
        if quiz_filter:
            queryset = queryset.filter(quiz__title__icontains=quiz_filter)
        user_filter = self.request.GET.get("user_filter")
        if user_filter:
            queryset = queryset.filter(user__username__icontains=user_filter)
        return queryset


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizMarkingDetail(DetailView):
    model = Sitting
    template_name = "quiz/quiz_marking_detail.html"

    def post(self, request, *args, **kwargs):
        sitting = self.get_object()
        question_id = request.POST.get("qid")
        if question_id:
            question = Question.objects.get_subclass(id=int(question_id))
            if int(question_id) in sitting.get_incorrect_questions:
                sitting.remove_incorrect_question(question)
            else:
                sitting.add_incorrect_question(question)
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["questions"] = self.object.get_questions(with_answers=True)
        return context


# ########################################################
# Quiz Taking View
# ########################################################


@method_decorator([login_required], name="dispatch")
class QuizTake(FormView):
    form_class = QuestionForm
    template_name = "quiz/question.html"
    result_template_name = "quiz/result.html"

    def dispatch(self, request, *args, **kwargs):
        self.quiz = get_object_or_404(Quiz, slug=self.kwargs["slug"])
        self.course = get_object_or_404(Course, pk=self.kwargs["pk"])

        # Block students from draft quizzes even via direct URL
        if request.user.is_student and self.quiz.draft:
            messages.error(request, "This quiz is not available.")
            return redirect("quiz_index", slug=self.course.slug)
        
        # Check if quiz is available
        if not self.quiz.is_available():
            if request.user.is_student:
                # Expired quiz → redirect to review
                if self.quiz.is_expired():
                    return redirect("quiz_review", pk=self.course.pk, slug=self.quiz.slug)
                if self.quiz.available_from and now() < self.quiz.available_from:
                    messages.warning(
                        request,
                        f"This quiz is not yet available. It will open on {self.quiz.available_from.strftime('%B %d, %Y at %I:%M %p')}."
                    )
                else:
                    messages.warning(request, "This quiz is no longer available.")
                return redirect("quiz_index", slug=self.course.slug)
        
        if not Question.objects.filter(quiz=self.quiz).exists():
            messages.warning(request, "This quiz has no questions available.")
            return redirect("quiz_index", slug=self.course.slug)

        self.sitting = Sitting.objects.user_sitting(
            request.user, self.quiz, self.course
        )
        if not self.sitting:
            messages.info(
                request,
                "You have already completed this quiz. Only one attempt is permitted.",
            )
            return redirect("quiz_index", slug=self.course.slug)
        
        # Server-side time expiry check — auto-submit if expired
        if self.sitting.is_time_expired():
            messages.warning(request, "Time has expired for this quiz. Your answers have been automatically submitted.")
            self.sitting.mark_quiz_complete()
            return redirect("quiz_review", pk=self.course.pk, slug=self.quiz.slug)

        self.question = self.sitting.get_first_question()
        self.progress = self.sitting.progress()

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["question"] = self.question
        return kwargs

    def get_form_class(self):
        if isinstance(self.question, EssayQuestion):
            return EssayForm
        elif isinstance(self.question, TrueFalseQuestion):
            return TrueFalseForm
        elif isinstance(self.question, FillInTheBlankQuestion):
            return FillInTheBlankForm
        return self.form_class

    def form_valid(self, form):
        self.form_valid_user(form)
        if not self.sitting.get_first_question():
            return self.final_result_user()
        return super().get(self.request)

    def form_valid_user(self, form):
        progress, _ = Progress.objects.get_or_create(user=self.request.user)
        guess = form.cleaned_data["answers"]
        is_correct = self.question.check_if_correct(guess)

        if is_correct:
            self.sitting.add_to_score(1)
            progress.update_score(self.question, 1, 1)
        else:
            self.sitting.add_incorrect_question(self.question)
            progress.update_score(self.question, 0, 1)

        if not self.quiz.answers_at_end:
            self.previous = {
                "previous_answer": guess,
                "previous_outcome": is_correct,
                "previous_question": self.question,
                "answers": self.question.get_choices(),
                "question_type": {self.question.__class__.__name__: True},
            }
        else:
            self.previous = {}

        self.sitting.add_user_answer(self.question, guess)
        self.sitting.remove_first_question()

        self.question = self.sitting.get_first_question()
        self.progress = self.sitting.progress()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["question"] = self.question
        context["quiz"] = self.quiz
        context["course"] = self.course
        if hasattr(self, "previous"):
            context["previous"] = self.previous
        if hasattr(self, "progress"):
            context["progress"] = self.progress
        
        # Timer context
        if self.quiz.time_limit_minutes:
            context["time_limit_minutes"] = self.quiz.time_limit_minutes
            context["time_remaining_seconds"] = self.sitting.get_time_remaining()
            context["show_timer"] = True
        else:
            context["show_timer"] = False
        
        return context

    def final_result_user(self):
        self.sitting.mark_quiz_complete()
        if self.quiz.exam_paper and self.request.user.is_student:
            from core.notifications import notify
            from course.models import CourseAllocation

            teacher_ids = CourseAllocation.objects.filter(
                courses=self.course
            ).values_list("teacher_id", flat=True).distinct()
            for teacher in User.objects.filter(
                pk__in=teacher_ids, school=self.course.school
            ):
                notify(
                    school=self.course.school,
                    recipient=teacher,
                    title=f"Quiz submitted: {self.quiz.title}",
                    message=f"{self.request.user.get_full_name} submitted {self.quiz.title} and it may need marking.",
                    link="/quiz/marking_list/",
                    actor=self.request.user,
                )
        results = {
            "course": self.course,
            "quiz": self.quiz,
            "score": self.sitting.get_current_score,
            "max_score": self.sitting.get_max_score,
            "percent": self.sitting.get_percent_correct,
            "sitting": self.sitting,
            "previous": getattr(self, "previous", {}),
        }

        if self.quiz.answers_at_end:
            results["questions"] = self.sitting.get_questions(with_answers=True)
            results["incorrect_questions"] = self.sitting.get_incorrect_questions

        if (
            not self.quiz.exam_paper
            or self.request.user.is_superuser
            or self.request.user.is_school_admin
            or self.request.user.is_lecturer
            or self.request.user.is_teacher
        ):
            self.sitting.delete()

        return render(self.request, self.result_template_name, results)
