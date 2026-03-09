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

        # Added minutes argument for demo purposes
        parser.add_argument(
            "--minutes",
            type=int,
            default=None,
            help="Delete OTPs older than this many minutes (for demo use)."
        )

    def handle(self, *args, **options):
        days = options["days"]
        minutes = options["minutes"]

        if minutes is not None:
            cutoff = timezone.now() - timedelta(minutes=minutes)
            retention_label = f"{minutes} minute(s)"
        else:
            cutoff = timezone.now() - timedelta(days=days)
            retention_label = f"{days} days"

        qs = OtpVerification.objects.filter(
            created_at__lt=cutoff
        ).filter(
            models.Q(used_at__isnull=False) |
            models.Q(expires_at__lt=timezone.now())
        )

        count = qs.count()
        qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {count} OTP records older than {retention_label}."
        ))