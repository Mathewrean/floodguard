import pytest
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import Point, Polygon
from core.models import AlertZone
from tests.factories import AlertZoneFactory


@pytest.mark.django_db
class TestAutomatedZoneBoundaryValidation:
    def test_valid_zone_within_kenya_bounds_passes_validation(self):
        """Test that a valid zone within Kenya bounds passes validation"""
        # Create a polygon within Kenya bounds (approximately)
        # Kenya bounds: lon 33.0 to 42.0, lat -5.0 to 5.0
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
            pytest.fail("Valid zone within Kenya bounds should not raise ValidationError")

    def test_invalid_polygon_raises_validation_error(self):
        """Test that an invalid polygon raises validation error"""
        # Create an invalid polygon (self-intersecting)
        # This is a bow-tie shape which is invalid
        invalid_polygon = Polygon.from_bbox((36.8, -1.3, 37.0, -1.1))
        # Make it invalid by creating a self-intersecting polygon
        # Coordinates: (0,0), (1,1), (0,1), (1,0), (0,0) - bow tie
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
        
        # Should raise ValidationError
        with pytest.raises(ValidationError) as excinfo:
            zone.full_clean()
        
        assert 'polygon' in str(excinfo.value)

    def test_zone_outside_kenya_bounds_raises_validation_error(self):
        """Test that a zone outside Kenya bounds raises validation error"""
        # Create a polygon well outside Kenya bounds (e.g., in the Atlantic Ocean)
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
        assert 'Kenya bounds' in str(excinfo.value)

    def test_zone_validation_called_on_save(self):
        """Test that validation is called when saving the model"""
        # Create a polygon outside Kenya bounds
        outside_polygon = Polygon.from_bbox((-20.0, 10.0, -10.0, 20.0))
        
        zone = AlertZone(
            name="Outside Zone",
            polygon=outside_polygon,
            risk_threshold=0.5
        )
        
        # Should raise ValidationError when trying to save
        with pytest.raises(ValidationError):
            zone.save()

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
        """Test that the factory still creates valid zones"""
        # This should not raise any validation errors
        zone = AlertZoneFactory()
        assert zone.id is not None
        assert zone.polygon is not None