# Migration for AlertZoneActivity model
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0012_floodprediction'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlertZoneActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(choices=[('static', 'Static / Predefined'), ('dynamic', 'Dynamic / GPS-derived'), ('user', 'User-created'), ('imported', 'Imported')], default='dynamic', help_text='How this zone was created', max_length=20)),
                ('latitude', models.FloatField(help_text="User's latitude at check-in")),
                ('longitude', models.FloatField(help_text="User's longitude at check-in")),
                ('accuracy_meters', models.FloatField(help_text='GPS accuracy in meters', null=True, blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('zone', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='core.alertzone')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='zone_activities', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['zone', '-created_at'], name='zone_created_idx'), models.Index(fields=['user', '-created_at'], name='user_created_idx'), models.Index(fields=['source'], name='activity_source_idx'), models.Index(fields=['-created_at'], name='activity_created_idx')],
            },
        ),
    ]
