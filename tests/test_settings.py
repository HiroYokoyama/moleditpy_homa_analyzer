import json

from homa_analyzer import settings


def test_defaults_when_missing(isolated_settings):
    assert settings.load_settings() == settings.DEFAULTS


def test_round_trip(isolated_settings):
    data = dict(
        settings.DEFAULTS,
        label_color="#00FF00",
        font_family="Times New Roman",
        font_size=30,
        italic=True,
        underline=True,
        show_spheres=True,
        sphere_color_mode="fixed",
        sphere_radius=0.5,
        colormap="viridis_r",
        range_min=-0.5,
        legend_title="HOMA index",
        legend_vertical=False,
    )
    settings.save_settings(data)
    assert settings.load_settings() == dict(data, label_color="#00ff00")
    assert isolated_settings.exists()


def test_bad_values_fall_back_or_clamp():
    out = settings.sanitize(
        {
            "label_color": "red",
            "font_family": "",
            "font_size": 500,
            "decimals": 0,
            "bold": "yes",
            "show_labels": False,
            "label_color_mode": "rainbow",
            "colormap": "nope",
            "sphere_radius": 99,
            "sphere_opacity": 0,
            "legend_labels": 50,
            "legend_title": "x" * 41,
        }
    )
    d = settings.DEFAULTS
    assert out["label_color"] == d["label_color"]
    assert out["font_family"] == d["font_family"]
    assert out["font_size"] == 72 and out["decimals"] == 1
    assert out["bold"] is True and out["show_labels"] is False
    assert out["label_color_mode"] == "fixed" and out["colormap"] == d["colormap"]
    assert out["sphere_radius"] == 2.0 and out["sphere_opacity"] == 0.05
    assert out["legend_labels"] == 11 and out["legend_title"] == "HOMA"


def test_inverted_range_resets():
    out = settings.sanitize({"range_min": 0.9, "range_max": 0.1})
    assert (out["range_min"], out["range_max"]) == (0.0, 1.0)


def test_bool_is_not_a_size():
    assert settings.sanitize({"font_size": True})["font_size"] == 18


def test_unreadable_file_gives_defaults(isolated_settings):
    isolated_settings.write_text("{not json", encoding="utf-8")
    assert settings.load_settings() == settings.DEFAULTS
    isolated_settings.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert settings.load_settings() == settings.DEFAULTS


def test_unwritable_path_does_not_raise(tmp_path):
    settings.save_settings(settings.DEFAULTS, path=str(tmp_path / "no" / "x.json"))


def test_file_is_named_settings_json():
    assert settings.SETTINGS_FILE.endswith("settings.json")
