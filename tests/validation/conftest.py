import pytest
from rest_framework.test import APIClient
from django.test import Client
from tests.factories import (
    SuperAdminUserFactory,
    GovernmentOfficialFactory,
    EmergencyResponderFactory,
    MeteoOfficerFactory,
    NGOHumanitarianFactory,
    UserFactory,
    ResearcherFactory,
    AlertZoneFactory,
    IncidentReportFactory,
    FloodReadingFactory,
    FloodPredictionFactory,
    BeneficiaryGroupFactory,
    MonthlyReportFactory,
    MilestoneFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def web_client():
    return Client()


@pytest.fixture
def super_admin(db):
    user = SuperAdminUserFactory()
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def govt_national(db):
    user = GovernmentOfficialFactory(level='national')
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def govt_county(db):
    user = GovernmentOfficialFactory(level='county')
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def emergency_responder(db):
    user = EmergencyResponderFactory()
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def meteo_officer(db):
    user = MeteoOfficerFactory()
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def ngo_humanitarian(db):
    user = NGOHumanitarianFactory()
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def citizen(db):
    user = UserFactory()
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def researcher(db):
    user = ResearcherFactory()
    user.set_password('password')
    user.save()
    return user


@pytest.fixture
def zone(db):
    return AlertZoneFactory()


@pytest.fixture
def incident(db):
    return IncidentReportFactory()


@pytest.fixture
def prediction(db):
    return FloodPredictionFactory()
