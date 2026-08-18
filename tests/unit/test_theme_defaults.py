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
    assert 'background: rgba(255,255,255,0.96);' in css
