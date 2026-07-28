import factory
from faker import Faker
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, Polygon
from core.models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile, FloodPrediction, BeneficiaryGroup, MonthlyReport, Milestone

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


class SuperAdminUserFactory(UserFactory):
    class Meta:
        skip_postgeneration_save = True

    @factory.post_generation
    def make_superuser(self, create, extracted, **kwargs):
        if not create:
            return
        self.is_superuser = True
        self.is_staff = True
        self.save(update_fields=['is_superuser', 'is_staff'])
        UserProfile.objects.update_or_create(
            user=self,
            defaults={'role': 'super_admin'}
        )
        self._state.fields_cache.pop('profile', None)


class GovernmentOfficialFactory(UserFactory):
    class Meta:
        skip_postgeneration_save = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        level = kwargs.pop('level', 'national')
        instance = super()._create(model_class, *args, **kwargs)
        instance._govt_level = level
        return instance

    @factory.post_generation
    def add_to_group(self, create, extracted, **kwargs):
        if not create:
            return
        from django.contrib.auth.models import Group
        level = getattr(self, '_govt_level', 'national')
        role = f'govt_{level}'
        group_name = 'GovernmentTeam'
        group, _ = Group.objects.get_or_create(name=group_name)
        self.groups.add(group)
        UserProfile.objects.update_or_create(
            user=self,
            defaults={'role': role}
        )
        self._state.fields_cache.pop('profile', None)


class EmergencyResponderFactory(UserFactory):
    class Meta:
        skip_postgeneration_save = True

    @factory.post_generation
    def add_to_group(self, create, extracted, **kwargs):
        if not create:
            return
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='EmergencyTeam')
        self.groups.add(group)
        UserProfile.objects.update_or_create(
            user=self,
            defaults={'role': 'emergency_responder'}
        )
        self._state.fields_cache.pop('profile', None)


class MeteoOfficerFactory(UserFactory):
    class Meta:
        skip_postgeneration_save = True

    @factory.post_generation
    def add_to_group(self, create, extracted, **kwargs):
        if not create:
            return
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='MeteorologicalTeam')
        self.groups.add(group)
        UserProfile.objects.update_or_create(
            user=self,
            defaults={'role': 'meteo_officer'}
        )
        self._state.fields_cache.pop('profile', None)


class NGOHumanitarianFactory(UserFactory):
    class Meta:
        skip_postgeneration_save = True

    @factory.post_generation
    def add_to_group(self, create, extracted, **kwargs):
        if not create:
            return
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='NGOTeam')
        self.groups.add(group)
        UserProfile.objects.update_or_create(
            user=self,
            defaults={'role': 'ngo_humanitarian'}
        )
        self._state.fields_cache.pop('profile', None)


class ResearcherFactory(UserFactory):
    class Meta:
        skip_postgeneration_save = True

    @factory.post_generation
    def add_to_group(self, create, extracted, **kwargs):
        if not create:
            return
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='ResearchTeam')
        self.groups.add(group)
        UserProfile.objects.update_or_create(
            user=self,
            defaults={'role': 'researcher'}
        )
        self._state.fields_cache.pop('profile', None)


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


class FloodPredictionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FloodPrediction

    zone = factory.SubFactory(AlertZoneFactory)
    target_date = factory.Faker('date')
    risk_score = factory.Faker('pyfloat', min_value=0.0, max_value=1.0)
    water_level_metres = factory.Faker('pyfloat', min_value=0.0, max_value=10.0)
    river_discharge_m3s = factory.Faker('pyfloat', min_value=0.0, max_value=500.0)
    confidence = factory.Faker('pyfloat', min_value=0.0, max_value=1.0)


class BeneficiaryGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BeneficiaryGroup

    name = factory.LazyAttribute(lambda obj: fake.company())
    group_type = factory.Faker('random_element', elements=['community', 'school', 'ngo', 'government', 'business'])
    member_count = factory.Faker('random_int', min=10, max=500)
    location = factory.Faker('city')
    enrolled_date = factory.Faker('date')
    trained = factory.Faker('boolean')
    training_date = factory.Faker('date')
    contact = factory.Faker('phone_number')
    notes = factory.Faker('text')


class MonthlyReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MonthlyReport

    period_start = factory.Faker('date_this_month')
    period_end = factory.Faker('date_this_month')
    alerts_sent = factory.Faker('random_int', min=0, max=100)
    reports_received = factory.Faker('random_int', min=0, max=200)
    reports_verified = factory.Faker('random_int', min=0, max=150)
    high_risk_events = factory.Faker('random_int', min=0, max=50)
    new_users = factory.Faker('random_int', min=0, max=100)
    zones_monitored = factory.Faker('random_int', min=10, max=100)
    uptime_pct = factory.Faker('pyfloat', min_value=90.0, max_value=100.0)
    notes = factory.Faker('text')


class MilestoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Milestone

    title = factory.LazyAttribute(lambda obj: fake.catch_phrase())
    description = factory.Faker('text')
    achieved_date = factory.Faker('date_this_year')
    category = factory.Faker('random_element', elements=['technical', 'community', 'business', 'partnership'])
    evidence_url = factory.Faker('url')
    is_public = factory.Faker('boolean')