"""Run the annual promotion engine from the command line.

Examples::

    python manage.py promote_students --dry-run
    python manage.py promote_students --division "Primary"
    python manage.py promote_students --level "JHS 3"
    python manage.py promote_students
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Term
from result.promotion import apply_promotion, build_candidates
from school.models import School


class Command(BaseCommand):
    help = "Evaluate annual results and promote (or hold back) students."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            help="School slug or subdomain. Defaults to the only school in the database.",
        )
        parser.add_argument(
            "--session",
            help="Academic session to evaluate. Defaults to the current term's year.",
        )
        parser.add_argument(
            "--division",
            choices=[
                settings.DIVISION_NURSERY,
                settings.DIVISION_PRIMARY,
                settings.DIVISION_JHS,
            ],
            help="Limit promotion to one school division.",
        )
        parser.add_argument(
            "--level",
            help='Limit promotion to one class, e.g. "Primary 1".',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the decision table without changing any student records.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running outside the Third Term.",
        )

    def _get_school(self, value):
        if value:
            school = School.objects.filter(slug=value).first()
            if not school:
                school = School.objects.filter(subdomain=value).first()
            if not school:
                raise CommandError(f"No school found for {value!r}.")
            return school

        schools = School.objects.all()
        if schools.count() == 1:
            return schools.first()
        if schools.count() == 0:
            raise CommandError("No schools exist. Seed demo data first.")
        raise CommandError(
            "More than one school exists. Pass --school <slug> to choose one."
        )

    def _levels(self, division, level):
        if level:
            if level not in [choice[0] for choice in settings.LEVEL_CHOICES]:
                raise CommandError(f"Unknown level {level!r}.")
            return [level]

        if division:
            return settings.DIVISION_LEVEL_MAPPING[division]

        return [choice[0] for choice in settings.LEVEL_CHOICES]

    def handle(self, *args, **options):
        school = self._get_school(options["school"])
        current_term = Term.objects.filter(
            school=school, is_current_term=True
        ).first()

        if current_term is None and not options["session"]:
            raise CommandError(
                "No current term is set. Pass --session <year> explicitly."
            )

        if (
            current_term is not None
            and current_term.term != settings.THIRD_TERM
            and not options["force"]
        ):
            raise CommandError(
                f"Current term is {current_term.term}. Promotion normally runs "
                "in the Third Term. Re-run with --force to override."
            )

        session = options["session"] or current_term.year
        levels = self._levels(options["division"], options["level"])
        dry_run = options["dry_run"]
        policy = getattr(school, "promotion_policy", None)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Promotion evaluation - {school.name} - {session}"
            )
        )
        if policy:
            self.stdout.write(
                f"Policy: pass >= {policy.promotion_cut_off}%, "
                f"fail < {policy.failure_cut_off}%, "
                f"borderline between the two."
            )
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN - no student records will be changed.\n"
                )
            )

        totals = {"promoted": 0, "graduated": 0, "held_back": 0}
        evaluated = 0

        # Build every level's candidate list *before* applying any changes.
        # Otherwise students promoted out of an earlier level appear in the
        # next level's evaluation during the same run, with no results there.
        level_candidates = []
        for level in levels:
            candidates = build_candidates(level, session, school, policy)
            if not candidates:
                continue
            level_candidates.append((level, candidates))
            evaluated += len(candidates)

        for level, candidates in level_candidates:
            self.stdout.write(
                self.style.HTTP_INFO(f"\n{level} ({len(candidates)} students)")
            )
            header = (
                f"{'Student':<28} {'T1':>6} {'T2':>6} {'T3':>6} "
                f"{'Annual':>7} {'Status':<12} Action"
            )
            self.stdout.write(header)
            self.stdout.write("-" * len(header))

            def fmt(value):
                return f"{value:.2f}" if value is not None else "-"

            for candidate in candidates:
                self.stdout.write(
                    f"{str(candidate.student):<28} "
                    f"{fmt(candidate.term1):>6} "
                    f"{fmt(candidate.term2):>6} "
                    f"{fmt(candidate.term3):>6} "
                    f"{candidate.average:>7.2f} "
                    f"{candidate.status:<12} {candidate.action}"
                )

            if not dry_run:
                summary = apply_promotion(candidates)
                for key in totals:
                    totals[key] += summary[key]

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nEvaluated {evaluated} students. "
                    "Re-run without --dry-run to save changes."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Evaluated {evaluated} students: "
                f"{totals['promoted']} promoted, "
                f"{totals['graduated']} graduated, "
                f"{totals['held_back']} held back."
            )
        )
