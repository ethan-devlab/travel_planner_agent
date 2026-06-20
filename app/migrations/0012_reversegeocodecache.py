# Generated for persistent, provider-compliant reverse-geocoding results.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0011_migrate_sqlite_ids_to_uuid'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReverseGeocodeCache',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('provider', models.CharField(default='nominatim', max_length=32)),
                ('coordinate_key', models.CharField(max_length=64)),
                ('latitude', models.FloatField()),
                ('longitude', models.FloatField()),
                ('city', models.CharField(blank=True, default='', max_length=150)),
                ('state', models.CharField(blank=True, default='', max_length=150)),
                ('country', models.CharField(blank=True, default='', max_length=150)),
                ('country_code', models.CharField(blank=True, default='', max_length=2)),
                ('display_name', models.TextField(blank=True, default='')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(
                        fields=('provider', 'coordinate_key'),
                        name='unique_reverse_geocode_provider_coordinate',
                    ),
                ],
            },
        ),
    ]
