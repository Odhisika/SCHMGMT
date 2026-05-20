from django.test import TestCase

from superadmin.forms import SchoolCreationForm


class SchoolCreationFormTests(TestCase):
    def test_form_does_not_expose_subdomain_and_generates_internal_identifiers(self):
        form = SchoolCreationForm(data={
            "name": "Imperial Academy",
            "email": "admin@imperialacademy.edu.gh",
            "phone": "+233000000000",
            "address": "Accra",
            "website": "https://imperialacademy.edu.gh",
            "custom_domain": "",
            "primary_color": "#007bff",
            "secondary_color": "#6c757d",
            "is_active": "on",
        })

        self.assertNotIn("subdomain", form.fields)
        self.assertTrue(form.is_valid(), form.errors)

        school = form.save()

        self.assertEqual(school.slug, "imperial-academy")
        self.assertEqual(school.subdomain, "imperial-academy")
