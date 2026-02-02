from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from school.models import School
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = 'Initialize SaaS platform with first school and super admin'

    def add_arguments(self, parser):
        parser.add_argument('--school-name', type=str, default='Demo School', help='Name of the first school')
        parser.add_argument('--subdomain', type=str, default='demo', help='Subdomain for the school')
        parser.add_argument('--admin-username', type=str, default='superadmin', help='Superuser username')
        parser.add_argument('--admin-email', type=str, default='admin@example.com', help='Superuser email')
        parser.add_argument('--admin-password', type=str, default='admin123', help='Superuser password')

    def handle(self, *args, **options):
        school_name = options['school_name']
        subdomain = options['subdomain']
        admin_username = options['admin_username']
        admin_email = options['admin_email']
        admin_password = options['admin_password']

        try:
            with transaction.atomic():
                # Create or get the first school
                school, created = School.objects.get_or_create(
                    subdomain=subdomain,
                    defaults={
                        'name': school_name,
                        'is_active': True,
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f'✓ School "{school.name}" created successfully'))
                else:
                    self.stdout.write(self.style.WARNING(f'⚠ School "{school.name}" already exists'))

                # Create or get superuser
                if User.objects.filter(username=admin_username).exists():
                    self.stdout.write(self.style.WARNING(f'⚠ Superuser "{admin_username}" already exists'))
                else:
                    superuser = User.objects.create_superuser(
                        username=admin_username,
                        email=admin_email,
                        password=admin_password,
                        school=None,  # Superuser doesn't belong to any specific school
                    )
                    self.stdout.write(self.style.SUCCESS(f'✓ Superuser "{admin_username}" created successfully'))

                # Display access information
                self.stdout.write(self.style.SUCCESS('\n' + '='*60))
                self.stdout.write(self.style.SUCCESS('SaaS Platform Initialized Successfully!'))
                self.stdout.write(self.style.SUCCESS('='*60))
                self.stdout.write(f'\n📚 School: {school.name}')
                self.stdout.write(f'🌐 Subdomain: {school.subdomain}')
                self.stdout.write(f'\n👤 Superuser Username: {admin_username}')
                self.stdout.write(f'📧 Superuser Email: {admin_email}')
                self.stdout.write(f'🔑 Superuser Password: {admin_password}')
                self.stdout.write(f'\n🔗 Super Admin Portal: http://127.0.0.1:8000/superadmin/')
                self.stdout.write(self.style.WARNING('\n⚠️  Please change the default password after first login!'))
                self.stdout.write('')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
            raise
