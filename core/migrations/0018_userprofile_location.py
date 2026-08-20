from django.db import migrations, models
import django.contrib.gis.db.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_add_admin_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='location',
            field=django.contrib.gis.db.models.PointField(blank=True, help_text='Last known location for geo-fenced alerts', null=True, srid=4326),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='location_updated_at',
            field=models.DateTimeField(blank=True, help_text='When location was last updated', null=True),
        ),
    ]