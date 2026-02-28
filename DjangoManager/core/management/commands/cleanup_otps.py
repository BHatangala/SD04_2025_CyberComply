from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from core.models import OtpVerification


class Command(BaseCommand):
    help = "Deletes old OTP records that are no longer needed (used/closed) after a retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Delete OTPs older than this many days (default: 7)."
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)

        # Only delete OTPs that are already used (closed) and older than cutoff
        qs = OtpVerification.objects.filter(
            used_at__isnull=False,
            created_at__lt=cutoff
        )

        count = qs.count()
        qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {count} OTP records older than {days} days."
        ))