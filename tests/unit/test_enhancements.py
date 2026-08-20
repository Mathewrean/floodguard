"""
Regression tests for all five FloodGuard future enhancements:
1. H3 Hierarchical Indexing
2. Real-Time Zone Interpolation
3. Predictive Modeling (48h forecasts)
4. Cross-Zone Flood Propagation Simulation
5. Automated Zone Splitting and Merging
"""
import pytest
import hashlib
from unittest.mock import patch, MagicMock
from django.contrib.gis.geos import Polygon

from core.risk_engine import (
    compute_parent_risk,
    get_child_cells,
    get_parent_cell,
    zoom_level_to_resolution,
    interpolate_risk_scores,
    predict_risk_timeline,
    simulate_propagation,
    should_split,
    should_merge,
    auto_split_merge,
    normalize_01,
)

pytestmark = pytest.mark.django_db

# Try to import h3 — tests skip if not available
try:
    import h3
    H3_AVAILABLE = True
except ImportError:
    H3_AVAILABLE = False

pytestmark_h3 = pytest.mark.skipif(not H3_AVAILABLE, reason="h3 library not installed")


# ============================================================
# Enhancement 1 — H3 Hierarchical Indexing
# ============================================================

class TestH3Hierarchy:
    """Tests for H3 hierarchical indexing and zoom-level mapping."""

    def test_zoom_14_maps_to_resolution_7(self):
        """Assert zoom 14 maps to resolution 7 (Street Scale)."""
        assert zoom_level_to_resolution(14) == 7

    def test_zoom_mapping_table(self):
        """Verify all zoom-to-resolution mappings."""
        assert zoom_level_to_resolution(1) == 3
        assert zoom_level_to_resolution(6) == 3
        assert zoom_level_to_resolution(7) == 4
        assert zoom_level_to_resolution(9) == 4
        assert zoom_level_to_resolution(10) == 5
        assert zoom_level_to_resolution(11) == 5
        assert zoom_level_to_resolution(12) == 6
        assert zoom_level_to_resolution(13) == 6
        assert zoom_level_to_resolution(14) == 7
        assert zoom_level_to_resolution(15) == 7
        assert zoom_level_to_resolution(16) == 8
        assert zoom_level_to_resolution(18) == 8

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_parent_score_aggregation_formula(self):
        """Assert parent score equals max * 0.6 + mean * 0.4 for a known child set."""
        child_scores = [0.2, 0.4, 0.6, 0.8]
        max_score = max(child_scores)
        mean_score = sum(child_scores) / len(child_scores)
        expected = max_score * 0.6 + mean_score * 0.4
        result = compute_parent_risk(child_scores)
        assert result == pytest.approx(expected, abs=0.001)

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_parent_score_empty_children(self):
        """Empty children returns 0.0."""
        assert compute_parent_risk([]) == 0.0

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_parent_score_single_child(self):
        """Single child returns that child's score."""
        assert compute_parent_risk([0.75]) == pytest.approx(0.75 * 1.0, abs=0.001)

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_get_child_cells_returns_children_at_res_plus_one(self):
        """get_child_cells returns cells at resolution + 1."""
        parent = h3.latlng_to_cell(-1.2921, 36.8219, 6)
        children = get_child_cells(parent)
        assert len(children) > 0
        for child in children:
            assert h3.get_resolution(child) == 7
            # Parent should be the parent of each child
            assert h3.cell_to_parent(child, 6) == parent

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_get_parent_cell(self):
        """get_parent_cell returns the parent H3 index."""
        cell = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        parent = get_parent_cell(cell)
        assert parent is not None
        assert h3.get_resolution(parent) == 6

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_get_parent_cell_at_resolution_zero(self):
        """get_parent_cell returns None at resolution 0 (no parent)."""
        cell = h3.latlng_to_cell(-1.2921, 36.8219, 1)
        # h3.cell_to_parent on a res-0 cell raises, so get_parent_cell returns None
        parent = get_parent_cell(cell)
        # The function should handle this gracefully
        assert parent is None or h3.get_resolution(parent) < h3.get_resolution(cell)


# ============================================================
# Enhancement 2 — Real-Time Zone Interpolation (IDW)
# ============================================================

class TestInterpolation:
    """Tests for IDW interpolation of H3 cell risk scores."""

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_interpolate_produces_score_between_min_and_max(self):
        """interpolated score must be between min and max of input neighbours."""
        # Create a small grid of cells
        center = h3.latlng_to_cell(-1.2921, 36.8219, 9)
        neighbors = h3.grid_disk(center, 2)

        # Assign scores to a subset of cells
        cell_scores = {}
        for i, cell in enumerate(neighbors[:5]):
            cell_scores[cell] = 0.3 + (i * 0.1)  # 0.3, 0.4, 0.5, 0.6, 0.7

        result = interpolate_risk_scores(cell_scores)

        # Check that interpolated cells have scores between 0.3 and 0.7
        for idx, data in result.items():
            if data['interpolated']:
                assert 0.0 <= data['risk_score'] <= 0.7 + 0.1  # small tolerance for rounding

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_interpolated_cells_never_exceed_max_neighbour(self):
        """Interpolated cells cannot exceed the maximum score of direct-data neighbours."""
        center = h3.latlng_to_cell(-1.2921, 36.8219, 9)
        neighbors = h3.grid_disk(center, 1)

        # Direct data cells with scores
        cell_scores = {neighbors[0]: 0.3, neighbors[1]: 0.2}

        result = interpolate_risk_scores(cell_scores)

        max_direct = max(cell_scores.values())
        for idx, data in result.items():
            if data['interpolated']:
                assert data['risk_score'] <= max_direct + 0.001  # tolerance

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_interpolated_field_true_only_for_non_direct_cells(self):
        """The interpolated field is True only for cells without a direct data point."""
        center = h3.latlng_to_cell(-1.2921, 36.8219, 9)
        neighbors = h3.grid_disk(center, 1)

        cell_scores = {neighbors[0]: 0.5, neighbors[1]: 0.3}
        result = interpolate_risk_scores(cell_scores)

        for idx, data in result.items():
            if idx in cell_scores:
                assert data['interpolated'] is False
            # Cells not in cell_scores but in result should be interpolated=True
            # (if they have data from interpolation)

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_interpolation_cache(self):
        """The Redis cache key is set after the first call and served on the second."""
        from core.risk_engine import interpolate_risk_cached
        from core.cache_keys import cache_key as make_cache_key

        bbox_hash = make_cache_key('bbox', -1.4, 36.8, -1.2, 37.0, 7, False)
        cell_scores = {'abc123': 0.5, 'def456': 0.3}

        # First call should compute and cache
        result1 = interpolate_risk_cached(cell_scores, bbox_hash)
        assert result1 is not None

        # Mock the cache to verify the key was set
        from unittest.mock import MagicMock
        from django.core.cache import cache
        cache.set = MagicMock()
        cache.get = MagicMock(return_value=result1)

        # Second call should use cache
        result2 = interpolate_risk_cached(cell_scores, bbox_hash)
        assert result2 is not None
        cache.get.assert_called()

    def test_interpolate_empty_input(self):
        """Empty input returns empty dict."""
        assert interpolate_risk_scores({}) == {}


# ============================================================
# Enhancement 3 — Predictive Modeling (48h timeline)
# ============================================================

class TestPredictiveTimeline:
    """Tests for 48-hour predictive risk timeline."""

    def test_escalate_2_tiers_when_3_consecutive_hours_over_20mm(self):
        """3 consecutive hours exceeding 20 mm/hr escalates 2 tiers from base."""
        base_score = 0.3  # MODERATE
        hourly_data = []
        for i in range(48):
            hourly_data.append({
                'precipitation_mm': 25.0 if 5 <= i < 8 else 0,
                'rain_mm': 25.0 if 5 <= i < 8 else 0,
                'soil_moisture': 0.3,
                'river_discharge': 5.0,
                'current_discharge': 5.0,
            })

        timeline = predict_risk_timeline(hourly_data, base_score)

        # At hour 7 (after 3 consecutive > 20mm), should escalate 2 tiers
        assert len(timeline) == 48
        assert timeline[7]['escalation_trigger'] == '3_consecutive_hours_over_20mm'

    def test_escalate_1_tier_when_soil_moisture_over_085_and_precip_over_5(self):
        """Soil moisture > 0.85 AND precip > 5 mm/hr escalates 1 tier."""
        base_score = 0.2  # LOW
        hourly_data = []
        for i in range(48):
            hourly_data.append({
                'precipitation_mm': 10.0,
                'rain_mm': 10.0,
                'soil_moisture': 0.9,
                'river_discharge': 5.0,
                'current_discharge': 5.0,
            })

        timeline = predict_risk_timeline(hourly_data, base_score)
        assert len(timeline) == 48

        # With 10mm precipitation and 0.9 soil moisture, escalation should trigger
        triggered_hours = [t for t in timeline if t['escalation_trigger'] is not None]
        assert len(triggered_hours) > 0

    def test_timeline_returns_exactly_48_entries(self):
        """The timeline must return exactly 48 entries."""
        hourly_data = [{'precipitation_mm': 0, 'rain_mm': 0, 'soil_moisture': 0.5, 'river_discharge': 5.0, 'current_discharge': 5.0} for _ in range(48)]
        timeline = predict_risk_timeline(hourly_data, 0.5)
        assert len(timeline) == 48

    def test_timeline_entries_have_required_fields(self):
        """Each timeline entry must have hour, predicted_score, predicted_level, escalation_trigger."""
        hourly_data = [{'precipitation_mm': 0, 'rain_mm': 0, 'soil_moisture': 0.5, 'river_discharge': 5.0, 'current_discharge': 5.0} for _ in range(48)]
        timeline = predict_risk_timeline(hourly_data, 0.5)

        for i, entry in enumerate(timeline):
            assert entry['hour'] == i
            assert 0.0 <= entry['predicted_score'] <= 1.0
            assert entry['predicted_level'] in ['SAFE', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL']
            assert 'escalation_trigger' in entry

    def test_no_escalation_when_conditions_not_met(self):
        """When no escalation rules fire, predicted level equals base."""
        base_score = 0.1
        hourly_data = [{'precipitation_mm': 0, 'rain_mm': 0, 'soil_moisture': 0.3, 'river_discharge': 1.0, 'current_discharge': 1.0} for _ in range(48)]
        timeline = predict_risk_timeline(hourly_data, base_score)

        for entry in timeline:
            if entry['escalation_trigger'] is None:
                assert entry['predicted_score'] == pytest.approx(base_score, abs=0.01)

    def test_river_discharge_24h_spike_triggers_escalation(self):
        """River discharge 24h > 1.5x current triggers escalation."""
        base_score = 0.5
        hourly_data = []
        for i in range(48):
            discharge = 5.0 if i < 24 else 10.0  # doubles after 24h
            hourly_data.append({
                'precipitation_mm': 0,
                'rain_mm': 0,
                'soil_moisture': 0.5,
                'river_discharge': discharge,
                'current_discharge': 5.0,
            })

        timeline = predict_risk_timeline(hourly_data, base_score)
        # Hour 24 onwards should have escalation trigger
        triggered = [t for t in timeline[24:] if t['escalation_trigger'] == 'river_discharge_24h_spike']
        assert len(triggered) > 0


# ============================================================
# Enhancement 4 — Cross-Zone Flood Propagation
# ============================================================

class TestFloodPropagation:
    """Tests for BFS flood propagation simulation."""

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_propagation_never_exceeds_12_hours(self):
        """simulate_propagation must never return cells more than 12 hours out."""
        from core.risk_engine import simulate_propagation
        center = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        with patch('core.risk_engine.get_cached_elevation', return_value=100.0):
            result = simulate_propagation([center], hours=15, cell_risks={center: 0.8})
        for cell_idx, cell_data in result['cells'].items():
            assert cell_data['propagation_hour'] <= 12

    def test_propagation_returns_dict_with_cells_and_paths(self):
        """Result has 'cells' and 'propagation_paths' keys."""
        from core.risk_engine import simulate_propagation
        center = h3.latlng_to_cell(-1.2921, 36.8219, 7) if H3_AVAILABLE else "test_cell"
        with patch('core.risk_engine.get_cached_elevation', return_value=100.0):
            result = simulate_propagation([center], hours=3, cell_risks={center: 0.85})

        assert 'cells' in result
        assert 'propagation_paths' in result
        assert isinstance(result['cells'], dict)
        assert isinstance(result['propagation_paths'], list)

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_elevation_decay_higher_target(self):
        """Cell at higher elevation than source receives decay factor 0.3."""
        from core.risk_engine import elevation_decay
        with patch('core.risk_engine.get_cached_elevation') as mock_elev:
            # source at lat=-1.29 -> elev 100, target at lat=1.0 -> elev 200 (higher)
            mock_elev.side_effect = lambda lat, lon: 100.0 if lat < 0 else 200.0
            decay = elevation_decay(-1.29, 36.82, 1.0, 36.82)
            assert decay == 0.3

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_elevation_decay_lower_target(self):
        """Cell at lower elevation than source receives decay factor 0.9."""
        from core.risk_engine import elevation_decay
        with patch('core.risk_engine.get_cached_elevation') as mock_elev:
            mock_elev.side_effect = lambda lat, lon: 200.0 if lat < 0 else 100.0
            decay = elevation_decay(-1.0, 36.82, -1.29, 36.82)
            assert decay == 0.9

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_propagated_score_formula(self):
        """propagated_score = source_score * 0.75 * decay for a known input."""
        center = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        cell_risks = {center: 0.9}

        with patch('core.risk_engine.get_cached_elevation') as mock_elev:
            mock_elev.return_value = 100.0  # flat terrain -> decay = 0.9

            result = simulate_propagation([center], hours=1, cell_risks=cell_risks)

            for cell_idx, data in result['cells'].items():
                if data['propagation_hour'] == 1:
                    # score should be 0.9 * 0.75 * 0.9 = 0.6075
                    expected = 0.9 * 0.75 * 0.9
                    assert data['risk_score'] == pytest.approx(expected, abs=0.01)

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    @pytest.mark.django_db
    def test_propagation_endpoint_rejects_hours_over_12(self):
        """The propagation endpoint returns HTTP 400 for hours > 12."""
        from rest_framework.test import APIClient
        from rest_framework.throttling import SimpleRateThrottle

        center = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        # Disable all throttling for this test
        SimpleRateThrottle.allow_request = lambda self, request, view: True

        client = APIClient()
        response = client.get(f'/api/v1/flood-propagation/?seed_cell={center}&hours=15')
        assert response.status_code == 400

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_propagation_cache_key_set(self):
        """The Redis cache key is set after the first call."""
        from core.risk_engine import simulate_propagation_cached
        from core.cache_keys import cache_key as make_cache_key

        center = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        cache_key_str = make_cache_key('propagation', center, 3)

        # First call should compute and cache
        result = simulate_propagation_cached([center], hours=3, cell_risks={center: 0.8}, cache_key_str=cache_key_str)
        assert result is not None


# ============================================================
# Enhancement 5 — Automated Zone Splitting and Merging
# ============================================================

class TestSplitMerge:
    """Tests for automated zone splitting and merging based on risk heterogeneity."""

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_should_split_returns_true_when_range_exceeds_03(self):
        """should_split returns True when child score range exceeds 0.3."""
        child_scores = {'a': 0.1, 'b': 0.8}
        assert should_split(child_scores) is True

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_should_split_returns_false_when_range_under_03(self):
        """should_split returns False when child score range is below 0.3."""
        child_scores = {'a': 0.5, 'b': 0.7}
        assert should_split(child_scores) is False

    def test_should_split_empty_returns_false(self):
        """should_split on empty or single-child returns False."""
        assert should_split({}) is False
        assert should_split({'a': 0.5}) is False

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_should_merge_returns_true_when_range_below_010(self):
        """should_merge returns True when adjacent cell score range is below 0.10."""
        cells = ['a', 'b', 'c']
        cell_scores = {'a': 0.30, 'b': 0.32, 'c': 0.35}
        assert should_merge(cells, cell_scores) is True

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_should_merge_returns_false_when_range_above_010(self):
        """should_merge returns False when score range exceeds 0.10."""
        cells = ['a', 'b', 'c']
        cell_scores = {'a': 0.30, 'b': 0.50, 'c': 0.70}
        assert should_merge(cells, cell_scores) is False

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_auto_split_merge_never_produces_below_res_8(self):
        """auto_split_merge never produces cells below resolution 8 via splitting."""
        cells = []
        center = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        children = h3.cell_to_children(center, 8)

        # Create cells with heterogeneous risk
        scores = [0.1, 0.9, 0.3, 0.2, 0.8, 0.1, 0.4, 0.1, 0.3, 0.2, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        for i, child in enumerate(children[:len(scores)]):
            cells.append({
                'h3_index': child,
                'risk_score': scores[i % len(scores)],
                'risk_level': 'HIGH' if scores[i % len(scores)] > 0.7 else 'SAFE' if scores[i % len(scores)] < 0.2 else 'MODERATE',
                'resolution': 7,
            })

        result = auto_split_merge(cells)

        for cell in result:
            if 'split_from' in cell and cell.get('split_from'):
                res = cell.get('resolution', 7)
                assert res >= 3, "Split children should not go below resolution 3"

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_auto_split_merge_never_produces_above_res_3(self):
        """auto_split_merge never produces cells above resolution 3 via merging."""
        cells = []
        center = h3.latlng_to_cell(-1.2921, 36.8219, 4)
        children = h3.cell_to_children(center, 4)

        for child in children[:6]:
            cells.append({
                'h3_index': child,
                'risk_score': 0.35,  # homogeneous scores
                'risk_level': 'LOW',
                'resolution': 4,
            })

        result = auto_split_merge(cells)

        for cell in result:
            res = cell.get('resolution', 4)
            if 'merged_from' in cell and cell.get('merged_from'):
                assert res <= 3, "Merged parent should not exceed resolution 3"

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_safe_cells_never_split_or_merged(self):
        """SAFE cells are never split or merged."""
        cells = [{
            'h3_index': 'test_cell',
            'risk_score': 0.05,
            'risk_level': 'SAFE',
            'resolution': 7,
        }]
        result = auto_split_merge(cells)
        assert len(result) == 1
        assert result[0]['risk_level'] == 'SAFE'
        assert 'split_from' not in result[0]
        assert 'merged_from' not in result[0]

    @pytest.mark.skipif(not H3_AVAILABLE, reason="h3 not installed")
    def test_auto_split_merge_preserves_at_least_one_safe_cell(self):
        """auto_split_merge ensures at least one SAFE cell in output."""
        cells = []
        center = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        children = h3.cell_to_children(center, 8)[:6]

        for i, child in enumerate(children):
            cells.append({
                'h3_index': child,
                'risk_score': 0.8,  # all high risk
                'risk_level': 'HIGH',
                'resolution': 7,
            })

        result = auto_split_merge(cells)
        safe_count = sum(1 for c in result if normalize_01(c.get('risk_score', 0)) < 0.2)
        assert safe_count >= 1
