"""
Migration: full analysis_result + finding schema
=================================================
Place as: core/migrations/0017_analysis_finding_schema.py

This REPLACES the existing 0017_report.py in the ordering.
See 0018_report.py for the updated report migration.

Steps:
  1. DELETE core/migrations/0017_report.py
  2. ADD this file as core/migrations/0017_analysis_finding_schema.py
  3. ADD 0018_report.py as core/migrations/0018_report.py
  4. Run: python manage.py migrate
"""

import uuid
import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_analysisresult_recommendation"),
    ]

    operations = [

        # Drop both tables cleanly regardless of current DB state
        migrations.RunSQL("DROP TABLE IF EXISTS finding CASCADE;",         reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL("DROP TABLE IF EXISTS analysis_result CASCADE;", reverse_sql=migrations.RunSQL.noop),

        # Recreate analysis_result to exact spec
        migrations.CreateModel(
            name="AnalysisResult",
            fields=[
                ("result_id",        models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("document",         models.OneToOneField(db_column="document_id", on_delete=django.db.models.deletion.CASCADE, related_name="analysis_result", to="core.document")),
                ("compliance_score", models.IntegerField(default=0)),
                ("risk_level",       models.CharField(choices=[("LOW","Low"),("MEDIUM","Medium"),("HIGH","High")], default="MEDIUM", max_length=10)),
                ("summary",          models.TextField(blank=True, null=True)),
                ("raw_output",       models.JSONField(blank=True, null=True)),
                ("created_at",       models.DateTimeField(default=timezone.now)),
            ],
            options={"db_table": "analysis_result", "ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="analysisresult",
            constraint=models.CheckConstraint(
                check=models.Q(compliance_score__gte=0) & models.Q(compliance_score__lte=100),
                name="compliance_score_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="analysisresult",
            constraint=models.CheckConstraint(
                check=models.Q(risk_level__in=["LOW","MEDIUM","HIGH"]),
                name="risk_level_valid",
            ),
        ),

        # Recreate finding to exact spec
        migrations.CreateModel(
            name="Finding",
            fields=[
                ("finding_id",   models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("result",       models.ForeignKey(db_column="result_id", on_delete=django.db.models.deletion.CASCADE, related_name="findings", to="core.analysisresult")),
                ("finding_type", models.CharField(choices=[("GAP","Gap"),("RISK","Risk")], default="GAP", max_length=10)),
                ("title",        models.CharField(default="", max_length=200)),
                ("description",  models.TextField(default="")),
                ("created_at",   models.DateTimeField(default=timezone.now)),
            ],
            options={"db_table": "finding", "ordering": ["finding_type","title"]},
        ),
        migrations.AddConstraint(
            model_name="finding",
            constraint=models.CheckConstraint(
                check=models.Q(finding_type__in=["GAP","RISK"]),
                name="finding_type_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="finding",
            index=models.Index(fields=["result","finding_type"], name="finding_result_type_idx"),
        ),
    ]