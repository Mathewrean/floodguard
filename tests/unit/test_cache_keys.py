from core.cache_keys import cache_key


def test_dynamic_values_produce_memcached_safe_keys():
    key = cache_key('risk-vector', -1.29, 36.82, 'Dynamic Zone - Nairobi CBD (weather)')
    assert len(key) < 250
    assert all(33 <= ord(character) <= 126 for character in key)
    assert 'Nairobi' not in key


def test_cache_key_is_deterministic():
    assert cache_key('search', 'Westlands market') == cache_key('search', 'Westlands market')
