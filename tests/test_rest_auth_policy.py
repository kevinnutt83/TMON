from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_uc_routes_do_not_use_public_permission_callback():
    text = (ROOT / 'tmon-admin' / 'includes' / 'api-uc.php').read_text(encoding='utf-8')
    assert "permission_callback' => '__return_true'" not in text


def test_public_allowlist_is_limited_to_expected_bootstrap_and_version_routes():
    admin_api = (ROOT / 'tmon-admin' / 'includes' / 'api.php').read_text(encoding='utf-8')
    v2_api = (ROOT / 'unit-connector' / 'includes' / 'v2-api.php').read_text(encoding='utf-8')

    public_routes = [
        "'/status'",
        "'/github/manifest'",
        "'/version'",
        "'/device/check-in'",
    ]

    for route in public_routes:
        assert route in admin_api or route in v2_api

    assert admin_api.count("permission_callback' => '__return_true'") <= 4
    assert v2_api.count("permission_callback' => '__return_true'") <= 0
