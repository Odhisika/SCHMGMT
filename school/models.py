from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.utils import timezone


class School(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text=_("Name of the school"))
    slug = models.SlugField(max_length=200, unique=True, help_text=_("Unique identifier for the school (subdomain/path)"))
    email = models.EmailField(blank=True, null=True)
    logo = models.ImageField(upload_to="school_logos/", blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    # Domain management
    custom_domain = models.URLField(blank=True, null=True, help_text="Custom domain for this school")
    subdomain = models.SlugField(max_length=200, unique=True, help_text="Subdomain for this school")
    
    # Branding
    primary_color = models.CharField(max_length=7, default='#007bff', help_text="Primary theme color")
    secondary_color = models.CharField(max_length=7, default='#6c757d', help_text="Secondary theme color")
    
    # School status
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("School")
        verbose_name_plural = _("Schools")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.subdomain:
            self.subdomain = self.slug
        super().save(*args, **kwargs)
    
    def get_active_users_count(self):
        return self.users.filter(is_active=True).count()
    
    def get_student_count(self):
        return self.users.filter(is_student=True, is_active=True).count()
    
    def get_teacher_count(self):
        return self.users.filter(is_lecturer=True, is_active=True).count()
    
    def get_admin_count(self):
        return self.users.filter(is_school_admin=True, is_active=True).count()
