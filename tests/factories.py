import factory
from faker import Faker
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, Polygon
from core.models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile

fake = Faker()

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = fake.first_name()
    last_name = fake.last_name()

    @factory.post_generation
    def profile(self, create, extracted, **kwargs):
        if not create:
            return
        UserProfile.objects.get_or_create(
            user=self,
            defaults={'role': kwargs.get('role', 'citizen')}
        )

class AuthorityUserFactory(UserFactory):
    @factory.post_generation
    def add_to_group(self, create, extracted, **kwargs):
        if not create:
            return
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='EmergencyTeam')
        self.groups.add(group)
        UserProfile.objects.get_or_create(
            user=self,
            defaults={'role': 'authority'}
        )

class AlertZoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AlertZone

    name = factory.LazyAttribute(lambda obj: fake.city())
    # Nairobi bbox: lat -1.444 to -1.163, lon 36.650 to 37.103
    # Create a small polygon within bounds
    polygon = factory.LazyFunction(lambda: Polygon([
        (36.8, -1.3), (36.9, -1.3), (36.9, -1.2), (36.8, -1.2), (36.8, -1.3)
    ], srid=4326))
    risk_threshold = factory.Faker('pyfloat', min_value=0.0, max_value=1.0)

class FloodReadingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FloodReading

    location = factory.LazyFunction(lambda: Point(
        fake.pyfloat(min_value=36.650, max_value=37.103),
        fake.pyfloat(min_value=-1.444, max_value=-1.163),
        srid=4326
    ))
    water_level_metres = factory.Faker('pyfloat', min_value=0.0, max_value=10.0)
    risk_score = factory.Faker('pyfloat', min_value=0.0, max_value=1.0)
    source = factory.Faker('word')
    verified = factory.Faker('boolean')

class IncidentReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IncidentReport

    location = factory.LazyFunction(lambda: Point(
        fake.pyfloat(min_value=36.650, max_value=37.103),
        fake.pyfloat(min_value=-1.444, max_value=-1.163),
        srid=4326
    ))
    severity = factory.Faker('random_int', min=1, max=5)
    description = factory.Faker('text')
    status = 'pending'
    submitted_by = factory.SubFactory(UserFactory)

class AlertLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AlertLog

    alert_zone = factory.SubFactory(AlertZoneFactory)
    message = factory.Faker('text')
    channel = factory.Faker('random_element', elements=['SMS', 'Email', 'App Push'])
    recipient_count = factory.Faker('random_int', min=0, max=100)