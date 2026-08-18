import pytest


pytestmark = pytest.mark.django_db
h3 = pytest.importorskip('h3')


def test_h3_geojson_is_valid_longitude_latitude_polygon():
    from core.h3_risk import h3_index_to_geojson

    index = h3.latlng_to_cell(-1.2921, 36.8219, 7)
    geometry = h3_index_to_geojson(index)

    assert geometry['type'] == 'Polygon'
    ring = geometry['coordinates'][0]
    assert len(ring) >= 6
    for longitude, latitude in ring:
        assert -180 <= longitude <= 180
        assert -90 <= latitude <= 90


def test_persisted_h3_cell_uses_cell_centroid_not_source_point():
    from core.zoning.h3_intelligence import get_or_create_h3_cell

    cell = get_or_create_h3_cell(-1.2921, 36.8219, resolution=7)
    expected_lat, expected_lon = h3.cell_to_latlng(cell.h3_index)

    assert cell.centroid_lat == pytest.approx(expected_lat)
    assert cell.centroid_lon == pytest.approx(expected_lon)


def test_h3_cell_api_rejects_oversized_or_invalid_viewports(client):
    assert client.get('/api/v1/h3-cells/?min_lat=-90&min_lon=-180&max_lat=90&max_lon=180').status_code == 400
    assert client.get('/api/v1/h3-cells/?min_lat=10&min_lon=1&max_lat=9&max_lon=2').status_code == 400
