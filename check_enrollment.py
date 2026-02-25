#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from course.models import Course
from accounts.models import Student
from result.models import TakenCourse

print("="*60)
print("DIAGNOSTIC: Student Auto-Enrollment Status")
print("="*60)

# Check JHS 1 courses
print("\n[1] JHS 1 Courses:")
jhs_courses = Course.objects.filter(level='JHS 1')
print(f"   Total courses for JHS 1: {jhs_courses.count()}")
for course in jhs_courses[:10]:
    print(f"   - {course.title} ({course.code}) - Term: {course.term}, School: {course.school}")

# Check JHS 1 students  
print("\n[2] JHS 1 Students:")
jhs_students = Student.objects.filter(level='JHS 1')
print(f"   Total students in JHS 1: {jhs_students.count()}")

if jhs_students.count() > 0:
    print("\n   Student Enrollment Details:")
    for student in jhs_students[:5]:
        taken_courses = TakenCourse.objects.filter(student=student)
        print(f"   - {student.student.get_full_name} ({student.student.email})")
        print(f"     Level: {student.level}, Program: {student.program}, School: {student.student.school}")
        print(f"     Enrolled in {taken_courses.count()} courses")
        for tc in taken_courses[:3]:
            print(f"       * {tc.course.title}")

# Check if signals are registered
print("\n[3] Signal Registration Check:")
from django.db.models.signals import post_save
receivers = post_save.receivers
account_student_receivers = [r for r in receivers if 'accounts.Student' in str(r[0])]
print(f"   post_save receivers for accounts.Student: {len(account_student_receivers)}")

print("\n" + "="*60)
print("END OF DIAGNOSTIC")
print("="*60)
