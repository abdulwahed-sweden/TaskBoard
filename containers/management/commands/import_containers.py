"""Import container-domain data (customers, sites, containers, requests) from a
CSV/XLSX file for one organization.

Usage:
    python manage.py import_containers customers --org acme --file customers.csv
    python manage.py import_containers requests  --org acme --file rq.xlsx --commit

Without --commit the file is validated and a preview summary is printed; nothing
is written.
"""

from django.core.management.base import BaseCommand, CommandError

from organizations.models import Organization

from containers.importer import IMPORTERS, ImportError, parse_upload


class Command(BaseCommand):
    help = "Import customers/sites/containers/requests from a CSV or XLSX file."

    def add_arguments(self, parser):
        parser.add_argument("entity", choices=list(IMPORTERS))
        parser.add_argument("--org", required=True, help="Organization slug.")
        parser.add_argument("--file", required=True, help="Path to a .csv/.xlsx file.")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Write valid rows (default is a dry-run preview).",
        )

    def handle(self, *args, **options):
        try:
            organization = Organization.objects.get(slug=options["org"])
        except Organization.DoesNotExist:
            raise CommandError(f"No organization with slug '{options['org']}'.")

        importer = IMPORTERS[options["entity"]](organization)
        try:
            with open(options["file"], "rb") as fh:
                headers, rows = parse_upload(fh, options["file"])
        except (OSError, ImportError) as exc:
            raise CommandError(str(exc))

        mapping = importer.auto_mapping(headers)

        if not options["commit"]:
            results = importer.preview(rows, mapping)
            valid = sum(1 for r in results if r["valid"])
            self.stdout.write(
                f"Preview: {valid}/{len(results)} row(s) valid (dry run, nothing written)."
            )
            for r in results:
                if not r["valid"]:
                    reason = r["errors"] or {"__all__": "duplicate"}
                    self.stdout.write(f"  row {r['row_number']}: {reason}")
            return

        result = importer.commit(rows, mapping)
        self.stdout.write(self.style.SUCCESS(f"Created {result['created']} row(s)."))
        for skip in result["skipped"]:
            self.stdout.write(f"  skipped row {skip['row_number']}: {skip['errors']}")
