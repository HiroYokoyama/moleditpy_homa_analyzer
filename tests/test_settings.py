import json

from homa_analyzer import settings


def test_defaults_when_missing(isolated_settings):
    assert settings.load_settings() == settings.DEFAULTS


def test_round_trip(isolated_settings):
    data = dict(
        settings.DEFAULTS, label_color="#00FF00", font_family="times", font_size=30
    )
    settings.save_settings(data)
    loaded = settings.load_settings()
    assert loaded["label_color"] == "#00ff00"
    assert loaded["font_family"] == "times" and loaded["font_size"] == 30
    assert isolated_settings.exists()


def test_bad_values_fall_back_or_clamp():
    out = settings.sanitize(
        {
            "label_color": "red",
            "font_family": "comic",
            "font_size": 500,
            "decimals": 0,
            "bold": "yes",
            "show_labels": False,
        }
    )
    assert out["label_color"] == settings.DEFAULTS["label_color"]
    assert out["font_family"] == "arial"
    assert out["font_size"] == 72 and out["decimals"] == 1
    assert out["bold"] is True and out["show_labels"] is False


def test_bool_is_not_a_size():
    assert settings.sanitize({"font_size": True})["font_size"] == 18


def test_unreadable_file_gives_defaults(isolated_settings):
    isolated_settings.write_text("{not json", encoding="utf-8")
    assert settings.load_settings() == settings.DEFAULTS
    isolated_settings.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert settings.load_settings() == settings.DEFAULTS


def test_file_is_named_settings_json():
    assert settings.SETTINGS_FILE.endswith("settings.json")
