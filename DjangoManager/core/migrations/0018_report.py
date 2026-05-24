# Generated migration for Report table
# Depends on 0016_analysisresult_recommendation (teammates' migration)
# AnalysisResult is already created in 0016 — this only adds the Report table.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_analysisresult_recommendation'),
    ]

    operations = [
        migrations.CreateModel(
            name='Report',
            fields=[
                ('report_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('report_snapshot', models.JSONField()),
                ('report_s3_key', models.CharField(max_length=255)),
                ('file_size', models.BigIntegerField()),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('result', models.ForeignKey(db_column='result_id', on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='core.analysisresult')),
            ],
            options={
                'db_table': 'reports',
            },
        ),
    ]
