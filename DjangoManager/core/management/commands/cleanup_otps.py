from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import models

from core.models import OtpVerification


class Command(BaseCommand):
    help = "Deletes old OTP records that are no longer needed (used or expired) after a retention period."

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

        qs = OtpVerification.objects.filter(
            created_at__lt=cutoff,  # Delete OTPs only older than retention window
        ).filter(
            models.Q(used_at__isnull=False) | models.Q(expires_at__lt=timezone.now())  # Delete OTPs used OR expired
        )

        count = qs.count()
        qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {count} OTP records older than {days} days (used or expired)."
        ))