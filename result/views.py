import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
from django.template.loader import get_template
from django.db import models
from django.db import transaction
from decimal import Decimal, InvalidOperation
from xhtml2pdf import pisa
from core.pdf_utils import link_callback, get_school_document_frame, clean_hex_color

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER, TA_RIGHT

# from reportlab.platypus.tables import Table
from reportlab.lib.units import inch
from reportlab.lib import colors

from core.models import Semester
from course.models import Course
from accounts.models import Student
from accounts.decorators import lecturer_required, student_required, admin_required
from django.utils.translation import gettext as _
from django.db.models import Count
from .models import TakenCourse, Result
from .promotion import apply_promotion, build_candidates
from school.models import GradeWeightConfig


CM = 2.54


def get_next_level(current_level):
    """Helper to determine next class level"""
    levels = [l[0] for l in settings.LEVEL_CHOICES]  # Extract keys
    try:
        index = levels.index(current_level)
        if index + 1 < len(levels):
            return levels[index + 1]
    except ValueError:
        pass
    return None


@login_required
@admin_required
def create_promotion(request):
    """
    Promote students from one class to another based on annual performance.
    Only active during Third Term.
    """
    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()
    is_third_term = current_term and current_term.term == settings.THIRD_TERM

    policy = getattr(request.school, "promotion_policy", None)
    pass_mark = float(policy.promotion_cut_off) if policy else 50.0
    failure_mark = float(policy.failure_cut_off) if policy else 40.0
    
    # Division filtering logic
    DEFAULT_DIV = settings.DIVISION_NURSERY
    current_division = request.GET.get('division', DEFAULT_DIV)
    division_levels_list = settings.DIVISION_LEVEL_MAPPING.get(current_division, [])
    
    # Filter level choices for the dropdown
    division_level_choices = []
    for code, name in settings.LEVEL_CHOICES:
        if code in division_levels_list:
            division_level_choices.append((code, name))

    selected_level = request.GET.get("level") or request.POST.get("level")
    
    # Ensure selected level belongs to current division if coming from tabs
    if selected_level and selected_level not in division_levels_list:
        selected_level = None

    context = {
        "title": _("Promote Students"),
        "current_term": current_term,
        "is_third_term": is_third_term,
        "levels": division_level_choices, # Filtered levels
        "pass_mark": pass_mark,
        "failure_mark": failure_mark,
        "current_division": current_division,
        "divisions": [
            (settings.DIVISION_NURSERY, _("Nursery/Pre-School")),
            (settings.DIVISION_PRIMARY, _("Primary School")),
            (settings.DIVISION_JHS, _("Junior High School")),
        ],
        "selected_level": selected_level,
    }

    if selected_level:
        students = Student.objects.filter(
            level=selected_level, student__school=request.school
        ).order_by("student__last_name")

        promotion_list = build_candidates(
            selected_level,
            current_term.year if current_term else None,
            request.school,
            policy,
        )

        # Handle POST: Execute Promotion
        if request.method == "POST" and is_third_term:
            student_action = request.POST.get("student_action", "")
            if ":" in student_action:
                student_id, action = student_action.rsplit(":", 1)
            else:
                student_id = request.POST.get("student_id")
                action = request.POST.get("action")

            if student_id and action in ("promote", "repeat"):
                candidate = next(
                    (
                        item
                        for item in promotion_list
                        if str(item.student.pk) == str(student_id)
                    ),
                    None,
                )
                if candidate is None:
                    messages.error(request, "That student is no longer in this class list.")
                else:
                    new_status = "MANUAL_PASS" if action == "promote" else "MANUAL_FAIL"
                    if candidate.result is not None:
                        candidate.result.promotion_status = new_status
                        candidate.result.save(
                            update_fields=["promotion_status", "promoted"]
                        )
                    candidate.status = new_status
                    candidate.promoted = action == "promote"
                    summary = apply_promotion([candidate])
                    verb = "promoted" if action == "promote" else "held back"
                    messages.success(
                        request,
                        f"{candidate.student.student.get_full_name()} was {verb}.",
                    )
                return HttpResponseRedirect(
                    reverse_lazy("create_promotion")
                    + f"?division={current_division}&level={selected_level}"
                )

            summary = apply_promotion(promotion_list)
            messages.success(
                request,
                (
                    f"Promotion processed for {selected_level}: "
                    f"{summary['promoted']} promoted, "
                    f"{summary['graduated']} graduated, "
                    f"{summary['held_back']} held back to repeat."
                ),
            )
            return HttpResponseRedirect(
                reverse_lazy("create_promotion")
                + f"?division={current_division}&level={selected_level}"
            )

        context["promotion_list"] = promotion_list
        context["students"] = students # Adding students to context to trigger list view

    return render(request, "result/create_promotion.html", context)

@login_required
@lecturer_required
def add_score(request):
    """
    Legacy score-entry landing page.

    Score entry is now handled by the weighted ``manage_scores`` workflow.
    Keep this route as a permanent redirect so old bookmarks and links do not
    expose the retired 40/60 entry screen.
    """
    return redirect("manage_scores")


@login_required
@lecturer_required
def add_score_for(request, id):
    """
    Shows a page where a teacher will add score for students that
    are taking subjects allocated to him in a specific term.
    Enforces locking if results are published.
    """
    current_term = get_object_or_404(
        Semester, is_current_term=True, school=request.school
    )
    current_session = current_term.year
    course = get_object_or_404(Course, pk=id, school=request.school)
    is_admin = request.user.is_superuser or request.user.is_school_admin

    if not is_admin and not course.allocated_course.filter(
        teacher=request.user, teacher__school=request.school
    ).exists():
        messages.error(request, f"You are not authorized to view scores for {course.title}.")
        return redirect("manage_scores")

    if is_admin and request.method == "POST":
        messages.error(request, "Administrators can view scores but cannot edit them.")
        return redirect("add_score_for", id=id)

    # All normal score entry uses the weighted interface. The legacy page is
    # only retained for the post-publication amendment workflow below.
    if not current_term.result_released:
        return redirect(
            f"{reverse_lazy('enter_scores', kwargs={'level': course.level})}"
            f"?subject={course.pk}"
        )
    
    # Check for Edit Permission
    from .models import ResultEditRequest
    
    # Global Lock
    is_locked = current_term.result_released
    
    # Identify who needs to approve whom
    # Find the teacher allocated to this course
    allocation = course.allocated_course.filter(school=request.school).first()
    allocated_teacher = allocation.teacher if allocation else None
    
    edit_request = None
    if is_locked:
        if request.user.is_superuser or request.user.is_school_admin:
            # Admin is on page: Look for approved request FROM Admin TO Teacher
            edit_request = ResultEditRequest.objects.filter(
                requested_by=request.user,
                teacher=allocated_teacher,
                course=course,
                term=current_term,
                request_type=ResultEditRequest.ADMIN_REQUEST
            ).order_by("-created_at").first()
        else:
            # Teacher is on page: Look for approved request FROM Teacher TO Admin
            edit_request = ResultEditRequest.objects.filter(
                teacher=request.user,
                course=course,
                term=current_term,
                request_type=ResultEditRequest.TEACHER_REQUEST
            ).order_by("-created_at").first()

        if edit_request and edit_request.status == ResultEditRequest.APPROVED:
            is_locked = False

    if request.method == "GET":
        # ... fetch courses and students
        courses = Course.objects.filter(
            allocated_course__teacher__pk=request.user.id,
            school=request.school
        ).filter(term=current_term.term)
        
        # If user is admin but not the lecturer, they might not see 'their' courses here.
        # Let's ensure they see something if they got here via URL.
        if not courses.exists() and (request.user.is_superuser or request.user.is_school_admin):
            courses = Course.objects.filter(school=request.school).filter(term=current_term.term)

        students = (
            TakenCourse.objects.filter(
                school=request.school
            )
            .filter(course__id=id)
            .filter(course__term=current_term.term)
        )
        context = {
            "title": "View Scores" if is_admin else "Submit Score",
            "courses": courses,
            "course": course,
            "students": students,
            "current_session": current_session,
            "current_term": current_term,
            "is_locked": is_locked,
            "can_edit_scores": not is_admin,
            "is_admin": is_admin,
            "edit_request": edit_request,
            "allocated_teacher": allocated_teacher,
            "ResultEditRequest": ResultEditRequest,
        }
        return render(request, "result/add_score_for.html", context)

    if request.method == "POST":
        # Handle Edit Request Submission
        if "request_edit" in request.POST:
            reason = request.POST.get("reason")
            req_type = ResultEditRequest.TEACHER_REQUEST
            if request.user.is_superuser or request.user.is_school_admin:
                req_type = ResultEditRequest.ADMIN_REQUEST
            
            ResultEditRequest.objects.create(
                teacher=allocated_teacher, # Target or Owner
                requested_by=request.user,
                course=course,
                term=current_term,
                reason=reason,
                request_type=req_type,
                school=request.school
            )
            from core.notifications import notify, notify_admins
            from core.models import Notification
            if req_type == ResultEditRequest.TEACHER_REQUEST:
                notify_admins(
                    request.school,
                    title="Result amendment needs review",
                    message=f"{allocated_teacher.get_full_name} requested a result amendment for {course.title}.",
                    link=reverse_lazy("result_amendment_requests"),
                    actor=request.user,
                )
            else:
                notify(
                    school=request.school,
                    recipient=allocated_teacher,
                    title="Admin requested a result amendment",
                    message=f"Please review the result amendment request for {course.title}.",
                    link=reverse_lazy("result_amendment_requests"),
                    actor=request.user,
                )
            messages.info(request, "Request for result amendment has been submitted.")
            return HttpResponseRedirect(reverse_lazy("add_score_for", kwargs={"id": id}))

        # Handle Score Submission
        if is_locked:
            messages.error(request, "Results are published and locked. You must have prior approval to edit.")
            return HttpResponseRedirect(reverse_lazy("add_score_for", kwargs={"id": id}))

        data = request.POST.copy()
        data.pop("csrfmiddlewaretoken", None)
        
        # In the template, we'll have inputs like student_id-class_score and student_id-exam_score
        student_ids = set()
        for key in data.keys():
            if '-' in key:
                student_ids.add(key.split('-')[0])
            else:
                student_ids.add(key)

        for s_id in student_ids:
            try:
                taken_course = TakenCourse.objects.get(id=s_id, school=request.school)
                # Handle both old and new mapping styles
                if f"{s_id}-class_score" in data:
                    class_score = data.get(f"{s_id}-class_score", 0)
                    exam_score = data.get(f"{s_id}-exam_score", 0)
                else:
                    # Fallback for simple list-based POST if template not yet updated
                    scores = data.getlist(s_id)
                    class_score = scores[0] if len(scores) > 0 else 0
                    exam_score = scores[1] if len(scores) > 1 else 0
                
                taken_course.class_score = class_score
                taken_course.exam_score = exam_score
                taken_course.save() # save() calculates total, grade, remark
                
                # Update/Create Term Result
                term_avg = taken_course.calculate_term_average()
                
                res, created = Result.objects.get_or_create(
                    student=taken_course.student,
                    term=current_term.term,
                    session=current_session,
                    level=taken_course.student.level,
                    school=request.school,
                )
                res.term_average = term_avg
                res.save()
            except TakenCourse.DoesNotExist:
                pass
            except Exception as e:
                print(f"Error saving score for {s_id}: {e}")

        messages.success(request, f"Scores for {Course.objects.get(id=id).title} saved successfully!")
        return HttpResponseRedirect(reverse_lazy("add_score_for", kwargs={"id": id}))


@login_required
def result_amendment_requests(request):
    """
    Manage result amendment requests.
    If Admin: see all incoming Teacher requests.
    If Teacher: see all incoming Admin requests (concerns regarding their subjects).
    """
    from .models import ResultEditRequest
    
    if request.method == "POST":
        req_id = request.POST.get("request_id")
        action = request.POST.get("action")
        req = get_object_or_404(ResultEditRequest, pk=req_id, school=request.school)
        
        # Security check: Who can approve?
        # 1. Teacher results -> Admin approves
        # 2. Admin edit -> Teacher approves
        can_process = False
        if req.request_type == ResultEditRequest.TEACHER_REQUEST and (request.user.is_superuser or request.user.is_school_admin):
            can_process = True
        elif req.request_type == ResultEditRequest.ADMIN_REQUEST and request.user == req.teacher:
            can_process = True
            
        if not can_process:
            messages.error(request, "You do not have permission to process this request.")
            return redirect("result_amendment_requests")

        if action == "approve":
            req.status = ResultEditRequest.APPROVED
            req.save()
            from core.models import Notification
            from core.notifications import notify
            notify(
                school=request.school,
                recipient=req.requested_by,
                title="Result amendment approved",
                message=f"The amendment request for {req.course.title} was approved.",
                link=reverse_lazy("result_amendment_requests"),
                notification_type=Notification.TYPE_SUCCESS,
                actor=request.user,
            )
            messages.success(request, f"Approved amendment request.")
        elif action == "reject":
            req.status = ResultEditRequest.REJECTED
            req.save()
            from core.models import Notification
            from core.notifications import notify
            notify(
                school=request.school,
                recipient=req.requested_by,
                title="Result amendment rejected",
                message=f"The amendment request for {req.course.title} was rejected.",
                link=reverse_lazy("result_amendment_requests"),
                notification_type=Notification.TYPE_WARNING,
                actor=request.user,
            )
            messages.info(request, f"Rejected amendment request.")
            
        return redirect("result_amendment_requests")

    # Fetching requests
    if request.user.is_superuser or request.user.is_school_admin:
        # Admin sees incoming teacher requests AND the ones they sent
        requests = ResultEditRequest.objects.filter(school=request.school).order_by("-created_at")
    else:
        # Teacher sees requests targeting them (sent by Admin) OR requests they sent
        requests = ResultEditRequest.objects.filter(
            models.Q(teacher=request.user) | models.Q(requested_by=request.user),
            school=request.school
        ).order_by("-created_at")

    context = {
        "requests": requests,
        "title": "Result Amendments"
    }
    return render(request, "result/requests_list.html", context)
    return HttpResponseRedirect(reverse_lazy("add_score_for", kwargs={"id": id}))


@login_required
@student_required
def grade_result(request):
    student = get_object_or_404(Student, student__pk=request.user.id, student__school=request.school)
    
    # Get all results for this student
    all_results = Result.objects.filter(student=student, school=request.school)
    
    # Filter only released results
    released_results = []
    terms_results = {}
    for res in all_results:
        term_obj = Semester.objects.filter(term=res.term, year=res.session, school=request.school).first()
        if term_obj and term_obj.result_released:
            released_results.append(res)
            terms_results[res.term] = res

    # Filter TakenCourse to match released terms
    courses = TakenCourse.objects.filter(
        student=student, 
        course__term__in=[r.term for r in released_results],
        school=request.school
    )

    context = {
        "courses": courses,
        "results": released_results,
        "terms_results": terms_results,
        "student": student,
    }
    return render(request, "result/grade_results.html", context)


@login_required
@student_required
def assessment_result(request):
    student = get_object_or_404(Student, student__pk=request.user.id, student__school=request.school)
    
    # Similar logic for assessment view - only show if term released
    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    
    if current_term and current_term.result_released:
        courses = TakenCourse.objects.filter(
            student=student, 
            course__term=current_term.term, 
            school=request.school
        )
    else:
        courses = TakenCourse.objects.none()
        messages.info(request, "Results for the current term have not been released yet.")

    context = {
        "courses": courses,
        "student": student,
    }
    return render(request, "result/assessment_results.html", context)


@login_required
@lecturer_required
def result_sheet_pdf_view(request, id):
    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    if not current_term:
        return HttpResponse("No active term found.")
    
    current_session = current_term.year
    result = TakenCourse.objects.filter(course__pk=id)
    course = get_object_or_404(Course, id=id)
    no_of_pass = TakenCourse.objects.filter(course__pk=id, comment="PASS").count()
    no_of_fail = TakenCourse.objects.filter(course__pk=id, comment="FAIL").count()
    fname = (
        str(current_term)
        + "_term_"
        + str(current_session)
        + "_"
        + str(course)
        + "_resultSheet.pdf"
    )
    fname = fname.replace("/", "-")
    flocation = settings.MEDIA_ROOT + "/result_sheet/" + fname

    doc = SimpleDocTemplate(
        flocation,
        rightMargin=0,
        leftMargin=6.5 * CM,
        topMargin=0.3 * CM,
        bottomMargin=0,
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(name="ParagraphTitle", fontSize=11, fontName="FreeSansBold")
    )
    Story = [Spacer(1, 0.2)]
    style = styles["Normal"]

    # picture = request.user.picture
    # l_pic = Image(picture, 1*inch, 1*inch)
    # l_pic.__setattr__("_offs_x", 200)
    # l_pic.__setattr__("_offs_y", -130)
    # Story.append(l_pic)

    # logo = settings.MEDIA_ROOT + "/logo/logo-mini.png"
    # im_logo = Image(logo, 1*inch, 1*inch)
    # im_logo.__setattr__("_offs_x", -218)
    # im_logo.__setattr__("_offs_y", -60)
    # Story.append(im_logo)

    print("\nsettings.MEDIA_ROOT", settings.MEDIA_ROOT)
    print("\nsettings.STATICFILES_DIRS[0]", settings.STATICFILES_DIRS[0])
    logo = settings.STATICFILES_DIRS[0] + "/img/brand.png"
    im = Image(logo, 1 * inch, 1 * inch)
    im.__setattr__("_offs_x", -200)
    im.__setattr__("_offs_y", -45)
    Story.append(im)

    style = getSampleStyleSheet()
    normal = style["Normal"]
    normal.alignment = TA_CENTER
    normal.fontName = "Helvetica"
    normal.fontSize = 12
    normal.leading = 15
    title = (
        "<b> "
        + str(current_term)
        + " Term "
        + str(current_session)
        + " Result Sheet</b>"
    )
    title = Paragraph(title.upper(), normal)
    Story.append(title)
    Story.append(Spacer(1, 0.1 * inch))

    style = getSampleStyleSheet()
    normal = style["Normal"]
    normal.alignment = TA_CENTER
    normal.fontName = "Helvetica"
    normal.fontSize = 10
    normal.leading = 15
    title = "<b>Course lecturer: " + request.user.get_full_name + "</b>"
    title = Paragraph(title.upper(), normal)
    Story.append(title)
    Story.append(Spacer(1, 0.1 * inch))

    normal = style["Normal"]
    normal.alignment = TA_CENTER
    normal.fontName = "Helvetica"
    normal.fontSize = 10
    normal.leading = 15
    level = result.filter(course_id=id).first()
    title = "<b>Level: </b>" + str(level.course.level)
    title = Paragraph(title.upper(), normal)
    Story.append(title)
    Story.append(Spacer(1, 0.6 * inch))

    elements = []
    count = 0
    header = [("S/N", "ID NO.", "FULL NAME", "TOTAL", "GRADE", "POINT", "COMMENT")]

    table_header = Table(header, [inch], [0.5 * inch])
    table_header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.black),
                ("TEXTCOLOR", (1, 0), (-1, -1), colors.white),
                ("TEXTCOLOR", (0, 0), (0, 0), colors.cyan),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    Story.append(table_header)

    for student in result:
        data = [
            (
                count + 1,
                student.student.student.username.upper(),
                Paragraph(
                    student.student.student.get_full_name.capitalize(), styles["Normal"]
                ),
                student.total,
                student.grade,
                student.point,
                student.comment,
            )
        ]
        color = colors.black
        if student.grade == "F":
            color = colors.red
        count += 1

        t_body = Table(data, colWidths=[inch])
        t_body.setStyle(
            TableStyle(
                [
                    ("INNERGRID", (0, 0), (-1, -1), 0.05, colors.black),
                    ("BOX", (0, 0), (-1, -1), 0.1, colors.black),
                ]
            )
        )
        Story.append(t_body)

    Story.append(Spacer(1, 1 * inch))
    style_right = ParagraphStyle(
        name="right", parent=styles["Normal"], alignment=TA_RIGHT
    )
    tbl_data = [
        [
            Paragraph("<b>Date:</b>_____________________________", styles["Normal"]),
            Paragraph("<b>No. of PASS:</b> " + str(no_of_pass), style_right),
        ],
        [
            Paragraph(
                "<b>Siganture / Stamp:</b> _____________________________",
                styles["Normal"],
            ),
            Paragraph("<b>No. of FAIL: </b>" + str(no_of_fail), style_right),
        ],
    ]
    tbl = Table(tbl_data)
    Story.append(tbl)

    doc.build(Story)

    fs = FileSystemStorage(settings.MEDIA_ROOT + "/result_sheet")
    with fs.open(fname) as pdf:
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = "inline; filename=" + fname + ""
        return response
    return response


@login_required
@student_required
def course_registration_form(request):
    courses = TakenCourse.objects.filter(student__student__id=request.user.id)
    fname = request.user.username + ".pdf"
    fname = fname.replace("/", "-")
    # flocation = '/tmp/' + fname
    # print(MEDIA_ROOT + "\\" + fname)
    flocation = settings.MEDIA_ROOT + "/registration_form/" + fname
    doc = SimpleDocTemplate(
        flocation, rightMargin=15, leftMargin=15, topMargin=0, bottomMargin=0
    )
    styles = getSampleStyleSheet()

    Story = [Spacer(1, 0.5)]
    Story.append(Spacer(1, 0.4 * inch))
    style = styles["Normal"]

    style = getSampleStyleSheet()
    normal = style["Normal"]
    normal.alignment = TA_CENTER
    normal.fontName = "Helvetica"
    normal.fontSize = 12
    normal.leading = 18
    title = "<b>EZOD UNIVERSITY OF TECHNOLOGY, ADAMA</b>"  # TODO: Make this dynamic
    title = Paragraph(title.upper(), normal)
    Story.append(title)
    style = getSampleStyleSheet()

    school = style["Normal"]
    school.alignment = TA_CENTER
    school.fontName = "Helvetica"
    school.fontSize = 10
    school.leading = 18
    school_title = (
        "<b>SCHOOL OF ELECTRICAL ENGINEERING & COMPUTING</b>"  # TODO: Make this dynamic
    )
    school_title = Paragraph(school_title.upper(), school)
    Story.append(school_title)

    style = getSampleStyleSheet()
    Story.append(Spacer(1, 0.1 * inch))
    department = style["Normal"]
    department.alignment = TA_CENTER
    department.fontName = "Helvetica"
    department.fontSize = 9
    department.leading = 18
    department_title = (
        "<b>DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING</b>"  # TODO: Make this dynamic
    )
    department_title = Paragraph(department_title, department)
    Story.append(department_title)
    Story.append(Spacer(1, 0.3 * inch))

    title = "<b><u>STUDENT COURSE REGISTRATION FORM</u></b>"
    title = Paragraph(title.upper(), normal)
    Story.append(title)
    student = Student.objects.get(student__pk=request.user.id)

    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    current_session = current_term.year if current_term else ""
    tbl_data = [
        [
            Paragraph(
                "<b>Registration Number : " + request.user.username.upper() + "</b>",
                styles["Normal"],
            )
        ],
        [
            Paragraph(
                "<b>Name : " + request.user.get_full_name.upper() + "</b>",
                styles["Normal"],
            )
        ],
        [
            Paragraph(
                "<b>Session : " + str(current_session).upper() + "</b>",
                styles["Normal"],
            ),
            Paragraph("<b>Level: " + student.level + "</b>", styles["Normal"]),
        ],
    ]
    tbl = Table(tbl_data)
    Story.append(tbl)
    Story.append(Spacer(1, 0.6 * inch))

    style = getSampleStyleSheet()
    semester = style["Normal"]
    semester.alignment = TA_LEFT
    semester.fontName = "Helvetica"
    semester.fontSize = 9
    semester.leading = 18
    semester_title = "<b>FIRST SEMESTER</b>"
    semester_title = Paragraph(semester_title, semester)
    Story.append(semester_title)

    # FIRST SEMESTER
    count = 0
    header = [
        (
            "S/No",
            "Course Code",
            "Course Title",
            "Unit",
            Paragraph("Name, Siganture of course lecturer & Date", style["Normal"]),
        )
    ]
    table_header = Table(header, 1 * [1.4 * inch], 1 * [0.5 * inch])
    table_header.setStyle(
        TableStyle(
            [
                ("ALIGN", (-2, -2), (-2, -2), "CENTER"),
                ("VALIGN", (-2, -2), (-2, -2), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ("ALIGN", (-4, 0), (-4, 0), "LEFT"),
                ("VALIGN", (-4, 0), (-4, 0), "MIDDLE"),
                ("ALIGN", (-3, 0), (-3, 0), "LEFT"),
                ("VALIGN", (-3, 0), (-3, 0), "MIDDLE"),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
            ]
        )
    )
    Story.append(table_header)

    first_semester_unit = 0
    for course in courses:
        if course.course.term == settings.FIRST_TERM:
            # first_semester_unit += int(course.course.credit) # Removed credit field
            data = [
                (
                    count + 1,
                    course.course.code.upper(),
                    Paragraph(course.course.title, style["Normal"]),
                    "N/A",
                    "",
                )
            ]
            count += 1
            table_body = Table(data, 1 * [1.4 * inch], 1 * [0.3 * inch])
            table_body.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (-2, -2), (-2, -2), "CENTER"),
                        ("ALIGN", (1, 0), (1, 0), "CENTER"),
                        ("ALIGN", (0, 0), (0, 0), "CENTER"),
                        ("ALIGN", (-4, 0), (-4, 0), "LEFT"),
                        ("TEXTCOLOR", (0, -1), (-1, -1), colors.black),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
                        ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
                    ]
                )
            )
            Story.append(table_body)

    style = getSampleStyleSheet()
    semester = style["Normal"]
    semester.alignment = TA_LEFT
    semester.fontName = "Helvetica"
    semester.fontSize = 8
    semester.leading = 18
    semester_title = (
        "<b>Total Second First Credit : " + str(first_semester_unit) + "</b>"
    )
    semester_title = Paragraph(semester_title, semester)
    Story.append(semester_title)

    # FIRST SEMESTER ENDS HERE
    Story.append(Spacer(1, 0.6 * inch))

    style = getSampleStyleSheet()
    semester = style["Normal"]
    semester.alignment = TA_LEFT
    semester.fontName = "Helvetica"
    semester.fontSize = 9
    semester.leading = 18
    semester_title = "<b>SECOND SEMESTER</b>"
    semester_title = Paragraph(semester_title, semester)
    Story.append(semester_title)
    # SECOND SEMESTER
    count = 0
    header = [
        (
            "S/No",
            "Course Code",
            "Course Title",
            "Unit",
            Paragraph(
                "<b>Name, Signature of course lecturer & Date</b>", style["Normal"]
            ),
        )
    ]
    table_header = Table(header, 1 * [1.4 * inch], 1 * [0.5 * inch])
    table_header.setStyle(
        TableStyle(
            [
                ("ALIGN", (-2, -2), (-2, -2), "CENTER"),
                ("VALIGN", (-2, -2), (-2, -2), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ("ALIGN", (-4, 0), (-4, 0), "LEFT"),
                ("VALIGN", (-4, 0), (-4, 0), "MIDDLE"),
                ("ALIGN", (-3, 0), (-3, 0), "LEFT"),
                ("VALIGN", (-3, 0), (-3, 0), "MIDDLE"),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
            ]
        )
    )
    Story.append(table_header)

    second_semester_unit = 0
    for course in courses:
        if course.course.term == settings.SECOND_TERM:
            # second_semester_unit += int(course.course.credit) # Removed credit field
            data = [
                (
                    count + 1,
                    course.course.code.upper(),
                    Paragraph(course.course.title, style["Normal"]),
                    "N/A",
                    "",
                )
            ]
            # color = colors.black
            count += 1
            table_body = Table(data, 1 * [1.4 * inch], 1 * [0.3 * inch])
            table_body.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (-2, -2), (-2, -2), "CENTER"),
                        ("ALIGN", (1, 0), (1, 0), "CENTER"),
                        ("ALIGN", (0, 0), (0, 0), "CENTER"),
                        ("ALIGN", (-4, 0), (-4, 0), "LEFT"),
                        ("TEXTCOLOR", (0, -1), (-1, -1), colors.black),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.black),
                        ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
                    ]
                )
            )
            Story.append(table_body)

    style = getSampleStyleSheet()
    semester = style["Normal"]
    semester.alignment = TA_LEFT
    semester.fontName = "Helvetica"
    semester.fontSize = 8
    semester.leading = 18
    semester_title = (
        "<b>Total Second Semester Credit : " + str(second_semester_unit) + "</b>"
    )
    semester_title = Paragraph(semester_title, semester)
    Story.append(semester_title)

    Story.append(Spacer(1, 2))
    style = getSampleStyleSheet()
    certification = style["Normal"]
    certification.alignment = TA_JUSTIFY
    certification.fontName = "Helvetica"
    certification.fontSize = 8
    certification.leading = 18
    student = Student.objects.get(student__pk=request.user.id)
    certification_text = (
        "CERTIFICATION OF REGISTRATION: I certify that <b>"
        + str(request.user.get_full_name.upper())
        + "</b>\
    has been duly registered for the <b>"
        + student.level
        + " level </b> of study in the department\
    of COMPUTER SICENCE & ENGINEERING and that the courses and credits \
    registered are as approved by the senate of the University"
    )
    certification_text = Paragraph(certification_text, certification)
    Story.append(certification_text)

    # FIRST SEMESTER ENDS HERE

    logo = settings.STATICFILES_DIRS[0] + "/img/brand.png"
    im_logo = Image(logo, 1 * inch, 1 * inch)
    setattr(im_logo, "_offs_x", -218)
    setattr(im_logo, "_offs_y", 480)
    Story.append(im_logo)

    picture = settings.BASE_DIR + request.user.get_picture()
    im = Image(picture, 1.0 * inch, 1.0 * inch)
    setattr(im, "_offs_x", 218)
    setattr(im, "_offs_y", 550)
    Story.append(im)

    doc.build(Story)
    fs = FileSystemStorage(settings.MEDIA_ROOT + "/registration_form")
    with fs.open(fname) as pdf:
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = "inline; filename=" + fname + ""
        return response
    return response


@login_required
def report_card_pdf_view(request, pk):
    """
    Generate a full report card for a student in PDF format.
    """
    student = get_object_or_404(Student, pk=pk, student__school=request.school)
    courses = TakenCourse.objects.filter(student=student, school=request.school)
    results = Result.objects.filter(student=student, school=request.school)

    if not results.exists():
        messages.error(request, f"No results found for {student.student.get_full_name}. PDF cannot be generated.")
        return HttpResponseRedirect(reverse_lazy("report_cards"))

    # Process results by term
    terms_results = {}
    for res in results:
        terms_results[res.term] = res

    school = getattr(student.student, "school", None) or getattr(request, "school", None)
    frame_path = get_school_document_frame(school)
    primary_color = clean_hex_color(getattr(school, "primary_color", None), "#0c2340")
    secondary_color = clean_hex_color(getattr(school, "secondary_color", None), "#7cb342")
    accent_color = clean_hex_color(getattr(school, "accent_color", None), "#f59e0b")

    logo_path = None
    if school and getattr(school, "logo", None) and school.logo:
        try:
            if os.path.exists(school.logo.path):
                logo_path = school.logo.path
        except Exception:
            pass

    context = {
        "courses": courses,
        "results": results,
        "terms_results": terms_results,
        "student": student,
        "school": school,
        "title": f"Report Card - {student.student.get_full_name}",
        "request": request,
        "background_image_path": frame_path,
        "logo_path": logo_path,
        "primary_color": primary_color,
        "secondary_color": secondary_color,
        "accent_color": accent_color,
    }

    # Verify if results are published for students/parents
    if request.user.is_student or request.user.is_parent:
        current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
        if not current_term or not current_term.result_released:
             messages.warning(request, "Results for this term have not been published yet.")
             return redirect("home")

    template_path = "result/report_card_pdf.html"
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'filename="report_card_{student.student.username}.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=link_callback)
    if pisa_status.err:
        return HttpResponse(f"We encountered some errors <pre>{html}</pre>")
    
    return response
@login_required
@admin_required
def report_cards(request):
    """
    List all students and their report card status for the school admin.
    """
    from accounts.utils import get_division_for_level
    
    # Get current division and level from request
    DIVISION_NURSERY = settings.DIVISION_NURSERY
    current_division = request.GET.get('division', DIVISION_NURSERY)
    selected_level = request.GET.get('level')
    
    # Base queryset
    students = Student.objects.filter(student__school=request.school)
    
    # Division filtering
    division_levels = settings.DIVISION_LEVEL_MAPPING.get(current_division, [])
    if division_levels:
        students = students.filter(level__in=division_levels)
    
    # Level filtering
    if selected_level:
        students = students.filter(level=selected_level)
    
    students = students.annotate(result_count=Count('result')).order_by('level', 'student__username')
    
    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    
    # Prepare context for tabs and filters
    divisions = [
        (settings.DIVISION_NURSERY, _("Nursery/Pre-School")),
        (settings.DIVISION_PRIMARY, _("Primary School")),
        (settings.DIVISION_JHS, _("Junior High School")),
    ]
    
    # Filter valid levels for the dropdown based on current division
    # settings.LEVEL_CHOICES contains all levels. We filter them.
    division_level_choices = []
    for code, name in settings.LEVEL_CHOICES:
        if code in division_levels:
            division_level_choices.append((code, name))

    context = {
        "students": students,
        "current_term": current_term,
        "title": "Report Cards Management",
        "current_division": current_division,
        "divisions": divisions,
        "selected_level": selected_level,
        "division_levels": division_level_choices,
    }
    return render(request, "result/report_cards_list.html", context)


# ============================================================================
# Teacher Score Entry System
# ============================================================================

_GRADE_COMPONENTS = (
    ("classwork", "Classwork", "classwork_score", "classwork_weight", "use_classwork"),
    ("class_test", "Class Test / Mid-Sem", "midsem_score", "class_test_weight", "use_class_test"),
    ("assignment", "Assignment", "assignment_score", "assignment_weight", "use_assignment"),
    ("attendance", "Attendance", "attendance_score", "attendance_weight", "use_attendance"),
    ("project", "Project / Lab", "project_score", "project_weight", "use_project"),
    ("exam", "Exam", "exam_score", "exam_weight", None),
)

# Components whose marks are entered from the dedicated CA scoresheet rather
# than from the Manage Scores page.
_CA_MANAGED_KEYS = {"classwork", "class_test", "assignment"}

_CA_CATEGORIES = (
    ("class_assignment", "Class Assignment", "class_assignment_score", "assignment"),
    ("homework", "Homework", "homework_score", "assignment"),
    ("class_test", "Class Test", "midsem_score", "class_test"),
    ("class_exercise", "Class Exercises", "classwork_score", "classwork"),
)


def _score_configuration(school):
    """Return the school's active teacher-entry components and config version."""
    config = GradeWeightConfig.objects.filter(school=school).first()
    version = config.updated_at.isoformat() if config else ""

    if config and config.is_valid_config():
        components = [
            {
                "key": key,
                "label": label,
                "field": field,
                "weight": getattr(config, weight_field),
                "weighted": True,
                "ca_managed": key in _CA_MANAGED_KEYS,
            }
            for key, label, field, weight_field, toggle in _GRADE_COMPONENTS
            if toggle is None or getattr(config, toggle)
        ]
        return {"components": components, "version": version, "valid": True}

    # Keep legacy score entry available until a valid grading setup is saved.
    components = [
        {"key": "midsem", "label": "Mid-Sem", "field": "midsem_score", "weight": 100, "weighted": False, "ca_managed": False},
        {"key": "quiz", "label": "Quiz", "field": "quiz_score", "weight": 100, "weighted": False, "ca_managed": False},
        {"key": "assignment", "label": "Assignment", "field": "assignment_score", "weight": 100, "weighted": False, "ca_managed": False},
        {"key": "exam", "label": "Exam", "field": "exam_score", "weight": 100, "weighted": False, "ca_managed": False},
    ]
    return {"components": components, "version": version, "valid": False}


def _score_rows(taken_courses, components):
    rows = []
    for taken_course in taken_courses:
        inputs = []
        for component in components:
            value = getattr(taken_course, component["field"])
            if component["key"] == "class_test" and not value and taken_course.quiz_score:
                value = taken_course.quiz_score
            inputs.append({
                "key": component["key"],
                "label": component["label"],
                "weight": component["weight"],
                "value": value,
                "ca_managed": component.get("ca_managed", False),
            })
        rows.append({"taken_course": taken_course, "inputs": inputs})
    return rows


def _build_ca_configuration(configuration):
    """Expose only the weights needed by the CA scoresheet."""
    components = {component["key"]: component for component in configuration["components"]}

    def component_entry(key, label):
        component = components.get(key)
        return {
            "key": key,
            "label": label,
            "weight": component["weight"] if component else 0,
            "enabled": bool(component),
            "ca_managed": bool(component and component.get("ca_managed")),
        }

    return {
        "valid": configuration["valid"],
        "version": configuration["version"],
        "components": {
            "assignment": component_entry("assignment", "Assignment"),
            "class_test": component_entry("class_test", "Class Test"),
            "classwork": component_entry("classwork", "Classwork"),
            "attendance": component_entry("attendance", "Attendance"),
            "project": component_entry("project", "Project"),
            "exam": component_entry("exam", "Exam"),
        },
    }


def _ca_columns(ca_configuration):
    columns = []
    for key, label, field, component_key in _CA_CATEGORIES:
        component = ca_configuration["components"].get(component_key, {})
        columns.append({
            "key": key,
            "label": label,
            "component": component_key,
            "weight": component.get("weight", 0),
            "enabled": component.get("enabled", False),
            # Class Assignment and Homework share the single Assignment weight.
            "shared": key in {"class_assignment", "homework"},
        })
    return columns


def _ca_rows(taken_courses):
    rows = []
    for taken_course in taken_courses:
        class_test = taken_course.midsem_score or taken_course.quiz_score
        class_assignment = taken_course.class_assignment_score
        if (
            class_assignment is None
            and taken_course.homework_score is None
            and taken_course.assignment_score
        ):
            # Pre-fill legacy rows so saving the CA sheet does not erase an
            # assignment mark that was entered before this feature existed.
            class_assignment = taken_course.assignment_score
        rows.append({
            "taken_course": taken_course,
            "inputs": [
                {
                    "key": "class_assignment",
                    "label": "Class Assignment",
                    "value": class_assignment,
                },
                {
                    "key": "homework",
                    "label": "Homework",
                    "value": taken_course.homework_score,
                },
                {
                    "key": "class_test",
                    "label": "Class Test",
                    "value": class_test,
                },
                {
                    "key": "class_exercise",
                    "label": "Class Exercises",
                    "value": taken_course.classwork_score,
                },
            ],
            "assignment_component": taken_course.get_assignment_component(),
            "attendance": taken_course.attendance_score,
            "project": taken_course.project_score,
            "exam": taken_course.exam_score,
            "ca_score": taken_course.class_score,
            "total": taken_course.total,
        })
    return rows


@login_required
@lecturer_required
def ca_scoresheet(request):
    """
    Continuous-assessment scoresheet for teachers.

    Class Assignment, Homework, Class Test and Class Exercises are entered
    here. The values are written to TakenCourse so the existing weighted
    Manage Scores / report-card calculations use them automatically.
    """
    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()
    is_admin = request.user.is_superuser or request.user.is_school_admin
    divisions = [
        (settings.DIVISION_NURSERY, _("Nursery/Pre-School")),
        (settings.DIVISION_PRIMARY, _("Primary School")),
        (settings.DIVISION_JHS, _("JHS")),
    ]

    if is_admin:
        current_division = request.GET.get("division", settings.DIVISION_NURSERY)
        if current_division not in dict(divisions):
            current_division = settings.DIVISION_NURSERY
        subjects = Course.objects.filter(school=request.school).distinct()
        division_levels = settings.DIVISION_LEVEL_MAPPING.get(current_division, [])
        subjects = subjects.filter(level__in=division_levels)
    else:
        subjects = Course.objects.filter(
            school=request.school,
            allocated_course__teacher=request.user,
        ).distinct()
        current_division = None

    if current_term:
        subjects = subjects.filter(term=current_term.term)

    allocated_levels = list(subjects.values_list("level", flat=True).distinct())
    levels = [level for level in settings.LEVEL_CHOICES if level[0] in allocated_levels]

    selected_level = request.GET.get("level", "")
    subject_id = request.GET.get("subject")
    course = None
    score_rows = []
    ca_configuration = None
    ca_columns = []

    if subject_id:
        course = get_object_or_404(Course, pk=subject_id, school=request.school)

        if current_term and course.term != current_term.term:
            messages.error(request, _("That subject is not part of the current term."))
            return redirect("ca_scoresheet")

        if not is_admin and not course.allocated_course.filter(
            teacher=request.user, teacher__school=request.school
        ).exists():
            messages.error(
                request,
                _("You are not authorized to enter CA scores for this subject."),
            )
            return redirect("ca_scoresheet")

        if is_admin:
            division_levels = settings.DIVISION_LEVEL_MAPPING.get(current_division, [])
            if course.level not in division_levels:
                messages.error(
                    request, _("That subject is outside the selected division.")
                )
                return redirect(f"{reverse_lazy('ca_scoresheet')}?division={current_division}")

        if course.level != selected_level:
            selected_level = course.level

        taken_courses = TakenCourse.objects.filter(
            course=course,
            student__level=course.level,
            school=request.school,
        ).select_related("student", "student__student").order_by(
            "student__student__last_name", "student__student__first_name"
        )
        configuration = _score_configuration(request.school)
        ca_configuration = _build_ca_configuration(configuration)
        ca_columns = _ca_columns(ca_configuration)
        score_rows = _ca_rows(taken_courses)

    context = {
        "course": course,
        "selected_level": selected_level,
        "levels": levels,
        "subjects": subjects,
        "divisions": divisions if is_admin else [],
        "current_division": current_division,
        "is_admin": is_admin,
        "can_edit_scores": not is_admin,
        "score_rows": score_rows,
        "ca_configuration": ca_configuration,
        "ca_columns": ca_columns,
        "current_term": current_term,
        "title": _("CA Scoresheet"),
    }
    return render(request, "result/ca_scoresheet.html", context)


@login_required
@lecturer_required
def save_ca_scores(request):
    """Bulk-save CA marks and recalculate each student's weighted total."""
    import json

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    if request.user.is_superuser or request.user.is_school_admin:
        return JsonResponse({
            "status": "error",
            "message": "Administrators can view CA scores but cannot edit them.",
        }, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid JSON request."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"status": "error", "message": "Invalid CA payload."}, status=400)

    configuration = _score_configuration(request.school)
    if data.get("config_version", "") != configuration["version"]:
        return JsonResponse({
            "status": "error",
            "message": "The grading weights changed. Reload the page and try again.",
            "configuration": configuration,
        }, status=409)

    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()
    if current_term and current_term.result_released:
        return JsonResponse({
            "status": "error",
            "message": "Results for this term have been published. Request an amendment before editing CA marks.",
        }, status=403)

    rows = data.get("rows")
    if not isinstance(rows, list):
        return JsonResponse({"status": "error", "message": "CA rows must be a list."}, status=400)

    allowed_keys = {category[0] for category in _CA_CATEGORIES}
    parsed_rows = []
    errors = []

    for item in rows:
        if not isinstance(item, dict):
            errors.append("A CA row is malformed.")
            continue

        taken_course = TakenCourse.objects.select_related("course").filter(
            pk=item.get("id"), school=request.school
        ).first()
        if not taken_course:
            errors.append(f"Student CA row {item.get('id')} was not found.")
            continue

        if not taken_course.course.allocated_course.filter(
            teacher=request.user, teacher__school=request.school
        ).exists():
            errors.append(
                f"You are not authorized to edit CA marks for {taken_course.course}."
            )
            continue

        if current_term and taken_course.course.term != current_term.term:
            errors.append(
                f"{taken_course.course} is not part of the current term."
            )
            continue

        values = item.get("values")
        if not isinstance(values, dict) or set(values) != allowed_keys:
            errors.append(
                f"The CA fields for {taken_course.student} are out of date. Reload the page."
            )
            continue

        parsed_values = {}
        row_invalid = False
        for key, raw_value in values.items():
            try:
                if raw_value is None or (
                    isinstance(raw_value, str) and raw_value.strip() == ""
                ):
                    value = None
                else:
                    value = Decimal(str(raw_value).strip())
                    if not value.is_finite() or value < 0 or value > 100:
                        raise InvalidOperation
            except (InvalidOperation, ValueError, TypeError):
                errors.append(
                    f"{taken_course.student}: {key} must be between 0 and 100."
                )
                row_invalid = True
                continue
            parsed_values[key] = value

        if not row_invalid:
            parsed_rows.append((taken_course, parsed_values))

    if errors:
        return JsonResponse({
            "status": "error",
            "message": "Please correct the invalid CA marks.",
            "errors": errors,
        }, status=400)

    updated_rows = []
    try:
        with transaction.atomic():
            for taken_course, values in parsed_rows:
                class_assignment = values["class_assignment"]
                homework = values["homework"]
                class_test = values["class_test"] or Decimal("0.00")
                class_exercise = values["class_exercise"] or Decimal("0.00")

                taken_course.class_assignment_score = class_assignment
                taken_course.homework_score = homework
                taken_course.midsem_score = class_test
                taken_course.quiz_score = class_test
                taken_course.classwork_score = class_exercise

                # Compute explicitly so clearing both raw marks does not fall
                # back to a stale legacy assignment value.
                raw_values = [
                    value for value in (class_assignment, homework)
                    if value is not None
                ]
                taken_course.assignment_score = (
                    sum(raw_values, Decimal("0.00")) / Decimal(len(raw_values))
                ).quantize(Decimal("0.01")) if raw_values else Decimal("0.00")
                taken_course.save()
                updated_rows.append({
                    "id": taken_course.pk,
                    "ca_score": float(taken_course.class_score),
                    "total": float(taken_course.total),
                    "grade": taken_course.grade,
                })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "message": f"CA marks could not be saved: {exc}",
        }, status=400)

    return JsonResponse({
        "status": "success",
        "message": f"Successfully saved CA marks for {len(parsed_rows)} students.",
        "updated": updated_rows,
    })


@login_required
@lecturer_required
def manage_scores_dashboard(request):
    """
    Dashboard for teachers to select class and subject for score entry.
    Strictly filters based on teacher's course allocations.
    """
    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()

    # Get subjects taught by teacher (strictly allocated)
    is_admin = request.user.is_superuser or request.user.is_school_admin
    divisions = [
        (settings.DIVISION_NURSERY, _("Nursery/Pre-School")),
        (settings.DIVISION_PRIMARY, _("Primary School")),
        (settings.DIVISION_JHS, _("JHS")),
    ]
    if is_admin:
        # Admins can view courses across the school, narrowed by division.
        current_division = request.GET.get("division", settings.DIVISION_NURSERY)
        if current_division not in dict(divisions):
            current_division = settings.DIVISION_NURSERY
        subjects = Course.objects.filter(school=request.school).distinct()
        division_levels = settings.DIVISION_LEVEL_MAPPING.get(current_division, [])
        subjects = subjects.filter(level__in=division_levels)
    else:
        # Filter strictly by teacher allocation, within this school
        subjects = Course.objects.filter(
            school=request.school,
            allocated_course__teacher=request.user,
        ).distinct()
        current_division = None

    # Courses are term-specific, so the entry screen only concerns the
    # currently active term.
    if current_term:
        subjects = subjects.filter(term=current_term.term)

    # Only offer levels that actually have a subject the user can manage.
    allocated_levels = list(
        subjects.values_list("level", flat=True).distinct()
    )

    # Map levels to settings choices for labels
    levels = [l for l in settings.LEVEL_CHOICES if l[0] in allocated_levels]

    selected_level = ""
    score_configuration = None
    score_sections = []
    if is_admin:
        requested_level = request.GET.get("level", "")
        if requested_level in allocated_levels:
            selected_level = requested_level
            score_configuration = _score_configuration(request.school)
            for course in subjects.filter(level=selected_level).order_by("title"):
                taken_courses = TakenCourse.objects.filter(
                    course=course, school=request.school
                ).select_related("student", "student__student").order_by(
                    "student__student__last_name", "student__student__first_name"
                )
                score_sections.append({
                    "course": course,
                    "rows": _score_rows(taken_courses, score_configuration["components"]),
                })

    context = {
        "levels": levels,
        "subjects": subjects,
        "is_admin": is_admin,
        "divisions": divisions if is_admin else [],
        "current_division": current_division,
        "selected_level": selected_level,
        "score_configuration": score_configuration,
        "score_sections": score_sections,
        "title": "Manage Scores",
    }
    return render(request, "result/manage_scores.html", context)


@login_required
@lecturer_required
def enter_scores(request, level):
    """
    Score entry interface for a specific class.
    Accepts subject_id via GET parameter.
    Verifies that the teacher is authorized to enter scores for this subject.
    """
    subject_id = request.GET.get('subject')
    if not subject_id:
        messages.error(request, "Please select a subject.")
        return HttpResponseRedirect(reverse_lazy('manage_scores'))
        
    course = get_object_or_404(Course, pk=subject_id, school=request.school)

    # The selected subject belongs to one level. Correct a mismatched level
    # instead of showing an empty score table.
    if level != course.level:
        return redirect(
            f"{reverse_lazy('enter_scores', kwargs={'level': course.level})}"
            f"?subject={course.pk}"
        )
    
    # Authorization Check: Ensure teacher is allocated to this course
    is_admin = request.user.is_superuser or request.user.is_school_admin
    if not is_admin:
        # Check if this course is in teacher's allocations
        if not course.allocated_course.filter(
            teacher=request.user, teacher__school=request.school
        ).exists():
            messages.error(request, f"You are not authorized to enter scores for {course.title}.")
            return HttpResponseRedirect(reverse_lazy('manage_scores'))
    
    # Get students enrolled in this course at this level
    taken_courses = TakenCourse.objects.filter(
        course=course,
        student__level=level,
        school=request.school
    ).select_related('student', 'student__student').order_by('student__student__last_name')
    
    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    
    score_configuration = _score_configuration(request.school)
    context = {
        "course": course,
        "level": level,
        "taken_courses": taken_courses,
        "score_rows": _score_rows(taken_courses, score_configuration["components"]),
        "score_configuration": score_configuration,
        "can_edit_scores": not is_admin,
        "is_admin": is_admin,
        "current_term": current_term,
        "title": f"{'View' if is_admin else 'Enter'} Scores - {course.title} ({level})",
    }
    return render(request, "result/enter_scores.html", context)


@login_required
@lecturer_required
def score_weights(request):
    """Small polling endpoint so open teacher pages pick up admin weight edits."""
    return JsonResponse(_score_configuration(request.school))


@login_required
@lecturer_required
def save_scores(request):
    """
    AJAX handler to save scores in bulk.
    """
    import json

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    if request.user.is_superuser or request.user.is_school_admin:
        return JsonResponse({
            "status": "error",
            "message": "Administrators can view scores but cannot edit them.",
        }, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid JSON request."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"status": "error", "message": "Invalid score payload."}, status=400)

    configuration = _score_configuration(request.school)
    if data.get("config_version", "") != configuration["version"]:
        return JsonResponse({
            "status": "error",
            "message": "The grading weights changed. The page is refreshing its weights; try saving again.",
            "configuration": configuration,
        }, status=409)

    scores = data.get("scores")
    if not isinstance(scores, list):
        return JsonResponse({"status": "error", "message": "Scores must be a list."}, status=400)

    components = configuration["components"]
    allowed_keys = {component["key"] for component in components}
    parsed_rows = []
    errors = []
    is_admin = request.user.is_superuser or request.user.is_school_admin

    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()
    if current_term and current_term.result_released and not is_admin:
        return JsonResponse({
            "status": "error",
            "message": "Results for this term have been published. Request an amendment before editing scores.",
        }, status=403)

    for item in scores:
        if not isinstance(item, dict):
            errors.append("A score row is malformed.")
            continue

        tc_id = item.get("id")
        taken_course = TakenCourse.objects.select_related("course").filter(
            pk=tc_id, school=request.school
        ).first()
        if not taken_course:
            errors.append(f"Student score row {tc_id} was not found.")
            continue
        if not taken_course.course.allocated_course.filter(
            teacher=request.user, teacher__school=request.school
        ).exists():
            errors.append(f"You are not authorized to edit scores for {taken_course.course}.")
            continue

        row_values = {}
        row_invalid = False
        submitted = item.get("values", {})
        if not isinstance(submitted, dict) or set(submitted) != allowed_keys:
            errors.append(f"The score fields for {taken_course.student} are out of date. Reload the page.")
            continue

        for key, raw_value in submitted.items():
            try:
                value = Decimal(str(raw_value if raw_value not in (None, "") else "0"))
                if not value.is_finite() or value < 0 or value > 100:
                    raise InvalidOperation
            except (InvalidOperation, ValueError, TypeError):
                errors.append(f"{taken_course.student}: {key} must be between 0 and 100.")
                row_invalid = True
                continue
            row_values[key] = value

        if not row_invalid:
            parsed_rows.append((taken_course, row_values))

    if errors:
        return JsonResponse({"status": "error", "message": "Please correct the invalid scores.", "errors": errors}, status=400)

    try:
        with transaction.atomic():
            for taken_course, row_values in parsed_rows:
                for component in components:
                    key = component["key"]
                    value = row_values[key]
                    if configuration["valid"] and component.get("ca_managed"):
                        # CA marks are owned by the CA scoresheet. Preserve the
                        # stored value even if the browser submitted a change.
                        value = getattr(taken_course, component["field"])
                        if key == "class_test" and not value and taken_course.quiz_score:
                            value = taken_course.quiz_score
                    setattr(taken_course, component["field"], value)
                    if key == "class_test":
                        # Keep the legacy quiz field synchronized with its modern class-test field.
                        taken_course.quiz_score = value
                taken_course.save()
    except Exception as exc:
        return JsonResponse({"status": "error", "message": f"Scores could not be saved: {exc}"}, status=400)

    return JsonResponse({
        "status": "success",
        "message": f"Successfully saved {len(parsed_rows)} student records.",
    })
