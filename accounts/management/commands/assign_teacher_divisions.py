"""
Management command to assign divisions to existing teachers
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import User


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
            help='Assign all teachers to a specific division (Nursery, Primary, or JHS)'
        )

    def handle(self, *args, **options):
        teachers = User.objects.filter(
            is_teacher=True
        ).select_related('department')
        
        teachers_without_division = teachers.filter(division__isnull=True)
        
        if not teachers_without_division.exists():
            self.stdout.write(
                self.style.SUCCESS('All teachers already have divisions assigned.')
            )
            return

        self.stdout.write(
            f'Found {teachers_without_division.count()} teachers without divisions.'
        )

        if options['division']:
            # Assign all to specific division
            division = options['division']
            valid_divisions = [d[0] for d in settings.DIVISION_CHOICES]
            
            if division not in valid_divisions:
                self.stdout.write(
                    self.style.ERROR(
                        f'Invalid division: {division}. '
                        f'Valid choices are: {", ".join(valid_divisions)}'
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
            # Auto-assign based on department name
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
            # Interactive mode
            self._interactive_assignment(teachers_without_division)

    def _guess_division(self, teacher):
        """Guess division based on teacher's department name"""
        if not teacher.department:
            return None
        
        dept_name = teacher.department.title.lower()
        
        if any(keyword in dept_name for keyword in ['nursery', 'pre-school', 'kg', 'kindergarten']):
            return settings.DIVISION_NURSERY
        elif any(keyword in dept_name for keyword in ['primary']):
            return settings.DIVISION_PRIMARY
        elif any(keyword in dept_name for keyword in ['jhs', 'junior', 'high']):
            return settings.DIVISION_JHS
        
        return None

    def _interactive_assignment(self, teachers):
        """Interactively assign divisions to teachers"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('INTERACTIVE DIVISION ASSIGNMENT')
        self.stdout.write('='*60 + '\n')
        
        divisions = dict(settings.DIVISION_CHOICES)
        division_keys = list(divisions.keys())
        
        for i, teacher in enumerate(teachers, 1):
            self.stdout.write(
                f'\nTeacher {i}/{teachers.count()}: '
                f'{teacher.get_full_name} ({teacher.username})'
            )
            if teacher.department:
                self.stdout.write(f'Department: {teacher.department.title}')
            
            self.stdout.write('\nAvailable divisions:')
            for idx, (key, name) in enumerate(divisions.items(), 1):
                self.stdout.write(f'  {idx}. {name} ({key})')
            self.stdout.write('  0. Skip this teacher')
            
            while True:
                try:
                    choice = input('\nSelect division (0-3): ').strip()
                    choice_int = int(choice)
                    
                    if choice_int == 0:
                        self.stdout.write(
                            self.style.WARNING(f'Skipped {teacher.username}')
                        )
                        break
                    elif 1 <= choice_int <= len(division_keys):
                        selected_division = division_keys[choice_int - 1]
                        teacher.division = selected_division
                        teacher.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Assigned {teacher.username} to {selected_division} division'
                            )
                        )
                        break
                    else:
                        self.stdout.write(
                            self.style.ERROR('Invalid choice, try again')
                        )
                except (ValueError, KeyboardInterrupt):
                    self.stdout.write(
                        self.style.ERROR('\nOperation cancelled')
                    )
                    return
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS('Division assignment complete!')
        )
        self.stdout.write('='*60)
