from pathlib import Path


def test_default_theme_does_not_follow_system_dark_mode():
    base_template = Path('templates/base.html').read_text(encoding='utf-8')
    main_js = Path('static/js/main.js').read_text(encoding='utf-8')
    assert "themePreferenceV2" in base_template
    assert "stored || 'light'" in base_template
    assert "savedTheme || 'light'" in main_js


def test_default_brand_palette_is_blue_not_black():
    css = Path('static/css/style.css').read_text(encoding='utf-8')
    assert '--primary: #0B5CAD;' in css
    assert '--bg: #F0F7FF;' in css
    assert '--surface-soft: #E8F4FD;' in css
    assert '--border: #B8D9F0;' in css
    assert 'background: rgba(255,255,255,0.96);' in css


def test_interactive_map_colours_use_the_shared_risk_palette():
    map_js = Path('static/js/map.js').read_text(encoding='utf-8')
    dashboard_js = Path('static/js/dashboard.js').read_text(encoding='utf-8')
    route_js = Path('static/js/safe_route.js').read_text(encoding='utf-8')

    assert "fillColor: '#1677C8'" in map_js
    assert "colour: '#7F1D1D'" in dashboard_js
    assert "safest: '#059669'" in route_js
