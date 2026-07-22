from django.core.management.base import BaseCommand
from core.models import BeneficiaryGroup
from datetime import date

SAMPLE_GROUPS = [
    {'name': 'Kibera Flood Response Team', 'group_type': 'community', 'member_count': 150, 'location': 'Kibera, Nairobi', 'enrolled_date': date(2025, 6, 15), 'trained': True, 'training_date': date(2025, 6, 20)},
    {'name': 'Mathare Emergency Volunteers', 'group_type': 'community', 'member_count': 85, 'location': 'Mathare, Nairobi', 'enrolled_date': date(2025, 6, 20), 'trained': True, 'training_date': date(2025, 6, 25)},
    {'name': 'St. Scholastica Primary School', 'group_type': 'school', 'member_count': 450, 'location': 'South B, Nairobi', 'enrolled_date': date(2025, 7, 1), 'trained': False, 'notes': 'Waiting for training session'},
    {'name': 'Nairobi Red Cross Chapter', 'group_type': 'ngo', 'member_count': 200, 'location': 'Nairobi County', 'enrolled_date': date(2025, 5, 10), 'trained': True, 'training_date': date(2025, 5, 15)},
]

class Command(BaseCommand):
    help = 'Add sample beneficiary groups for impact tracking'

    def handle(self, *args, **options):
        added = 0
        for group in SAMPLE_GROUPS:
            obj, created = BeneficiaryGroup.objects.get_or_create(
                name=group['name'],
                defaults=group
            )
            if created:
                added += 1
                self.stdout.write(f'Added: {group["name"]}')
            else:
                self.stdout.write(f'Exists: {group["name"]}')
        self.stdout.write(self.style.SUCCESS(f'\n{added} new groups added. Total: {BeneficiaryGroup.objects.count()}'))