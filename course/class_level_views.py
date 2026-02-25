from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.decorators import lecturer_required


@login_required
@lecturer_required
def class_level_detail(request, level_code):
    """
    Display all subjects/courses for a specific class level.
    Example: All subjects for Primary 1, Nursery 2, JHS 3, etc.
    """
    from django.conf import settings
    from course.models import Course, CourseAllocation
    from accounts.models import User
    
    # Get the display name for this level
    level_name = None
    division = None
    for code, name in settings.LEVEL_CHOICES:
        if code == level_code:
            level_name = name
            break
    
    # Determine division from level code
    if level_code in [settings.NURSERY_1, settings.NURSERY_2, settings.KG_1, settings.KG_2]:
        division = settings.DIVISION_NURSERY
        division_name = "Nursery/Pre-School"
    elif level_code in [settings.PRIMARY_1, settings.PRIMARY_2, settings.PRIMARY_3, 
                         settings.PRIMARY_4, settings.PRIMARY_5, settings.PRIMARY_6]:
        division = settings.DIVISION_PRIMARY
        division_name = "Primary School"
    elif level_code in [settings.JHS_1, settings.JHS_2, settings.JHS_3]:
        division = settings.DIVISION_JHS
        division_name = "Junior High School"
    else:
        division = None
        division_name = "Other"
    
    if not level_name:
        messages.error(request, "Invalid class level.")
        return redirect("programs")
    
    # Get all courses for this level
    courses = Course.objects.filter(
        level=level_code,
        school=request.school
    ).select_related('program').order_by('title')
    
    # Get teacher allocations for these courses
    allocations = CourseAllocation.objects.filter(
        courses__in=courses,
        teacher__school=request.school
    ).select_related('teacher').prefetch_related('courses').distinct()
    
    # Build a mapping of course -> teachers
    course_teachers = {}
    for allocation in allocations:
        for course in allocation.courses.all():
            if course.id not in course_teachers:
                course_teachers[course.id] = []
            if allocation.teacher not in course_teachers[course.id]:
                course_teachers[course.id].append(allocation.teacher)
    
    # Get teachers in this division for assignment
    division_teachers = User.objects.filter(
        is_teacher=True,
        division=division,
        school=request.school
    ).order_by('first_name', 'last_name')
    
    return render(
        request,
        "course/class_level_detail.html",
        {
            "title": f"{level_name} - Subjects",
            "level_code": level_code,
            "level_name": level_name,
            "division": division,
            "division_name": division_name,
            "courses": courses,
            "course_teachers": course_teachers,
            "division_teachers": division_teachers,
        },
    )


@login_required
@lecturer_required
def add_subject_to_level(request, level_code):
    """
    Add a new subject/course to a specific class level.
    Level is pre-filled based on the class selected.
    """
    from django.conf import settings
    from course.forms import CourseAddForm
    
    # Get level name
    level_name = None
    for code, name in settings.LEVEL_CHOICES:
        if code == level_code:
            level_name = name
            break
    
    if not level_name:
        messages.error(request, "Invalid class level.")
        return redirect("programs")
    
    if request.method == "POST":
        form = CourseAddForm(request.POST)
        if form.is_valid():
            # Get or create the appropriate Program for this level's division
            # We assume there is a Program for each division (Nursery, Primary, JHS)
            program_division = None
            if level_code in [settings.NURSERY_1, settings.NURSERY_2, settings.KG_1, settings.KG_2]:
                program_division = settings.DIVISION_NURSERY
            elif level_code in [settings.PRIMARY_1, settings.PRIMARY_2, settings.PRIMARY_3, 
                                 settings.PRIMARY_4, settings.PRIMARY_5, settings.PRIMARY_6]:
                program_division = settings.DIVISION_PRIMARY
            elif level_code in [settings.JHS_1, settings.JHS_2, settings.JHS_3]:
                program_division = settings.DIVISION_JHS
            
            from course.models import Program, Course
            from core.models import Term
            
            # Find the academic block program for this division
            program = Program.objects.filter(
                school=request.school,
                division=program_division,
                is_academic_block=True
            ).first()
            
            # If no specific program found, try to find a generic one or create one
            if not program:
                # Fallback: Create a program for this division if it doesn't exist
                # This ensures the system is robust
                division_title = dict(settings.DIVISION_CHOICES).get(program_division, "General") 
                program, created = Program.objects.get_or_create(
                    school=request.school,
                    division=program_division,
                    is_academic_block=True,
                    defaults={'title': f"{division_title} Section", 'summary': f"Main academic block for {division_title}"}
                )

            # Get current term
            current_term = Term.objects.filter(school=request.school, is_current_term=True).first()
            term_value = current_term.term if current_term else settings.FIRST # Default fallback
            
            # Helper to get short level code
            def get_level_suffix(level):
                if "Nursery" in level: return level.replace("Nursery ", "N")
                if "KG" in level: return level.replace(" ", "")
                if "Primary" in level: return level.replace("Primary ", "P")
                if "JHS" in level: return level.replace("JHS ", "J")
                return level[:3]

            # Get user provided code and strip any existing suffix if they added one by mistake
            base_code = form.cleaned_data.get('code').upper().strip()
            
            # Save the primary course
            course = form.save(commit=False)
            course.level = level_code
            course.school = request.school
            course.program = program
            course.term = term_value
            
            # Append suffix to ensure uniqueness
            suffix = get_level_suffix(level_code)
            if not base_code.endswith(f"-{suffix}"):
                course.code = f"{base_code}-{suffix}"
            
            try:
                course.save()
            except Exception as e:
                # If duplicate despite our best efforts, try to append a random string or just fail gracefully
                messages.error(request, f"Error creating subject: {e}")
                return redirect("class_level_detail", level_code=level_code)
            
            created_count = 1
            
            # Handle Replication
            replicate_to = form.cleaned_data.get('replicate_to')
            if replicate_to:
                for target_level in replicate_to:
                    if target_level == level_code:
                        continue # Skip self if selected
                        
                    # Determine program for target level
                    target_division = None
                    if target_level in [settings.NURSERY_1, settings.NURSERY_2, settings.KG_1, settings.KG_2]:
                        target_division = settings.DIVISION_NURSERY
                    elif target_level in [settings.PRIMARY_1, settings.PRIMARY_2, settings.PRIMARY_3, 
                                           settings.PRIMARY_4, settings.PRIMARY_5, settings.PRIMARY_6]:
                        target_division = settings.DIVISION_PRIMARY
                    elif target_level in [settings.JHS_1, settings.JHS_2, settings.JHS_3]:
                        target_division = settings.DIVISION_JHS
                    
                    # Find separate program for target level
                    target_program = Program.objects.filter(
                        school=request.school,
                        division=target_division,
                        is_academic_block=True
                    ).first()
                    
                    if not target_program:
                         # Fallback for target program
                        div_title = dict(settings.DIVISION_CHOICES).get(target_division, "General") 
                        target_program, _ = Program.objects.get_or_create(
                            school=request.school,
                            division=target_division,
                            is_academic_block=True,
                            defaults={'title': f"{div_title} Section", 'summary': f"Main academic block for {div_title}"}
                        )
                    
                    # Generate unique code for target
                    target_suffix = get_level_suffix(target_level)
                    target_code = f"{base_code}-{target_suffix}"

                    # Create replicated course
                    # Check if it already exists to avoid duplicates
                    exists = Course.objects.filter(
                        code=target_code,
                        school=request.school
                    ).exists()
                    
                    if not exists:
                        Course.objects.create(
                            title=course.title,
                            code=target_code,
                            summary=course.summary,
                            program=target_program,
                            level=target_level,
                            term=term_value,
                            is_core_subject=course.is_core_subject,
                            is_elective=course.is_elective,
                            school=request.school
                        )
                        created_count += 1

            if created_count > 1:
                messages.success(
                    request, f"Subject '{course.title}' added to {level_name} and {created_count-1} other classes."
                )
            else:
                 messages.success(
                    request, f"Subject '{course.title}' added to {level_name}."
                )
            return redirect("class_level_detail", level_code=level_code)
        messages.error(request, "Correct the error(s) below.")
    else:
        # Pre-fill form with level
        form = CourseAddForm(initial={"level": level_code})
    
    return render(
        request,
        "course/add_subject_to_level.html",
        {
            "title": f"Add Subject to {level_name}",
            "form": form,
            "level_code": level_code,
            "level_name": level_name,
        },
    )
