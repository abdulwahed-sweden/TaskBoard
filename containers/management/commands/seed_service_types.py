"""Seed the standard container service types for one or all organizations.

Usage:
    python manage.py seed_service_types --org <slug>
    python manage.py seed_service_types --all
"""

from django.core.management.base import BaseCommand, CommandError

from organizations.models import Organization

from containers.services import seed_service_types


class Command(BaseCommand):
    help = "Seed the standard container service types for one or all organizations."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--org", help="Slug of a single organization to seed.")
        group.add_argument(
            "--all", action="store_true", help="Seed every organization."
        )

    def handle(self, *args, **options):
        if options["all"]:
            organizations = list(Organization.objects.all())
        else:
            slug = options["org"]
            try:
                organizations = [Organization.objects.get(slug=slug)]
            except Organization.DoesNotExist:
                raise CommandError(f"No organization with slug '{slug}'.")

        total = 0
        for organization in organizations:
            created = seed_service_types(organization)
            total += len(created)
            self.stdout.write(
                f"{organization.slug}: created {len(created)} service type(s)."
            )
        self.stdout.write(
            self.style.SUCCESS(f"Done. {total} service type(s) created.")
        )
