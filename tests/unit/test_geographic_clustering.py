import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone
import datetime
from core.models import IncidentReport
from tests.factories import UserFactory, IncidentReportFactory


@pytest.mark.django_db
class TestGeographicClustering:
    def setup_method(self):
        self.user = UserFactory()
        self.base_location = Point(36.8, -1.3, srid=4326)  # Nairobi area

    def test_incident_report_has_cluster_id_field(self):
        """Test that IncidentReport model has cluster_id field"""
        report = IncidentReport(
            location=self.base_location,
            severity=3,
            description="Test report",
            submitted_by=self.user
        )
        assert hasattr(report, 'cluster_id')

    def test_cluster_id_is_auto_generated_on_save(self):
        """Test that cluster_id is automatically generated when saving a report"""
        report = IncidentReport(
            location=self.base_location,
            severity=3,
            description="Test report",
            submitted_by=self.user
        )
        # Before saving, cluster_id should be None or empty
        assert report.cluster_id is None or report.cluster_id == ''
        
        report.save()
        
        # After saving, cluster_id should be set
        assert report.cluster_id is not None
        assert report.cluster_id != ''
        assert isinstance(report.cluster_id, str)

    def test_nearby_reports_share_cluster_id(self):
        """Test that reports within clustering radius share the same cluster ID"""
        # Create first report
        report1 = IncidentReport(
            location=Point(36.8, -1.3, srid=4326),
            severity=3,
            description="First report",
            submitted_by=self.user
        )
        report1.save()
        cluster_id_1 = report1.cluster_id
        
        # Create second report very close to first (within 100m)
        report2 = IncidentReport(
            location=Point(36.8001, -1.3001, srid=4326),  # Very close
            severity=4,
            description="Second report",
            submitted_by=self.user
        )
        report2.save()
        cluster_id_2 = report2.cluster_id
        
        # They should share the same cluster ID
        assert cluster_id_1 == cluster_id_2

    def test_far_apart_reports_have_different_cluster_ids(self):
        """Test that reports far apart have different cluster IDs"""
        # Create first report
        report1 = IncidentReport(
            location=Point(36.8, -1.3, srid=4326),
            severity=3,
            description="First report",
            submitted_by=self.user
        )
        report1.save()
        cluster_id_1 = report1.cluster_id
        
        # Create second report far away (more than 100m)
        report2 = IncidentReport(
            location=Point(37.0, -1.5, srid=4326),  # Far away
            severity=4,
            description="Second report",
            submitted_by=self.user
        )
        report2.save()
        cluster_id_2 = report2.cluster_id
        
        # They should have different cluster IDs
        assert cluster_id_1 != cluster_id_2

    def test_cluster_id_based_on_earliest_report(self):
        """Test that cluster ID is based on the earliest report in the cluster"""
        # Create first report (earlier)
        report1 = IncidentReport(
            location=Point(36.8, -1.3, srid=4326),
            severity=3,
            description="First report",
            submitted_by=self.user
        )
        report1.save()
        
        # Simulate it being created earlier
        report1.created_at = timezone.now() - datetime.timedelta(minutes=10)
        report1.save(update_fields=['created_at'])
        
        # Create second report (later) nearby
        report2 = IncidentReport(
            location=Point(36.8001, -1.3001, srid=4326),
            severity=4,
            description="Second report",
            submitted_by=self.user
        )
        report2.save()
        
        # The cluster ID should be based on the earliest report
        assert report2.cluster_id == report1.cluster_id
        assert report1.cluster_id is not None

    def test_cluster_recent_reports_method_exists(self):
        """Test that the cluster_recent_reports class method exists"""
        assert hasattr(IncidentReport, 'cluster_recent_reports')
        assert callable(getattr(IncidentReport, 'cluster_recent_reports'))

    def test_cluster_recent_reports_updates_cluster_ids(self):
        """Test that cluster_recent_reports updates cluster IDs for reports without them"""
        # Create a report without explicit cluster_id (will get one on save)
        report1 = IncidentReport(
            location=Point(36.8, -1.3, srid=4326),
            severity=3,
            description="Report 1",
            submitted_by=self.user
        )
        report1.save()
        
        # Create another report nearby
        report2 = IncidentReport(
            location=Point(36.8001, -1.3001, srid=4326),
            severity=4,
            description="Report 2",
            submitted_by=self.user
        )
        # Don't save it yet - we want to test the clustering method
        
        # Manually remove cluster_id from report2 to simulate unset
        report2.cluster_id = None
        report2.save()
        
        # Verify report2 has no cluster_id
        assert report2.cluster_id is None
        
        # Run the clustering method
        IncidentReport.cluster_recent_reports(hours=24, radius_meters=100)
        
        # Refresh report2 from database
        report2.refresh_from_db()
        
        # Now it should have a cluster ID (same as report1)
        assert report2.cluster_id is not None
        assert report2.cluster_id == report1.cluster_id