# Generated for isolated demo-mode sessions.

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0011_migrate_sqlite_ids_to_uuid'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DemoSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(default='demo_user', max_length=32)),
                ('permissions', models.CharField(default='limited', max_length=32)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('ai_request_count', models.PositiveIntegerField(default=0)),
                ('minute_window_started_at', models.DateTimeField(blank=True, null=True)),
                ('minute_request_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='demo_session', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
