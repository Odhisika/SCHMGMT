from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Q

from accounts.decorators import lecturer_required, admin_required
from core.models import Term
from .models import LessonNote, Course
from .forms import LessonNoteForm, LessonNoteAdminReviewForm


# ########################################################
# Lesson Note Views - Teacher
# ########################################################


@login_required
@lecturer_required
def lesson_note_list(request):
    """Display all lesson notes for the current teacher"""
    # Filter by teacher
    lesson_notes = LessonNote.objects.filter(teacher=request.user).select_related(
        'course', 'term', 'reviewed_by'
    ).order_by('-created_at')
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        lesson_notes = lesson_notes.filter(status=status_filter)
    
    # Filter by term if provided
    term_filter = request.GET.get('term')
    if term_filter:
        lesson_notes = lesson_notes.filter(term_id=term_filter)
    
    context = {
        'lesson_notes': lesson_notes,
        'terms': Term.objects.all().order_by('-is_current_term', '-term'),
        'status_choices': LessonNote.STATUS_CHOICES,
        'selected_status': status_filter,
        'selected_term': term_filter,
    }
    return render(request, 'course/lesson_note_list.html', context)


@login_required
@lecturer_required
def lesson_note_create(request):
    """Create a new lesson note"""
    if request.method == 'POST':
        form = LessonNoteForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            lesson_note = form.save(commit=False)
            lesson_note.teacher = request.user
            lesson_note.status = 'DRAFT'
            lesson_note.save()
            messages.success(request, f"Lesson note '{lesson_note.title}' has been created as a draft.")
            return redirect('lesson_note_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = LessonNoteForm(user=request.user)
    
    return render(request, 'course/lesson_note_form.html', {
        'form': form,
        'title': 'Create Lesson Note',
        'action': 'Create'
    })


@login_required
@lecturer_required
def lesson_note_edit(request, pk):
    """Edit an existing lesson note (only drafts and rejected ones)"""
    lesson_note = get_object_or_404(LessonNote, pk=pk, teacher=request.user)
    
    # Check if lesson note can be edited
    if not lesson_note.can_edit():
        messages.error(request, "You can only edit lesson notes that are in DRAFT or REJECTED status.")
        return redirect('lesson_note_detail', pk=pk)
    
    if request.method == 'POST':
        form = LessonNoteForm(request.POST, request.FILES, instance=lesson_note, user=request.user)
        if form.is_valid():
            lesson_note = form.save()
            messages.success(request, f"Lesson note '{lesson_note.title}' has been updated.")
            return redirect('lesson_note_detail', pk=pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = LessonNoteForm(instance=lesson_note, user=request.user)
    
    return render(request, 'course/lesson_note_form.html', {
        'form': form,
        'lesson_note': lesson_note,
        'title': 'Edit Lesson Note',
        'action': 'Update'
    })


@login_required
@lecturer_required
def lesson_note_detail(request, pk):
    """View details of a lesson note"""
    lesson_note = get_object_or_404(
        LessonNote.objects.select_related('course', 'term', 'teacher', 'reviewed_by'),
        pk=pk,
        teacher=request.user
    )
    
    return render(request, 'course/lesson_note_detail.html', {
        'lesson_note': lesson_note
    })


@login_required
@lecturer_required
def lesson_note_submit(request, pk):
    """Submit a lesson note for admin review"""
    lesson_note = get_object_or_404(LessonNote, pk=pk, teacher=request.user)
    
    if not lesson_note.can_submit():
        messages.error(request, "This lesson note cannot be submitted.")
        return redirect('lesson_note_detail', pk=pk)
    
    lesson_note.status = 'SUBMITTED'
    lesson_note.submitted_at = timezone.now()
    lesson_note.save()
    
    messages.success(request, f"Lesson note '{lesson_note.title}' has been submitted for review.")
    return redirect('lesson_note_detail', pk=pk)


@login_required
@lecturer_required
def lesson_note_delete(request, pk):
    """Delete a lesson note (only drafts)"""
    lesson_note = get_object_or_404(LessonNote, pk=pk, teacher=request.user)
    
    if lesson_note.status != 'DRAFT':
        messages.error(request, "You can only delete lesson notes that are in DRAFT status.")
        return redirect('lesson_note_detail', pk=pk)
    
    title = lesson_note.title
    lesson_note.delete()
    messages.success(request, f"Lesson note '{title}' has been deleted.")
    return redirect('lesson_note_list')


# ########################################################
# Lesson Note Views - Admin Review
# ########################################################


@login_required
@admin_required
def lesson_note_admin_list(request):
    """Admin view of all lesson notes with filtering"""
    from django.conf import settings
    
    lesson_notes = LessonNote.objects.select_related(
        'course', 'term', 'teacher', 'reviewed_by'
    ).order_by('-created_at')
    
    # Division Filtering (Tabs)
    current_division = request.GET.get('division', settings.DIVISION_NURSERY) # Default to Nursery
    
    # Map levels to divisions for safer filtering
    division_levels_map = {
        settings.DIVISION_NURSERY: [settings.NURSERY_1, settings.NURSERY_2, settings.KG_1, settings.KG_2],
        settings.DIVISION_PRIMARY: [settings.PRIMARY_1, settings.PRIMARY_2, settings.PRIMARY_3, 
                                     settings.PRIMARY_4, settings.PRIMARY_5, settings.PRIMARY_6],
        settings.DIVISION_JHS: [settings.JHS_1, settings.JHS_2, settings.JHS_3],
    }
    
    # Filter by division using levels
    if current_division in division_levels_map:
        target_levels = division_levels_map[current_division]
        lesson_notes = lesson_notes.filter(course__level__in=target_levels)

    # Filter by specific level (Sub-filter)
    level_filter = request.GET.get('level')
    if level_filter:
        lesson_notes = lesson_notes.filter(course__level=level_filter)

    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        lesson_notes = lesson_notes.filter(status=status_filter)
    else:
        # Default to showing pending submissions
        lesson_notes = lesson_notes.filter(status='SUBMITTED')
    
    # Filter by teacher
    teacher_filter = request.GET.get('teacher')
    if teacher_filter:
        lesson_notes = lesson_notes.filter(teacher_id=teacher_filter)
    
    # Filter by term
    term_filter = request.GET.get('term')
    if term_filter:
        lesson_notes = lesson_notes.filter(term_id=term_filter)
    
    # Get unique teachers who have submitted lesson notes
    from accounts.models import User
    teachers = User.objects.filter(
        lesson_notes__isnull=False,
        school=request.school
    ).distinct().order_by('first_name', 'last_name')
    
    # Context data for tabs and filters
    divisions = [
        (settings.DIVISION_NURSERY, "Nursery/Pre-School"),
        (settings.DIVISION_PRIMARY, "Primary School"),
        (settings.DIVISION_JHS, "Junior High School"),
    ]
    
    # Get levels for the current division for the sub-filter dropdown
    current_division_levels = []
    if current_division in division_levels_map:
        # Get tuples of (code, name) for levels in this division
        all_levels = dict(settings.LEVEL_CHOICES)
        for lvl in division_levels_map[current_division]:
            current_division_levels.append((lvl, all_levels.get(lvl, lvl)))
            
    context = {
        'lesson_notes': lesson_notes,
        'teachers': teachers,
        'terms': Term.objects.all().order_by('-is_current_term', '-term'),
        'status_choices': LessonNote.STATUS_CHOICES,
        'selected_status': status_filter,
        'selected_teacher': teacher_filter,
        'selected_term': term_filter,
        'divisions': divisions,
        'current_division': current_division,
        'current_division_levels': current_division_levels,
        'selected_level': level_filter,
    }
    return render(request, 'course/lesson_note_admin_list.html', context)


@login_required
@admin_required
def lesson_note_admin_review(request, pk):
    """Admin review and approve/reject lesson note"""
    lesson_note = get_object_or_404(
        LessonNote.objects.select_related('course', 'term', 'teacher'),
        pk=pk
    )
    
    if request.method == 'POST':
        form = LessonNoteAdminReviewForm(request.POST, instance=lesson_note)
        if form.is_valid():
            lesson_note = form.save(commit=False)
            lesson_note.reviewed_by = request.user
            lesson_note.reviewed_at = timezone.now()
            lesson_note.save()
            
            status_text = lesson_note.get_status_display()
            messages.success(
                request,
                f"Lesson note '{lesson_note.title}' has been marked as {status_text}."
            )
            return redirect('lesson_note_admin_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = LessonNoteAdminReviewForm(instance=lesson_note)
    
    return render(request, 'course/lesson_note_admin_review.html', {
        'form': form,
        'lesson_note': lesson_note
    })
