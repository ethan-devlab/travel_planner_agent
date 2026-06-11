from django.core.management.base import BaseCommand

from app.demo import cleanup_expired_demo_sessions


class Command(BaseCommand):
    help = "Delete expired demo users and their temporary data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum number of expired demo sessions to remove.",
        )

    def handle(self, *args, **options):
        deleted_count = cleanup_expired_demo_sessions(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} expired demo session(s)."))
