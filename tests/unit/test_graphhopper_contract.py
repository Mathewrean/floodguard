import pytest
from django.test import override_settings


@pytest.mark.django_db
@override_settings(GRAPHOPPER_API_KEY='test-key')
def test_safe_route_uses_current_graphhopper_profile_contract(client, mocker):
    upstream = mocker.MagicMock(ok=True)
    upstream.json.return_value = {
        'paths': [{
            'distance': 1200,
            'time': 180000,
            'points': {'coordinates': [[36.8219, -1.2921], [36.8172, -1.2864]]},
        }]
    }
    get = mocker.patch('requests.get', return_value=upstream)

    response = client.get('/api/v1/safe-route/', {
        'origin_lat': -1.2921,
        'origin_lon': 36.8219,
        'dest_lat': -1.2864,
        'dest_lon': 36.8172,
        'vehicle': 'car',
    })

    assert response.status_code == 200
    assert response.data['routes'][0]['engine'] == 'GraphHopper + H3 Flood Overlay'
    params = get.call_args.kwargs['params']
    assert ('profile', 'car') in params
    assert not any(name in {'vehicle', 'algorithm'} for name, _ in params)
