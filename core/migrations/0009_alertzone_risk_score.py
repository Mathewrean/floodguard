from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_alter_floodreading_risk_score'),
    ]

    operations = [
        migrations.AddField(
            model_name='alertzone',
            name='risk_score',
            field=models.FloatField(
                default=0.0,
                help_text='Current calculated risk score (0.0-1.0)',
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
            ),
        ),
    ]
