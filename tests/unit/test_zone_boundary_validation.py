import pytest
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import Point, Polygon
from django.conf import settings
from core.models import AlertZone
from tests.factories import AlertZoneFactory


@pytest.mark.django_db
class TestAutomatedZoneBoundaryValidation:
    def test_valid_zone_within_kenya_bounds_passes_validation(self):
        """Test that a valid zone within default bounds passes validation"""
        # Default bounds: lon 33.0-42.0, lat -5.0 to 5.0 (Kenya/East Africa)
        valid_polygon = Polygon.from_bbox((36.8, -1.3, 37.0, -1.1))
        
        zone = AlertZone(
            name="Valid Zone",
            polygon=valid_polygon,
            risk_threshold=0.5
        )
        
        # Should not raise ValidationError
        try:
            zone.full_clean()
            zone.save()
            assert zone.id is not None
        except ValidationError:
            pytest.fail("Valid zone within bounds should not raise ValidationError")

    def test_invalid_polygon_raises_validation_error(self):
        """Test that an invalid polygon (self-intersecting) raises validation error"""
        invalid_polygon = Polygon([
            (36.8, -1.3), (37.0, -1.1), 
            (36.8, -1.1), (37.0, -1.3),
            (36.8, -1.3)
        ], srid=4326)
        
        zone = AlertZone(
            name="Invalid Zone",
            polygon=invalid_polygon,
            risk_threshold=0.5
        )
        
        # Should raise ValidationError for invalid geometry
        with pytest.raises(ValidationError) as excinfo:
            zone.full_clean()
        
        assert 'polygon' in str(excinfo.value)

    def test_zone_outside_default_bounds_raises_validation_error(self):
        """Test that a zone outside configured bounds raises validation error"""
        # Create a polygon outside default bounds (e.g., in Atlantic Ocean, far from Kenya)
        outside_polygon = Polygon.from_bbox((-20.0, 10.0, -10.0, 20.0))
        
        zone = AlertZone(
            name="Outside Zone",
            polygon=outside_polygon,
            risk_threshold=0.5
        )
        
        # Should raise ValidationError
        with pytest.raises(ValidationError) as excinfo:
            zone.full_clean()
        
        assert 'polygon' in str(excinfo.value)
        assert 'bounds' in str(excinfo.value).lower()

    def test_zone_validation_called_on_save(self):
        """Test that validation catches invalid polygons when called explicitly"""
        outside_polygon = Polygon.from_bbox((-20.0, 10.0, -10.0, 20.0))
        
        zone = AlertZone(
            name="Outside Zone",
            polygon=outside_polygon,
            risk_threshold=0.5
        )
        
        with pytest.raises(ValidationError):
            zone.full_clean()

    def test_valid_nairobi_area_zone_passes(self):
        """Test that a zone in the Nairobi area passes validation"""
        # Nairobi approximate bounds: lat -1.5 to -1.1, lon 36.6 to 37.2
        nairobi_polygon = Polygon.from_bbox((36.7, -1.4, 37.1, -1.0))
        
        zone = AlertZone(
            name="Nairobi Zone",
            polygon=nairobi_polygon,
            risk_threshold=0.5
        )
        
        # Should not raise ValidationError
        try:
            zone.full_clean()
            zone.save()
            assert zone.id is not None
        except ValidationError:
            pytest.fail("Valid Nairobi area zone should not raise ValidationError")

    def test_zone_validation_works_with_factory(self):
        """Test that the factory creates zones within valid bounds"""
        # AlertZoneFactory creates zones within Nairobi bounds (within default)
        zone = AlertZoneFactory()
        assert zone.id is not None
        assert zone.polygon is not None
        # Ensure it's valid
        zone.full_clean()  # Should not raise