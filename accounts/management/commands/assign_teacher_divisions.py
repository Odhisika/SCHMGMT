"""
Management command to assign divisions to existing teachers.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Q

from accounts.models import User
from school.division_utils import get_division_choices
from school.models import School


class Command(BaseCommand):
    help = 'Assign divisions to existing teachers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto',
            action='store_true',
            help='Automatically assign divisions based on department names'
        )
        parser.add_argument(
            '--division',
            type=str,
            help='Assign all teachers to a specific division (including custom ones)'
        )
        parser.add_argument(
            '--school',
            type=str,
            help='Limit to one school (slug or subdomain).'
        )

    def _get_school(self, value):
        if not value:
            return None
        school = School.objects.filter(slug=value).first() or School.objects.filter(
            subdomain=value
        ).first()
        if not school:
            raise ValueError(f"No school found for {value!r}.")
        return school

    def _available_divisions(self, school):
        """Return division choices for one school, or every known division."""
        if school:
            return list(get_division_choices(school))
        known = {}
        for item in School.objects.all():
            for key, label in get_division_choices(item):
                known.setdefault(key, label)
        if not known:
            return list(settings.DIVISION_CHOICES)
        return list(known.items())

    def handle(self, *args, **options):
        try:
            school = self._get_school(options['school'])
        except ValueError as exc:
            self.stdout.write(self.style.ERROR(str(exc)))
            return

        teachers = User.objects.filter(is_teacher=True).select_related('department', 'school')
        if school:
            teachers = teachers.filter(school=school)

        teachers_without_division = teachers.filter(
            Q(division__isnull=True) | Q(division="")
        )

        if not teachers_without_division.exists():
            self.stdout.write(
                self.style.SUCCESS('All teachers already have divisions assigned.')
            )
            return

        self.stdout.write(
            f'Found {teachers_without_division.count()} teachers without divisions.'
        )

        divisions = self._available_divisions(school)

        if options['division']:
            division = options['division']
            valid_divisions = [d[0] for d in divisions]
            invalid_teachers = [
                teacher
                for teacher in teachers_without_division
                if division not in dict(
                    get_division_choices(getattr(teacher, 'school', None))
                )
            ]

            if invalid_teachers:
                self.stdout.write(
                    self.style.ERROR(
                        f'Division {division!r} is not available for '
                        f'{len(invalid_teachers)} teacher(s). '
                        f'Known divisions are: {", ".join(valid_divisions)}'
                    )
                )
                return

            for teacher in teachers_without_division:
                teacher.division = division
                teacher.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Assigned {teacher.username} ({teacher.get_full_name}) '
                        f'to {division} division'
                    )
                )

        elif options['auto']:
            for teacher in teachers_without_division:
                division = self._guess_division(teacher)
                if division:
                    teacher.division = division
                    teacher.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Auto-assigned {teacher.username} ({teacher.get_full_name}) '
                            f'to {division} division (based on department)'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Could not auto-assign {teacher.username} '
                            f'({teacher.get_full_name}) - please assign manually'
                        )
                    )
        else:
            self._interactive_assignment(
                teachers_without_division, divisions, fixed_school=school
            )

    def _guess_division(self, teacher):
        """Guess division based on the teacher's department/section name."""
        if not teacher.department:
            return None

        dept_name = teacher.department.title.lower()

        # Custom divisions are more specific than the legacy keyword rules.
        built_in_keys = {key for key, _ in settings.DIVISION_CHOICES}
        for key, label in get_division_choices(getattr(teacher, 'school', None)):
            if key in built_in_keys:
                continue
            if key.lower() in dept_name or label.lower() in dept_name:
                return key

        if any(keyword in dept_name for keyword in ['nursery', 'pre-school', 'kg', 'kindergarten']):
            return settings.DIVISION_NURSERY
        elif any(keyword in dept_name for keyword in ['primary']):
            return settings.DIVISION_PRIMARY
        elif any(keyword in dept_name for keyword in ['jhs', 'junior', 'high']):
            return settings.DIVISION_JHS

        return None

    def _interactive_assignment(self, teachers, divisions, fixed_school=None):
        """Interactively assign divisions to teachers"""
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('INTERACTIVE DIVISION ASSIGNMENT')
        self.stdout.write('=' * 60 + '\n')

        total = teachers.count()
        for i, teacher in enumerate(teachers, 1):
            teacher_divisions = (
                divisions
                if fixed_school
                else list(get_division_choices(getattr(teacher, 'school', None)))
            )
            division_keys = [key for key, _ in teacher_divisions]

            self.stdout.write(
                f'\nTeacher {i}/{total}: '
                f'{teacher.get_full_name} ({teacher.username})'
            )
            if teacher.department:
                self.stdout.write(f'Department: {teacher.department.title}')

            self.stdout.write('\nAvailable divisions:')
            for idx, (key, name) in enumerate(teacher_divisions, 1):
                self.stdout.write(f'  {idx}. {name} ({key})')
            self.stdout.write('  0. Skip this teacher')

            while True:
                try:
                    choice = input(f'\nSelect division (0-{len(division_keys)}): ').strip()
                    choice_int = int(choice)
                except ValueError:
                    self.stdout.write(self.style.ERROR('Invalid choice, try again'))
                    continue
                except (KeyboardInterrupt, EOFError):
                    self.stdout.write(self.style.ERROR('\nOperation cancelled'))
                    return

                if choice_int == 0:
                    self.stdout.write(
                        self.style.WARNING(f'Skipped {teacher.username}')
                    )
                    break
                if 1 <= choice_int <= len(division_keys):
                    selected_division = division_keys[choice_int - 1]
                    teacher.division = selected_division
                    teacher.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Assigned {teacher.username} to {selected_division} division'
                        )
                    )
                    break

                self.stdout.write(self.style.ERROR('Invalid choice, try again'))

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(
            self.style.SUCCESS('Division assignment complete!')
        )
        self.stdout.write('=' * 60)
