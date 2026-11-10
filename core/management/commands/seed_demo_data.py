"""
Seed the database with a realistic, deterministic demo school.

Usage::

    python manage.py seed_demo_data                 # add demo data
    python manage.py seed_demo_data --flush         # wipe ALL data first
    python manage.py seed_demo_data --students 5    # more students per class
    python manage.py seed_demo_data --levels "Primary 1,Primary 2,JHS 1"

The command is safe to re-run without ``--flush`` for schools/records that are
already present, but a clean database produces the most predictable result.

``--flush`` is destructive and is blocked unless the database looks like a
demo-only development database. On a production-like database (``DEBUG=False``)
set ``SEED_ALLOW_FLUSH=1`` or pass ``--force``. ``--force`` is also required
when any non-demo school or user account exists.
"""

import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts.models import User
from core.demo_data import (
    DEMO_EMAIL_DOMAIN,
    DEMO_PASSWORD,
    DEMO_SCHOOL_SLUG,
    build_demo_data,
)
from school.models import School

FLUSH_ENV_VAR = "SEED_ALLOW_FLUSH"


def _env_flag(name):
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = "Seed a complete demo school dataset for testing and demos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete ALL existing data before seeding (destructive).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Allow --flush on a production-like database or when non-demo "
                "data exists. Use with extreme care."
            ),
        )
        parser.add_argument(
            "--students",
            type=int,
            default=3,
            help="Number of students to create per class/level (default: 3).",
        )
        parser.add_argument(
            "--attendance-days",
            type=int,
            default=10,
            help="Number of school days of attendance to generate (default: 10).",
        )
        parser.add_argument(
            "--levels",
            type=str,
            default="",
            help='Comma-separated levels, e.g. "Primary 1,JHS 1". Defaults to every level.',
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed for deterministic generation (default: 42).",
        )
        parser.add_argument(
            "--no-timetable",
            action="store_true",
            help="Skip generating timetable entries.",
        )
        parser.add_argument(
            "--no-resources",
            action="store_true",
            help="Skip generating learning resources.",
        )

    def _flush_blockers(self):
        """Return human-readable reasons why ``--flush`` should be refused."""
        blockers = []

        if not settings.DEBUG and not _env_flag(FLUSH_ENV_VAR):
            blockers.append(
                "DEBUG=False, so this looks like a production database. "
                f"Set {FLUSH_ENV_VAR}=1 or pass --force only if you are certain "
                "it contains no real data."
            )

        real_schools = School.objects.exclude(slug=DEMO_SCHOOL_SLUG)
        if real_schools.exists():
            names = list(real_schools.order_by("name").values_list("name", flat=True)[:5])
            extra = "" if real_schools.count() <= 5 else f" (+{real_schools.count() - 5} more)"
            blockers.append(
                f"{real_schools.count()} non-demo school(s) exist: "
                f"{', '.join(names)}{extra}. Run 'python manage.py "
                "remove_demo_data' instead of flushing."
            )

        real_users = User.objects.exclude(
            Q(email__iendswith=f"@{DEMO_EMAIL_DOMAIN}")
            | Q(school__isnull=False, school__slug=DEMO_SCHOOL_SLUG)
        )
        if real_users.exists():
            blockers.append(
                f"{real_users.count()} non-demo user account(s) exist. "
                "Flushing would delete them."
            )

        return blockers

    def handle(self, *args, **options):
        if options["flush"]:
            blockers = [] if options["force"] else self._flush_blockers()
            if blockers:
                raise CommandError(
                    "--flush refused for safety:\n  - " + "\n  - ".join(blockers)
                )

            self.stdout.write(self.style.WARNING("Flushing the entire database..."))
            call_command("flush", interactive=False, verbosity=0)
        elif School.objects.filter(slug=DEMO_SCHOOL_SLUG).exists():
            self.stderr.write(
                self.style.ERROR(
                    "Demo data already exists. Re-run with --flush to recreate it "
                    "(WARNING: this deletes all existing data)."
                )
            )
            return

        levels = [level.strip() for level in options["levels"].split(",") if level.strip()]
        if not levels:
            levels = None

        self.stdout.write("Seeding demo data...")
        data = build_demo_data(
            levels=levels,
            students_per_level=options["students"],
            attendance_days=options["attendance_days"],
            timetable=not options["no_timetable"],
            quizzes=True,
            resources=not options["no_resources"],
            seed=options["seed"],
        )

        self.stdout.write(self.style.SUCCESS("\nDemo data created successfully."))
        self.stdout.write("")
        self.stdout.write(f"  School:    {data.school.name} ({data.school.subdomain})")
        self.stdout.write(f"  License:   {data.school.slug}")
        self.stdout.write(f"  Term:      {data.current_term}")
        self.stdout.write(f"  Levels:    {len(data.courses)}")
        self.stdout.write(f"  Courses:   {sum(len(v) for v in data.courses.values())}")
        self.stdout.write(f"  Students:  {sum(len(v) for v in data.students.values())}")
        self.stdout.write(f"  Results:   {len(data.results)}")
        self.stdout.write(f"  Quizzes:   {len(data.quizzes)}")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Login credentials"))
        self.stdout.write(f"  Superuser:    root / {DEMO_PASSWORD}")
        self.stdout.write(f"  School admin: admin / {DEMO_PASSWORD}")
        self.stdout.write(f"  Teacher:      teacher.primary / {DEMO_PASSWORD}")
        self.stdout.write(f"  Class teacher:class.teacher / {DEMO_PASSWORD}")
        first_level_code = next(iter(data.students))
        first_student = data.students[first_level_code][0].student
        self.stdout.write(f"  Student:      {first_student.username} / {DEMO_PASSWORD}")
        first_parent_level = next(iter(data.parents))
        parent_user = data.parents[first_parent_level].user
        self.stdout.write(f"  Parent:       {parent_user.username} / {DEMO_PASSWORD}")
        self.stdout.write("")
        self.stdout.write(
            self.style.HTTP_INFO(
                "Tip: log in with an admin account, then visit /en/ for the school portal "
                "or /superadmin/ as the superuser."
            )
        )
