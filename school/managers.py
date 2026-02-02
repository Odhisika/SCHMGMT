from django.db import models
from django.db.models.query import QuerySet


class SchoolAwareQuerySet(QuerySet):
    """QuerySet that automatically filters by school when available"""
    
    def for_school(self, school):
        """Filter queryset for a specific school"""
        return self.filter(school=school)
    
    def active(self):
        """Filter for active records"""
        return self.filter(is_active=True)


class SchoolAwareManager(models.Manager):
    """Manager that provides school-aware querysets"""
    
    def get_queryset(self):
        return SchoolAwareQuerySet(self.model, using=self._db)
    
    def for_school(self, school):
        """Get records for a specific school"""
        return self.get_queryset().for_school(school)
    
    def active(self):
        """Get active records"""
        return self.get_queryset().active()


# Specific managers for different models
class CourseAwareManager(SchoolAwareManager):
    """Manager for Course model with school awareness"""
    pass


class ProgramAwareManager(SchoolAwareManager):
    """Manager for Program model with school awareness"""
    pass


class UserAwareManager(SchoolAwareManager):
    """Manager for User model with school awareness"""
    
    def get_active_students(self, school=None):
        """Get active students for a school"""
        queryset = self.get_queryset().filter(is_student=True, is_active=True)
        if school:
            queryset = queryset.for_school(school)
        return queryset
    
    def get_active_teachers(self, school=None):
        """Get active teachers for a school"""
        queryset = self.get_queryset().filter(is_lecturer=True, is_active=True)
        if school:
            queryset = queryset.for_school(school)
        return queryset
    
    def get_school_admins(self, school=None):
        """Get school administrators"""
        queryset = self.get_queryset().filter(is_school_admin=True, is_active=True)
        if school:
            queryset = queryset.for_school(school)
        return queryset