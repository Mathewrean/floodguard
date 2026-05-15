from core.data_sources.aggregator import build_risk_feature_vector, fetch_all_sources, get_source_status


class StubSource:
    def __init__(self, name, payload, configured=True):
        self.name = name
        self.payload = payload
        self.configured = configured

    def is_configured(self):
        return self.configured

    def safe_fetch(self, lat, lon):
        return {
            'source': self.name,
            'available': self.configured,
            **self.payload,
        }


def test_fetch_all_sources_merges_parallel_results(monkeypatch):
    monkeypatch.setattr(
        'core.data_sources.aggregator.ALL_SOURCES',
        [
            StubSource('open_meteo', {'river_discharge_today': 12}),
            StubSource('openweather', {'rainfall_1h_mm': 5}),
        ],
    )

    data = fetch_all_sources(-1.29, 36.82)

    assert data['open_meteo']['river_discharge_today'] == 12
    assert data['openweather']['rainfall_1h_mm'] == 5


def test_build_risk_feature_vector_contains_merged_fields(monkeypatch):
    monkeypatch.setattr(
        'core.data_sources.aggregator.fetch_all_sources',
        lambda lat, lon: {
            'open_meteo': {
                'source': 'open_meteo',
                'available': True,
                'river_discharge_today': 10,
                'river_discharge_24h': 11,
                'river_discharge_7d_max': 20,
            },
            'openweather': {
                'source': 'openweather',
                'available': True,
                'rainfall_1h_mm': 4,
                'humidity_pct': 80,
                'pressure_hpa': 1008,
                'wind_speed_ms': 3,
            },
            'nasa_gpm': {
                'source': 'nasa_gpm',
                'available': False,
                'nasa_precip_mmhr': 0,
            },
        },
    )

    features = build_risk_feature_vector(-1.29, 36.82, 'Nairobi')

    assert features['river_discharge'] == 10
    assert features['rainfall_1h_mm'] == 4
    assert features['humidity'] == 80
    assert features['sources_available'] == 2
    assert features['data_confidence'] == 'medium'
    assert features['zone_name'] == 'Nairobi'


def test_get_source_status_reports_configuration(monkeypatch):
    monkeypatch.setattr(
        'core.data_sources.aggregator.ALL_SOURCES',
        [
            StubSource('open_meteo', {}, configured=True),
            StubSource('tomorrow_io', {}, configured=False),
        ],
    )

    statuses = get_source_status()

    assert statuses == [
        {'name': 'open_meteo', 'configured': True, 'status': 'ok'},
        {'name': 'tomorrow_io', 'configured': False, 'status': 'no_key'},
    ]
