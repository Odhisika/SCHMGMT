"""
Deterministic demo/test data builder for the school management system.

The same builder is used by the ``seed_demo_data`` management command and by
the automated test-suite, so the fixtures exercised by tests are the same
relational graph that is seeded into a development database.

Everything is deterministic for a given ``seed`` value, which keeps test
assertions stable and makes the seeded demo database reproducible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from accounts.models import DepartmentHead, Parent, Student, User
from attendance.models import Attendance as AttendanceRecord
from attendance.models import AttendanceSession as AttendanceSessionModel
from attendance.models import AttendanceSummary
from core.models import House, NewsAndEvents, Term, TermWeek
from course.models import (
    Course,
    CourseAllocation,
    LessonNote,
    Program,
    SubjectTemplate,
)
from fees.models import (
    FeeItem,
    FeeStructure,
    Payment,
    SchoolBankAccount,
    StudentFeeAssignment,
    StudentPaymentReference,
)
from payments.models import FeeStructure as LegacyFeeStructure
from payments.models import Invoice
from payments.models import StudentPayment as LegacyStudentPayment
from quiz.models import (
    Assignment,
    Choice,
    FillInTheBlankQuestion,
    MCQuestion,
    Quiz,
    TrueFalseQuestion,
)
from resources.models import CourseFile, CourseVideo
from result.models import (
    BECEMockExam,
    BECEMockResult,
    PromotionRequest,
    Result,
    ResultEditRequest,
    TakenCourse,
)
from school.models import GradeWeightConfig, PromotionPolicy, School
from timetable.models import Period, TimetableEntry

DEMO_PASSWORD = "DemoPass123!"
DEMO_SCHOOL_NAME = "Greenwood International School"
DEMO_SCHOOL_SLUG = "greenwood-international-school"
DEMO_SCHOOL_SUBDOMAIN = "greenwood"
DEMO_EMAIL_DOMAIN = "greenwood.test"

WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]

# (subject title, code prefix, is core)
SUBJECTS = [
    ("English Language", "ENG", True),
    ("Mathematics", "MATH", True),
    ("Integrated Science", "SCI", True),
    ("Social Studies", "SOC", True),
    ("Computing", "ICT", False),
]

DIVISION_PROGRAMS = {
    settings.DIVISION_NURSERY: "Nursery Section",
    settings.DIVISION_PRIMARY: "Primary Section",
    settings.DIVISION_JHS: "JHS Section",
}


@dataclass
class DemoData:
    """Handles to every object created by :func:`build_demo_data`."""

    school: School
    superuser: User
    admin: User
    teachers: dict = field(default_factory=dict)
    class_teacher: User | None = None
    dep_head: User | None = None
    parents: dict = field(default_factory=dict)
    students: dict = field(default_factory=dict)  # level -> [Student]
    terms: dict = field(default_factory=dict)
    current_term: Term | None = None
    programs: dict = field(default_factory=dict)
    departments: dict = field(default_factory=dict)
    courses: dict = field(default_factory=dict)  # level -> [Course]
    taken_courses: list = field(default_factory=list)
    results: list = field(default_factory=list)
    quizzes: list = field(default_factory=list)
    fee_structures: list = field(default_factory=list)
    payments: list = field(default_factory=list)

    def student_users(self):
        return [student.student for students in self.students.values() for student in students]


def _level_code(level: str) -> str:
    return level.replace(" ", "").replace("-", "").upper()


def _division_for_level(level: str) -> str:
    for division, levels in settings.DIVISION_LEVEL_MAPPING.items():
        if level in levels:
            return division
    return settings.DIVISION_PRIMARY


def _create_user(username, *, school, password=DEMO_PASSWORD, **extra):
    extra.setdefault("email", f"{username}@{DEMO_EMAIL_DOMAIN}")
    extra.setdefault("first_name", username.replace(".", " ").title().split()[0])
    extra.setdefault("last_name", "Demo")
    return User.objects.create_user(
        username=username,
        password=password,
        school=school,
        **extra,
    )


def build_demo_data(
    *,
    levels=None,
    students_per_level=3,
    attendance_days=10,
    timetable=True,
    quizzes=True,
    resources=True,
    seed=42,
) -> DemoData:
    """Create a complete, deterministic school dataset.

    Parameters are intentionally conservative so the same function can build a
    small fixture for tests and a larger demo database for manual testing.
    """
    rng = random.Random(seed)
    levels = list(levels) if levels is not None else [choice[0] for choice in settings.LEVEL_CHOICES]
    today = date.today()
    academic_year = str(today.year)

    data = DemoData(school=None, superuser=None, admin=None)

    # ------------------------------------------------------------------
    # School, branding and policies
    # ------------------------------------------------------------------
    school = School.objects.create(
        name=DEMO_SCHOOL_NAME,
        slug=DEMO_SCHOOL_SLUG,
        subdomain=DEMO_SCHOOL_SUBDOMAIN,
        email="info@greenwood.test",
        phone="+233200000001",
        address="12 Independence Avenue, Accra, Ghana",
        website="https://greenwood.test",
        motto="Knowledge, Integrity, Service",
        founded_year=1998,
        primary_color="#0d6efd",
        secondary_color="#6c757d",
        accent_color="#ffc107",
        is_active=True,
    )
    data.school = school

    GradeWeightConfig.objects.create(
        school=school,
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
    PromotionPolicy.objects.create(
        school=school,
        promotion_cut_off=Decimal("50.00"),
        failure_cut_off=Decimal("40.00"),
        apply_to_all_terms=False,
        allow_teacher_requests=True,
    )

    # ------------------------------------------------------------------
    # Houses
    # ------------------------------------------------------------------
    houses = []
    for name, color, points in [
        ("Red House", "#dc3545", 120),
        ("Blue House", "#0d6efd", 115),
        ("Green House", "#198754", 130),
        ("Yellow House", "#ffc107", 100),
    ]:
        houses.append(
            House.objects.create(
                school=school, name=name, color=color, points=points,
                description=f"{name} house",
            )
        )

    # ------------------------------------------------------------------
    # Terms and term weeks
    # ------------------------------------------------------------------
    term_names = [settings.FIRST_TERM, settings.SECOND_TERM, settings.THIRD_TERM]
    for index, term_name in enumerate(term_names):
        start = today - timedelta(days=60 * (2 - index))
        end = start + timedelta(days=60)
        term = Term.objects.create(
            school=school,
            term=term_name,
            year=academic_year,
            is_current_term=(index == len(term_names) - 1),
            start_date=start,
            end_date=end,
            next_term_begins=end + timedelta(days=21),
            result_released=(index < len(term_names) - 1),
        )
        data.terms[term_name] = term

        for week in range(1, 15):
            if week == 7:
                activity = "mid_term"
                title = "Mid-Term Break"
            elif week == 13:
                activity = "sports"
                title = "Sports Week"
            else:
                activity = "normal_lesson"
                title = ""
            TermWeek.objects.create(
                term=term,
                week_number=week,
                activity_type=activity,
                title=title,
                description=f"Week {week} activities",
            )

    current_term = data.terms[settings.THIRD_TERM]
    data.current_term = current_term

    # ------------------------------------------------------------------
    # Programs / departments
    # ------------------------------------------------------------------
    for division, title in DIVISION_PROGRAMS.items():
        program = Program.objects.create(
            title=title,
            school=school,
            division=division,
            is_academic_block=True,
            summary=f"{title} academic division",
        )
        data.programs[division] = program

    maths_department = Program.objects.create(
        title="Mathematics Department",
        school=school,
        division=settings.DIVISION_JHS,
        is_academic_block=False,
        summary="Subject department for mathematics",
    )
    data.departments["mathematics"] = maths_department

    # ------------------------------------------------------------------
    # Courses and subject templates
    # ------------------------------------------------------------------
    for level in levels:
        division = _division_for_level(level)
        program = data.programs[division]
        level_courses = []
        for subject, prefix, is_core in SUBJECTS:
            code = f"{prefix}-{_level_code(level)}"
            course = Course.objects.create(
                title=subject,
                code=code,
                summary=f"{subject} for {level}",
                program=program,
                level=level,
                term=current_term.term,
                is_core_subject=is_core,
                is_elective=not is_core,
                school=school,
            )
            level_courses.append(course)
        data.courses[level] = level_courses

        SubjectTemplate.objects.create(
            title=f"{level} Core Package",
            code_prefix=f"CORE-{_level_code(level)}",
            level=level,
            division=division,
            is_core_subject=True,
            is_elective=False,
            description=f"Core subject package for {level}",
            school=school,
        )

    # ------------------------------------------------------------------
    # Users: superuser, admin, teachers, class teacher, department head
    # ------------------------------------------------------------------
    data.superuser = User.objects.create_superuser(
        username="root",
        email=f"root@{DEMO_EMAIL_DOMAIN}",
        password=DEMO_PASSWORD,
        first_name="Root",
        last_name="Administrator",
    )
    data.admin = _create_user(
        "admin",
        school=school,
        is_school_admin=True,
        first_name="Ama",
        last_name="Mensah",
        gender="F",
        phone="+233200000002",
    )

    for division in DIVISION_PROGRAMS:
        teacher = _create_user(
            f"teacher.{division.lower()}",
            school=school,
            is_lecturer=True,
            is_teacher=True,
            division=division,
            department=data.programs[division],
            gender="M",
            phone="+233200000010",
        )
        data.teachers[division] = teacher

    primary_levels = settings.DIVISION_LEVEL_MAPPING[settings.DIVISION_PRIMARY]
    data.class_teacher = _create_user(
        "class.teacher",
        school=school,
        is_lecturer=True,
        is_teacher=True,
        is_class_teacher=True,
        division=settings.DIVISION_PRIMARY,
        assigned_level=primary_levels[0],
        department=data.programs[settings.DIVISION_PRIMARY],
        gender="F",
        phone="+233200000011",
    )
    data.teachers["class_teacher"] = data.class_teacher

    data.dep_head = _create_user(
        "dept.head",
        school=school,
        is_lecturer=True,
        is_teacher=True,
        is_dep_head=True,
        division=settings.DIVISION_JHS,
        department=maths_department,
        gender="M",
        phone="+233200000012",
    )
    DepartmentHead.objects.create(user=data.dep_head, department=maths_department)

    # ------------------------------------------------------------------
    # Students and parents
    # ------------------------------------------------------------------
    first_names = ["Kofi", "Ama", "Yaw", "Akosua", "Kwame", "Abena", "Kojo", "Adwoa"]
    last_names = ["Owusu", "Boateng", "Asante", "Mensah", "Darko", "Appiah"]

    for level_index, level in enumerate(levels):
        division = _division_for_level(level)
        program = data.programs[division]
        data.students[level] = []
        for i in range(students_per_level):
            first_name = first_names[(level_index + i) % len(first_names)]
            last_name = last_names[(level_index + i) % len(last_names)]
            username = f"student.{_level_code(level).lower()}.{i + 1}"
            user = _create_user(
                username,
                school=school,
                is_student=True,
                first_name=first_name,
                last_name=last_name,
                gender="M" if i % 2 == 0 else "F",
                phone=f"+2332000{level_index:02d}{i:03d}",
            )
            student = Student.objects.create(
                student=user,
                level=level,
                program=program,
                house=houses[(level_index + i) % len(houses)].name,
            )
            data.students[level].append(student)

        # One parent per level, linked to the first student of that level.
        parent_user = _create_user(
            f"parent.{_level_code(level).lower()}",
            school=school,
            is_parent=True,
            first_name="Parent",
            last_name=last_name,
            gender="F",
            phone=f"+2332000{level_index:02d}999",
        )
        parent = Parent.objects.create(
            user=parent_user,
            student=data.students[level][0],
            first_name="Parent",
            last_name=last_name,
            phone=parent_user.phone,
            email=parent_user.email,
            relation_ship="Mother",
        )
        data.parents[level] = parent

    # ------------------------------------------------------------------
    # Course allocations
    # ------------------------------------------------------------------
    for division, teacher in data.teachers.items():
        if division not in DIVISION_PROGRAMS:
            continue
        division_levels = settings.DIVISION_LEVEL_MAPPING[division]
        courses = [c for level in division_levels for c in data.courses.get(level, [])]
        if not courses:
            continue
        allocation = CourseAllocation.objects.create(teacher=teacher)
        allocation.courses.set(courses)

    # ------------------------------------------------------------------
    # Enrollment (TakenCourse) and term results
    # ------------------------------------------------------------------
    for level_index, level in enumerate(levels):
        level_courses = data.courses[level]
        for student_index, student in enumerate(data.students[level]):
            for course_index, course in enumerate(level_courses):
                base = 45 + ((level_index * 7 + student_index * 11 + course_index * 5) % 50)
                # ``course.signals`` auto-enrols students in core subjects, so
                # reuse any existing row rather than creating duplicates.
                tc, _ = TakenCourse.objects.get_or_create(
                    student=student,
                    course=course,
                    school=school,
                )
                tc.classwork_score = Decimal(str(base))
                tc.midsem_score = Decimal(str(max(0, base - 3)))
                tc.assignment_score = Decimal(str(max(0, base - 2)))
                tc.attendance_score = Decimal("90.00")
                tc.exam_score = Decimal(str(max(0, base - 1)))
                tc.save()
                data.taken_courses.append(tc)

    for level_index, level in enumerate(levels):
        for student in data.students[level]:
            avg = TakenCourse.objects.filter(
                student=student,
                course__term=current_term.term,
            )
            term_average = (
                sum(tc.total for tc in avg) / Decimal(avg.count())
                if avg.count()
                else Decimal("0.00")
            )
            result = Result.objects.create(
                student=student,
                term_average=round(term_average, 2),
                term=current_term.term,
                session=academic_year,
                level=level,
                school=school,
                days_present=attendance_days - 1,
                days_absent=1,
                total_attendance_days=attendance_days,
            )
            data.results.append(result)

    # Recalculate positions after all rows exist so order-independent inserts
    # produce correct standings.
    for tc in data.taken_courses:
        tc.calculate_class_position()
    for result in data.results:
        result.calculate_overall_position()

    # ------------------------------------------------------------------
    # Attendance records and summaries
    # ------------------------------------------------------------------
    day_cursor = today
    attendance_dates = []
    while len(attendance_dates) < attendance_days:
        if day_cursor.weekday() < 5:
            attendance_dates.append(day_cursor)
        day_cursor -= timedelta(days=1)

    for level in levels:
        teacher = data.teachers[_division_for_level(level)]
        level_students = data.students[level]
        for day in attendance_dates:
            session = AttendanceSessionModel.objects.create(
                school=school,
                term=current_term,
                level=level,
                date=day,
                marked_by=teacher,
                notes="Auto-seeded attendance session",
            )
            for index, student in enumerate(level_students):
                if index % 5 == 0:
                    status = "Absent"
                elif index % 7 == 0:
                    status = "Late"
                else:
                    status = "Present"
                AttendanceRecord.objects.create(
                    student=student,
                    date=day,
                    status=status,
                    recorded_by=teacher,
                    school=school,
                )
            session.notes = f"{len(level_students)} students marked"
            session.save(update_fields=["notes"])

        for student in level_students:
            records = AttendanceRecord.objects.filter(student=student)
            AttendanceSummary.objects.update_or_create(
                student=student,
                term=current_term,
                school=school,
                defaults={
                    "days_present": records.filter(status="Present").count(),
                    "days_absent": records.filter(status="Absent").count(),
                    "days_late": records.filter(status="Late").count(),
                    "days_excused": records.filter(status="Excused").count(),
                    "total_school_days": records.count(),
                },
            )

    # ------------------------------------------------------------------
    # Fees, assignments, payments and school bank accounts
    # ------------------------------------------------------------------
    for level_index, level in enumerate(levels):
        fee = FeeStructure.objects.create(
            school=school,
            name=f"{level} Term Fees",
            level=level,
            term=current_term.term,
            is_active=True,
            auto_assign=True,
            description=f"Full term fees for {level}",
        )
        for item_name, amount in [
            ("Tuition", Decimal("500.00")),
            ("PTA Dues", Decimal("50.00")),
            ("Sports Levy", Decimal("30.00")),
            ("Examination", Decimal("40.00")),
            ("Library", Decimal("20.00")),
            ("Development Levy", Decimal("100.00")),
        ]:
            FeeItem.objects.create(fee_structure=fee, name=item_name, amount=amount)
        fee.update_total_amount()
        data.fee_structures.append(fee)

        for student_index, student in enumerate(data.students[level]):
            # ``fees.signals`` may already have auto-assigned this fee on
            # creation; keep the amount in sync with the final structure total.
            assignment, _ = StudentFeeAssignment.objects.update_or_create(
                student=student,
                fee_structure=fee,
                term=current_term,
                defaults={
                    "amount": fee.amount,
                    "due_date": today + timedelta(days=14),
                },
            )
            if student_index == 0:
                payment = Payment.objects.create(
                    school=school,
                    student=student,
                    assignment=assignment,
                    amount=fee.amount,
                    payment_method="CASH",
                    status="VERIFIED",
                    gateway_type="MANUAL",
                    recorded_by=data.admin,
                    receipt_number=f"RCPT-{_level_code(level)}-{student_index + 1}",
                    payment_date=today,
                    verified_at=timezone.now(),
                    notes="Full payment (seeded)",
                )
                data.payments.append(payment)
            elif student_index == 1:
                payment = Payment.objects.create(
                    school=school,
                    student=student,
                    assignment=assignment,
                    amount=(fee.amount / 2).quantize(Decimal("0.01")),
                    payment_method="MOBILE_MONEY",
                    status="VERIFIED",
                    gateway_type="MANUAL",
                    recorded_by=data.admin,
                    receipt_number=f"RCPT-{_level_code(level)}-{student_index + 1}",
                    payment_date=today - timedelta(days=1),
                    verified_at=timezone.now(),
                    notes="Part payment (seeded)",
                )
                data.payments.append(payment)
            else:
                payment = Payment.objects.create(
                    school=school,
                    student=student,
                    assignment=assignment,
                    amount=Decimal("100.00"),
                    payment_method="PAYSTACK",
                    status="PENDING",
                    gateway_type="PAYSTACK",
                    paystack_reference=f"PS-{_level_code(level)}-{student_index + 1}",
                    receipt_number=f"RCPT-{_level_code(level)}-{student_index + 1}",
                    payment_date=today - timedelta(days=2),
                    notes="Awaiting online payment verification (seeded)",
                )
                data.payments.append(payment)

    SchoolBankAccount.objects.create(
        school=school,
        account_type="BANK",
        bank_name="GCB Bank",
        account_name=DEMO_SCHOOL_NAME,
        account_number="1234567890",
        branch="Accra Main",
        swift_code="GHCBGHAC",
        is_active=True,
        is_default=True,
        notes="Please quote the student reference when paying.",
    )
    SchoolBankAccount.objects.create(
        school=school,
        account_type="MOBILE_MONEY",
        account_name=DEMO_SCHOOL_NAME,
        mobile_money_number="0240000000",
        mobile_money_network="MTN",
        is_active=True,
        is_default=True,
        notes="MTN MoMo merchant account.",
    )

    for student in data.student_users():
        student_profile = Student.objects.get(student=student)
        StudentPaymentReference.objects.get_or_create(student=student_profile)

    # ------------------------------------------------------------------
    # Timetable
    # ------------------------------------------------------------------
    if timetable:
        period_specs = [
            ("Period 1", "LESSON", time(8, 0), time(8, 40)),
            ("Period 2", "LESSON", time(8, 40), time(9, 20)),
            ("Short Break", "BREAK", time(9, 20), time(9, 40)),
            ("Period 3", "LESSON", time(9, 40), time(10, 20)),
            ("Period 4", "LESSON", time(10, 20), time(11, 0)),
            ("Long Break", "BREAK", time(11, 0), time(12, 0)),
            ("Period 5", "LESSON", time(12, 0), time(12, 40)),
            ("Period 6", "LESSON", time(12, 40), time(13, 20)),
        ]
        periods_by_division = {}
        for division in DIVISION_PROGRAMS:
            periods = []
            for order, (name, ptype, start, end) in enumerate(period_specs, start=1):
                period = Period.objects.create(
                    school=school,
                    name=name,
                    period_type=ptype,
                    division=division,
                    start_time=start,
                    end_time=end,
                    order=order,
                )
                periods.append(period)
            periods_by_division[division] = periods

        for level in levels:
            division = _division_for_level(level)
            division_courses = data.courses[level]
            lesson_periods = [p for p in periods_by_division[division] if p.period_type == "LESSON"]
            for day_index, day in enumerate(WEEKDAYS):
                for period_index, period in enumerate(lesson_periods):
                    course = division_courses[(day_index + period_index) % len(division_courses)]
                    TimetableEntry.objects.create(
                        school=school,
                        term=current_term,
                        level=level,
                        day_of_week=day,
                        period=period,
                        subject=course,
                        teacher=data.teachers[division],
                        classroom=f"Room {level}",
                        notes="Seeded timetable slot",
                    )

    # ------------------------------------------------------------------
    # Quizzes, questions and assignments
    # ------------------------------------------------------------------
    if quizzes:
        for level in levels[:2]:
            course = data.courses[level][0]
            quiz = Quiz.objects.create(
                course=course,
                title=f"{course.title} Quiz - {level}",
                description=f"Auto-seeded quiz for {course.title} ({level}).",
                category="assignment",
                random_order=False,
                answers_at_end=False,
                exam_paper=True,
                single_attempt=False,
                max_attempts=2,
                pass_mark=50,
                draft=False,
                time_limit_minutes=20,
                allow_review_after_submission=True,
            )
            data.quizzes.append(quiz)

            for q_index in range(3):
                question = MCQuestion.objects.create(
                    content=f"Question {q_index + 1}: What is {q_index + 1} + {q_index + 1}?",
                    explanation=f"{q_index + 1} + {q_index + 1} = {2 * (q_index + 1)}",
                    choice_order="content",
                )
                for option_index in range(3):
                    Choice.objects.create(
                        question=question,
                        choice_text=str(2 * (q_index + 1) + option_index),
                        correct=option_index == 0,
                    )
                question.quiz.add(quiz)

            true_false = TrueFalseQuestion.objects.create(
                content="The earth revolves around the sun.",
                correct_answer=True,
                explanation="Yes, the earth revolves around the sun.",
            )
            true_false.quiz.add(quiz)

            fill_blank = FillInTheBlankQuestion.objects.create(
                content="The capital city of Ghana is ______.",
                correct_answer="Accra",
                case_sensitive=False,
                explanation="Accra is the capital of Ghana.",
            )
            fill_blank.quiz.add(quiz)

            Assignment.objects.create(
                quiz=quiz,
                title=f"{course.title} Homework",
                description="Complete the practice questions in your workbook.",
                due_date=timezone.now() + timedelta(days=7),
                max_score=100,
            )

    # ------------------------------------------------------------------
    # Learning resources
    # ------------------------------------------------------------------
    if resources:
        for level in levels[:2]:
            course = data.courses[level][0]
            teacher = data.teachers[_division_for_level(level)]
            CourseFile.objects.create(
                title=f"{course.title} Class Notes",
                course=course,
                file=f"course_resources/files/demo/{course.slug}-notes.pdf",
                description="Seeded class notes (placeholder file).",
                uploaded_by=teacher,
                school=school,
                downloads=3,
            )
            CourseVideo.objects.create(
                title=f"{course.title} Lesson Video",
                course=course,
                video=f"course_resources/videos/demo/{course.slug}-lesson.mp4",
                description="Seeded lesson video (placeholder file).",
                uploaded_by=teacher,
                school=school,
                duration=timedelta(minutes=12),
                views=7,
            )

    # ------------------------------------------------------------------
    # Lesson notes
    # ------------------------------------------------------------------
    if levels:
        first_level = levels[0]
        teacher = data.teachers[_division_for_level(first_level)]
        for week, status in [(1, "SUBMITTED"), (2, "DRAFT")]:
            LessonNote.objects.create(
                teacher=teacher,
                course=data.courses[first_level][0],
                term=current_term,
                week_number=week,
                title=f"Week {week} Lesson",
                topic="Introduction and revision",
                objectives="Learners will recall prior knowledge and set goals.",
                content="Revision of previous term topics and introduction to new themes.",
                methodology="Discussion, group work and guided practice.",
                assessment="Oral questions and short exercise.",
                resources_needed="Textbook, chalkboard, worksheets.",
                homework="Read pages 1-5 of the textbook.",
                status=status,
            )

    # ------------------------------------------------------------------
    # News and events
    # ------------------------------------------------------------------
    NewsAndEvents.objects.create(
        school=school,
        title="Welcome Back to School",
        summary="We welcome all learners and parents to the new academic year.",
        posted_as="News",
        target_role="ALL",
    )
    NewsAndEvents.objects.create(
        school=school,
        title="PTA General Meeting",
        summary="The PTA general meeting will be held in the school hall.",
        posted_as="Event",
        target_role="PARENTS",
    )
    NewsAndEvents.objects.create(
        school=school,
        title="Examination Timetable Released",
        summary="The end-of-term examination timetable is now available.",
        posted_as="News",
        target_role="STUDENTS",
        target_division=settings.DIVISION_JHS,
    )

    # ------------------------------------------------------------------
    # BECE mock exam for the final JHS class
    # ------------------------------------------------------------------
    jhs_levels = settings.DIVISION_LEVEL_MAPPING[settings.DIVISION_JHS]
    if jhs_levels[-1] in data.courses:
        level = jhs_levels[-1]
        mock_exam = BECEMockExam.objects.create(
            name="First Mock Examination",
            year=academic_year,
            date_started=today - timedelta(days=30),
            date_finished=today - timedelta(days=25),
            is_active=True,
            school=school,
        )
        for student in data.students[level]:
            for course_index, course in enumerate(data.courses[level][:3]):
                BECEMockResult.objects.create(
                    student=student,
                    mock_exam=mock_exam,
                    course=course,
                    score=Decimal(str(60 + course_index * 5)),
                    remarks="Seeded mock result",
                )

    # ------------------------------------------------------------------
    # Workflow records: result edits and promotion requests
    # ------------------------------------------------------------------
    if data.results:
        teacher = data.teachers[settings.DIVISION_PRIMARY]
        first_course = data.courses[levels[0]][0]
        ResultEditRequest.objects.create(
            teacher=teacher,
            course=first_course,
            term=current_term,
            requested_by=data.admin,
            request_type=ResultEditRequest.ADMIN_REQUEST,
            reason="Please review the examination score for this course.",
            status=ResultEditRequest.PENDING,
            school=school,
        )

        borderline = next(
            (r for r in data.results if r.term_average is not None and r.term_average < Decimal("50")),
            data.results[0],
        )
        PromotionRequest.objects.create(
            student=borderline.student,
            result=borderline,
            request_type="PROMOTE",
            requested_by=teacher,
            reason="Student showed significant improvement during the term.",
            status="PENDING",
            school=school,
        )

    # ------------------------------------------------------------------
    # Legacy payments app records
    # ------------------------------------------------------------------
    Invoice.objects.create(
        user=data.admin,
        total=1500.0,
        amount=1500.0,
        payment_complete=True,
        invoice_code=f"INV-{academic_year}-0001",
        school=school,
    )
    for level in levels:
        legacy_fee = LegacyFeeStructure.objects.create(
            grade_level=level,
            term=current_term.term,
            year=academic_year,
            tuition_fee=Decimal("500.00"),
            pta_dues=Decimal("50.00"),
            sports_levy=Decimal("30.00"),
            exam_fees=Decimal("40.00"),
            library_fees=Decimal("20.00"),
            development_levy=Decimal("100.00"),
            other_fees=Decimal("0.00"),
            school=school,
        )
        first_student = data.students[level][0]
        LegacyStudentPayment.objects.create(
            student=first_student,
            term=current_term,
            fee_structure=legacy_fee,
            amount_paid=Decimal("740.00"),
            payment_date=today,
            payment_method="Cash",
            reference_number=f"LEGACY-{_level_code(level)}-1",
            receipt_number=f"LEGACY-RCPT-{_level_code(level)}-1",
            received_by=data.admin,
            remarks="Seeded legacy payment",
            school=school,
        )

    return data
