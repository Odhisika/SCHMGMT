"""
Remove the demo dataset created by ``seed_demo_data``.

Only objects belonging to the demo school (``greenwood-international-school``)
and demo accounts (email domain ``greenwood.test``) are deleted. Real schools
and users are left untouched, so this can be run on a database that already
contains production data.

Usage::

    python manage.py remove_demo_data --dry-run   # show what would be deleted
    python manage.py remove_demo_data             # ask for confirmation
    python manage.py remove_demo_data --no-input  # non-interactive
    python manage.py remove_demo_data --no-input --delete-media
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import Collector

from accounts.models import User
from core.demo_data import DEMO_EMAIL_DOMAIN, DEMO_SCHOOL_SLUG
from school.models import School


class Command(BaseCommand):
    help = "Remove the demo school and demo accounts created by seed_demo_data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without changing anything.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Skip the interactive confirmation prompt.",
        )
        parser.add_argument(
            "--delete-media",
            action="store_true",
            help="Also delete demo files under MEDIA_ROOT (paths containing '/demo/').",
        )

    def _demo_schools(self):
        return School.objects.filter(slug=DEMO_SCHOOL_SLUG)

    def _demo_users(self):
        return User.objects.filter(
            Q(email__iendswith=f"@{DEMO_EMAIL_DOMAIN}")
            & (Q(school__isnull=True) | Q(school__slug=DEMO_SCHOOL_SLUG))
        )

    def _summary(self, schools, users):
        """Count every object that the deletion would remove."""
        counts = {}
        seen = set()
        for queryset in (schools, users):
            objs = list(queryset)
            if not objs:
                continue
            collector = Collector(using="default")
            collector.collect(objs)
            for model, instances in collector.data.items():
                label = model._meta.label
                for obj in instances:
                    key = (label, obj.pk)
                    if key in seen:
                        continue
                    seen.add(key)
                    counts[label] = counts.get(label, 0) + 1
            # Models without delete signal receivers are bulk-deleted and are
            # recorded as querysets on ``fast_deletes`` rather than in ``data``.
            # Iterate their primary keys so overlapping relations and the
            # collector's ``data`` bucket are not double-counted.
            for fast_delete in collector.fast_deletes:
                label = fast_delete.model._meta.label
                for pk in fast_delete.values_list("pk", flat=True):
                    key = (label, pk)
                    if key in seen:
                        continue
                    seen.add(key)
                    counts[label] = counts.get(label, 0) + 1
        return {label: count for label, count in counts.items() if count}

    def _demo_media(self):
        from resources.models import CourseFile, CourseVideo

        files = []
        for model, field_names in (
            (CourseFile, ("file",)),
            (CourseVideo, ("video", "thumbnail")),
        ):
            for obj in model.objects.filter(school__slug=DEMO_SCHOOL_SLUG):
                for field_name in field_names:
                    field = getattr(obj, field_name, None)
                    if field and field.name and "/demo/" in field.name:
                        files.append(field)
        return files

    def _print_summary(self, counts):
        total = sum(counts.values())
        if not total:
            self.stdout.write("  (no objects found)")
            return
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            self.stdout.write(f"  {label:45} {count}")
        self.stdout.write(f"  {'TOTAL':45} {total}")

    def handle(self, *args, **options):
        schools = self._demo_schools()
        users = self._demo_users()

        school_count = schools.count()
        user_count = users.count()
        if not school_count and not user_count:
            self.stdout.write(self.style.SUCCESS("No demo data found."))
            return

        counts = self._summary(schools, users.filter(school__isnull=True))
        media = self._demo_media() if options["delete_media"] else []

        self.stdout.write("The following demo data will be removed:")
        self.stdout.write(
            f"  Demo school(s): {school_count} | demo account(s): {user_count}"
        )
        self._print_summary(counts)
        if options["delete_media"]:
            self.stdout.write(f"  Demo media file(s): {len(media)}")

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing was deleted. Re-run without --dry-run to remove.")
            )
            return

        if not options["no_input"]:
            try:
                answer = input("Type 'remove' to permanently delete this data: ")
            except EOFError:
                raise CommandError("Aborted. Nothing was deleted.")
            if answer.strip().lower() != "remove":
                raise CommandError("Aborted. Nothing was deleted.")

        with transaction.atomic():
            _, school_counts = self._demo_schools().delete()
            _, user_counts = self._demo_users().delete()

        deleted = sum(school_counts.values()) + sum(user_counts.values())
        self.stdout.write(
            self.style.SUCCESS(f"Demo data removed ({deleted} objects deleted).")
        )

        if media:
            media_deleted = 0
            for field in media:
                try:
                    field.storage.delete(field.name)
                    media_deleted += 1
                except Exception as exc:  # noqa: BLE001 - report and continue
                    self.stderr.write(f"Could not delete {field.name}: {exc}")
            self.stdout.write(f"Deleted {media_deleted} demo media file(s).")
