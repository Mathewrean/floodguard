"""
Management command to create initial data for FloodGuard.
Creates user groups, sample zones, and other essential initial data.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, User
from django.contrib.gis.geos import Polygon, Point
from core.models import AlertZone, IncidentReport, UserProfile
from django.utils import timezone


class Command(BaseCommand):
    help = 'Create initial demo data for FloodGuard development and testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of demo data (deletes existing)',
        )

    def handle(self, *args, **options):
        force = options['force']
        
        if force:
            self.stdout.write(self.style.WARNING('Deleting existing demo data...'))
            AlertZone.objects.all().delete()
            IncidentReport.objects.all().delete()
            # Keep users but remove profiles
            UserProfile.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS('Creating initial data...'))
        
        # Create groups
        citizen_group, _ = Group.objects.get_or_create(name='Citizen')
        authority_group, _ = Group.objects.get_or_create(name='EmergencyTeam')
        
        # Create demo users
        demo_citizen, created = User.objects.get_or_create(
            username='citizen',
            defaults={
                'email': 'citizen@example.com',
                'is_staff': False,
                'is_superuser': False,
            }
        )
        if created:
            demo_citizen.set_password('citizen123')
            demo_citizen.save()
            demo_citizen.profile.role = 'citizen'
            demo_citizen.profile.phone_number = '+254700000001'
            demo_citizen.profile.save()
            self.stdout.write(f'  Created citizen user: citizen / citizen123')
        
        demo_authority, created = User.objects.get_or_create(
            username='authority',
            defaults={
                'email': 'authority@example.com',
                'is_staff': False,
                'is_superuser': False,
            }
        )
        if created:
            demo_authority.set_password('authority123')
            demo_authority.save()
            demo_authority.profile.role = 'authority'
            demo_authority.profile.phone_number = '+254700000002'
            demo_authority.profile.save()
            demo_authority.groups.add(authority_group)
            self.stdout.write(f'  Created authority user: authority / authority123')
        
        demo_admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            demo_admin.set_password('admin123')
            demo_admin.save()
            demo_admin.profile.role = 'admin'
            demo_admin.profile.phone_number = '+254700000000'
            demo_admin.profile.save()
            self.stdout.write(f'  Created admin user: admin / admin123')
        
        # Create sample flood zones around Nairobi
        zones_data = [
            {
                'name': 'Nairobi CBD',
                'polygon': Polygon.from_bbox((
                    36.8150, -1.2950, 36.8350, -1.2750
                )),
                'risk_threshold': 0.6,
            },
            {
                'name': 'Kibera Settlement',
                'polygon': Polygon.from_bbox((
                    36.7150, -1.3150, 36.7450, -1.2950
                )),
                'risk_threshold': 0.55,
            },
            {
                'name': 'Mathare Valley',
                'polygon': Polygon.from_bbox((
                    36.8450, -1.2550, 36.8750, -1.2350
                )),
                'risk_threshold': 0.5,
            },
            {
                'name': 'Dandora Estate',
                'polygon': Polygon.from_bbox((
                    36.8650, -1.2650, 36.8950, -1.2450
                )),
                'risk_threshold': 0.65,
            },
            {
                'name': 'Mukuru kwa Njenga',
                'polygon': Polygon.from_bbox((
                    36.8250, -1.2850, 36.8550, -1.2650
                )),
                'risk_threshold': 0.6,
            },
        ]
        
        zones_created = 0
        for zone_data in zones_data:
            zone, created = AlertZone.objects.get_or_create(
                name=zone_data['name'],
                defaults={
                    'polygon': zone_data['polygon'],
                    'risk_threshold': zone_data['risk_threshold'],
                    'risk_score': 0.0,
                }
            )
            if created:
                zones_created += 1
                self.stdout.write(f'  Created zone: {zone.name}')
        
        self.stdout.write(self.style.SUCCESS(
            f'Demo data setup complete. {zones_created} zones created.'
        ))
        self.stdout.write('\nLogin credentials:')
        self.stdout.write('  Citizen:  citizen / citizen123')
        self.stdout.write('  Authority: authority / authority123')
        self.stdout.write('  Admin:     admin / admin123')
