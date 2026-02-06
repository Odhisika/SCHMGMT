from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
from django.template.loader import get_template
from django.db import models
from xhtml2pdf import pisa

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

    pass_mark = 50.0  # Pass mark percentage

    context = {
        "title": "Promote Students",
        "current_term": current_term,
        "is_third_term": is_third_term,
        "levels": settings.LEVEL_CHOICES,
        "pass_mark": pass_mark,
    }

    selected_level = request.GET.get("level") or request.POST.get("level")
    context["selected_level"] = selected_level

    if selected_level:
        students = Student.objects.filter(
            level=selected_level, student__school=request.school
        ).order_by("student__last_name")

        promotion_list = []

        for student in students:
            # Fetch results for the current academic session
            results = Result.objects.filter(
                student=student,
                session=current_term.year,
                level=selected_level,
                school=request.school,
            )

            t1 = results.filter(term=settings.FIRST_TERM).first()
            t2 = results.filter(term=settings.SECOND_TERM).first()
            t3 = results.filter(term=settings.THIRD_TERM).first()

            score1 = float(t1.term_average) if t1 and t1.term_average else 0
            score2 = float(t2.term_average) if t2 and t2.term_average else 0
            score3 = float(t3.term_average) if t3 and t3.term_average else 0

            # Determine divisor based on available results?
            # Ideally annual avg is sum / 3. If a term is missing, it counts as 0.
            annual_avg = round((score1 + score2 + score3) / 3, 2)

            next_lvl = get_next_level(selected_level)

            item = {
                "student": student,
                "term1": score1,
                "term2": score2,
                "term3": score3,
                "average": annual_avg,
                "next_level": next_lvl,
                "is_graduating": next_lvl is None,
                "promoted": False,
            }

            # Logic for Promotion
            if annual_avg >= pass_mark:
                item["promoted"] = True

            promotion_list.append(item)

        # Handle POST: Execute Promotion
        if request.method == "POST" and is_third_term:
            promote_count = 0
            for item in promotion_list:
                if item["promoted"]:
                    student = item["student"]
                    if item["next_level"]:
                        student.level = item["next_level"]
                        student.save()
                        promote_count += 1
                        # Create a record or log if necessary
                    elif item["is_graduating"]:
                        # Logic for graduation
                        # Maybe status=Alumni? For now, we'll just log it
                        pass

            messages.success(
                request,
                f"Successfully promoted {promote_count} students from {selected_level}.",
            )
            return HttpResponseRedirect(reverse_lazy("create_promotion"))

        context["promotion_list"] = promotion_list

    return render(request, "result/create_promotion.html", context)

@login_required
@lecturer_required
def add_score(request):
    """
    Shows a page where a teacher will select a subject allocated
    to him for score entry in a specific term
    """
    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()

    if not current_term:
        messages.error(request, "No active term found.")
        return render(request, "result/add_score.html")

    current_session = current_term.year
    courses = Course.objects.filter(
        allocated_course__teacher__pk=request.user.id,
        school=request.school
    ).filter(term=current_term.term)
    context = {
        "current_session": current_session,
        "current_term": current_term,
        "courses": courses,
    }
    return render(request, "result/add_score.html", context)


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
            "title": "Submit Score",
            "courses": courses,
            "course": course,
            "students": students,
            "current_session": current_session,
            "current_term": current_term,
            "is_locked": is_locked,
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
            messages.success(request, f"Approved amendment request.")
        elif action == "reject":
            req.status = ResultEditRequest.REJECTED
            req.save()
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

    context = {
        "courses": courses,
        "results": results,
        "terms_results": terms_results,
        "student": student,
        "title": f"Report Card - {student.student.get_full_name}",
        "request": request,
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
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"We encountered some errors <pre>{html}</pre>")
    
    return response
@login_required
@admin_required
def report_cards(request):
    """
    List all students and their report card status for the school admin.
    """
    students = Student.objects.filter(student__school=request.school).annotate(result_count=Count('result'))
    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    
    context = {
        "students": students,
        "current_term": current_term,
        "title": "Report Cards Management",
    }
    return render(request, "result/report_cards_list.html", context)
