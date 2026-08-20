# Generated for FloodGuard enhancement package

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_userprofile_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='h3cell',
            name='parent_index',
            field=models.CharField(blank=True, help_text='Parent H3 index for hierarchical aggregation', max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='h3cell',
            name='child_h3_indices',
            field=models.JSONField(blank=True, default=list, help_text='Child H3 indices for hierarchical navigation'),
        ),
        migrations.AlterField(
            model_name='h3cell',
            name='resolution',
            field=models.IntegerField(help_text='H3 resolution (0-15)'),
        ),
        migrations.AddIndex(
            model_name='h3cell',
            index=models.Index(fields=['parent_index'], name='core_h3cell_parent__idx'),
        ),
    ]
