from django.test import TestCase
from django.urls import reverse

from accounts.models import DepartmentHead, Parent, Student, User
from course.models import Program
from school.models import School


class UserModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Accounts Academy")
        cls.department = Program.objects.create(
            title="Primary Section", school=cls.school, division="Primary"
        )

    def make_user(self, username, **extra):
        extra.setdefault("school", self.school)
        return User.objects.create_user(
            username=username, password="password", **extra
        )

    def test_role_properties(self):
        superuser = User.objects.create_superuser(
            username="root", email="root@example.test", password="password"
        )
        admin = self.make_user("admin", is_school_admin=True)
        teacher = self.make_user(
            "teacher", is_teacher=True, is_lecturer=True, division="Primary"
        )
        class_teacher = self.make_user(
            "class.teacher", is_teacher=True, is_class_teacher=True
        )
        student = self.make_user("student", is_student=True)
        parent = self.make_user("parent", is_parent=True)
        plain = self.make_user("plain")

        self.assertEqual(superuser.get_user_role, "Super Admin")
        self.assertEqual(admin.get_user_role, "School Admin")
        self.assertEqual(teacher.get_user_role, "Teacher")
        self.assertEqual(class_teacher.get_user_role, "Class Teacher")
        self.assertEqual(student.get_user_role, "Student")
        self.assertEqual(parent.get_user_role, "Parent")
        self.assertEqual(plain.get_user_role, "User")

        self.assertTrue(admin.is_school_staff)
        self.assertTrue(teacher.is_school_staff)
        self.assertFalse(parent.is_school_staff)
        self.assertTrue(admin.can_manage_school)
        self.assertFalse(teacher.can_manage_school)

    def test_division_helpers(self):
        teacher = self.make_user(
            "primary.teacher", is_teacher=True, division="Primary"
        )
        unassigned = self.make_user("floating.teacher", is_teacher=True)

        self.assertIn("Primary 1", teacher.get_division_levels())
        self.assertNotIn("JHS 1", teacher.get_division_levels())
        self.assertEqual(unassigned.get_division_levels(), [])

        self.assertTrue(teacher.can_access_level("Primary 1"))
        self.assertFalse(teacher.can_access_level("JHS 1"))
        self.assertFalse(unassigned.can_access_level("Primary 1"))

        admin = self.make_user("admin2", is_school_admin=True)
        self.assertTrue(admin.can_access_level("JHS 3"))

    def test_absolute_url_and_display_helpers(self):
        user = self.make_user(
            "profile.user", first_name="Profile", last_name="User"
        )

        self.assertEqual(
            user.get_absolute_url(),
            reverse("profile_single", kwargs={"user_id": user.pk}),
        )
        self.assertEqual(user.get_full_name, "Profile User")
        self.assertIn("profile.user", str(user))
        self.assertTrue(user.get_picture().endswith("default.png"))

    def test_manager_search(self):
        self.make_user("kwame.search", first_name="Kwame", last_name="Mensah")

        self.assertEqual(User.objects.search("kwame").count(), 1)
        self.assertEqual(User.objects.search("mensah").count(), 1)
        self.assertEqual(User.objects.search("missing").count(), 0)


class StudentAndParentModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Students Academy")
        cls.program = Program.objects.create(
            title="Primary Section", school=cls.school, division="Primary"
        )

    def make_student(self, username="learner", **user_extra):
        user = User.objects.create_user(
            username=username,
            password="password",
            school=self.school,
            is_student=True,
            **user_extra,
        )
        return Student.objects.create(
            student=user, level="Primary 1", program=self.program
        )

    def test_student_string_and_absolute_url(self):
        student = self.make_student(first_name="Ama", last_name="Owusu")

        self.assertEqual(str(student), "Ama Owusu")
        self.assertEqual(
            student.get_absolute_url(),
            reverse("profile_single", kwargs={"user_id": student.student_id}),
        )

    def test_gender_count(self):
        self.make_student("learner.m", gender="M")
        self.make_student("learner.f", gender="F")

        self.assertEqual(Student.get_gender_count(), {"M": 1, "F": 1})

    def test_student_manager_search(self):
        self.make_student("learner.search")

        self.assertEqual(Student.objects.search("Primary").count(), 1)
        self.assertEqual(Student.objects.search("Primary Section").count(), 1)
        self.assertEqual(Student.objects.search("JHS").count(), 0)

    def test_deleting_student_also_deletes_the_user(self):
        student = self.make_student("learner.delete")

        student.delete()

        self.assertFalse(User.objects.filter(username="learner.delete").exists())
        self.assertFalse(Student.objects.filter(pk=student.pk).exists())

    def test_parent_and_department_head_strings(self):
        student = self.make_student("learner.parent")
        parent_user = User.objects.create_user(
            username="parent.user", password="password", school=self.school
        )
        parent = Parent.objects.create(
            user=parent_user,
            student=student,
            first_name="Parent",
            last_name="User",
        )
        head_user = User.objects.create_user(
            username="head.user", password="password", school=self.school
        )
        head = DepartmentHead.objects.create(
            user=head_user, department=self.program
        )

        self.assertEqual(str(parent), "parent.user")
        self.assertEqual(str(head), str(head_user))
