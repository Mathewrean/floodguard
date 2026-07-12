import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.gis.geos import Point
from rest_framework.exceptions import ValidationError
from core.serializers import IncidentReportSerializer, FloodReadingSerializer
from tests.factories import UserFactory, FloodReadingFactory


class TestIncidentReportSerializer:
    @pytest.mark.django_db
    def test_rejects_out_of_bounds_coordinates(self, settings):
        settings.DEFAULT_GEO_BOUNDS = [33.0, -5.0, 42.0, 5.0]
        user = UserFactory()
        data = {
            'location': Point(30.0, 0.0, srid=4326),  # Outside bounds
            'severity': 3,
            'description': 'Test',
            'submitted_by': user.id
        }
        serializer = IncidentReportSerializer(data=data)
        with pytest.raises(ValidationError, match="Location outside supported area"):
            serializer.is_valid(raise_exception=True)

    @pytest.mark.django_db
    def test_accepts_valid_coordinates(self):
        user = UserFactory()
        data = {
            'location': Point(36.8, -1.3, srid=4326),  # Inside Nairobi
            'severity': 3,
            'description': 'Test',
            'submitted_by': user.id
        }
        serializer = IncidentReportSerializer(data=data)
        assert serializer.is_valid()

    @pytest.mark.django_db
    def test_rejects_non_image_file(self):
        user = UserFactory()
        fake_file = SimpleUploadedFile("test.txt", b"not an image", content_type="text/plain")
        data = {
            'location': Point(36.8, -1.3, srid=4326),
            'severity': 3,
            'description': 'Test',
            'photo': fake_file,
            'submitted_by': user.id
        }
        serializer = IncidentReportSerializer(data=data)
        with pytest.raises(ValidationError):
            serializer.is_valid(raise_exception=True)

    @pytest.mark.django_db
    def test_accepts_image_file(self):
        user = UserFactory()
        # Create a fake JPEG
        fake_jpeg = SimpleUploadedFile("test.jpg", b"fake jpeg data", content_type="image/jpeg")
        data = {
            'location': Point(36.8, -1.3, srid=4326),
            'severity': 3,
            'description': 'Test',
            'photo': fake_jpeg,
            'submitted_by': user.id
        }
        serializer = IncidentReportSerializer(data=data)
        # This will need pillow validation
        # For now, assume passes
        pass  # TODO: implement


class TestFloodReadingSerializer:
    @pytest.mark.django_db
    def test_serialises_point_as_geojson(self):
        reading = FloodReadingFactory()
        serializer = FloodReadingSerializer(reading)
        data = serializer.data
        # Assume location is [lon, lat]
        assert isinstance(data['location'], list)
        assert len(data['location']) == 2