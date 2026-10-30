"""Label, sphere and gradient preferences, kept in settings.json beside the package.

Folder plugins must use exactly ``settings.json``: the Plugin Installer backs up
and restores only that name when it replaces the folder on an update.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "settings.json"
)

# The Mapped Cube Viewer's list, so both plugins offer the same choices.
COLORMAPS = (
    "coolwarm_r",
    "coolwarm",
    "jet_r",
    "jet",
    "rainbow_r",
    "rainbow",
    "bwr_r",
    "bwr",
    "seismic_r",
    "seismic",
    "viridis_r",
    "viridis",
    "plasma_r",
    "plasma",
    "magma_r",
    "magma",
    "inferno_r",
    "inferno",
)
COLOR_MODES = ("fixed", "gradient")

DEFAULTS = {
    "show_labels": True,
    "label_color_mode": "fixed",
    "label_color": "#d03000",
    "font_family": "Arial",
    "font_size": 18,
    "bold": True,
    "italic": False,
    "underline": False,
    "decimals": 3,
    "show_spheres": False,
    "sphere_color_mode": "gradient",
    "sphere_color": "#3070ff",
    "sphere_radius": 0.3,
    "sphere_opacity": 0.6,
    # HOMA 1 (aromatic) is red, 0 (Kekule) blue.
    "colormap": "coolwarm",
    "range_min": 0.0,
    "range_max": 1.0,
    "show_legend": True,
    "legend_title": "HOMA",
    "legend_vertical": True,
    "legend_labels": 5,
    "legend_font_size": 14,
    "legend_color": "#202020",
}

BOOLS = (
    "show_labels",
    "bold",
    "italic",
    "underline",
    "show_spheres",
    "show_legend",
    "legend_vertical",
)
COLORS = ("label_color", "sphere_color", "legend_color")
CHOICES = {
    "label_color_mode": COLOR_MODES,
    "sphere_color_mode": COLOR_MODES,
    "colormap": COLORMAPS,
}
TEXTS = {"font_family": 100, "legend_title": 40}
INT_LIMITS = {
    "font_size": (6, 72),
    "decimals": (1, 4),
    "legend_labels": (2, 11),
    "legend_font_size": (6, 48),
}
FLOAT_LIMITS = {
    "sphere_radius": (0.05, 2.0),
    "sphere_opacity": (0.05, 1.0),
    "range_min": (-10.0, 2.0),
    "range_max": (-10.0, 2.0),
}


def default_settings() -> dict:
    return dict(DEFAULTS)


def _is_hex_color(value) -> bool:
    if not (isinstance(value, str) and len(value) == 7 and value.startswith("#")):
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def _clamped(value, lo, hi, kind):
    if isinstance(value, bool):
        raise TypeError
    return min(max(kind(value), lo), hi)


def sanitize(data) -> dict:
    """Defaults merged with the valid, clamped entries of ``data``."""
    out = default_settings()
    if not isinstance(data, dict):
        return out
    for key in BOOLS:
        if isinstance(data.get(key), bool):
            out[key] = data[key]
    for key in COLORS:
        if _is_hex_color(data.get(key)):
            out[key] = data[key].lower()
    for key, allowed in CHOICES.items():
        if data.get(key) in allowed:
            out[key] = data[key]
    for key, limit in TEXTS.items():
        text = data.get(key)
        if isinstance(text, str) and text.strip() and len(text) <= limit:
            out[key] = text.strip()
    for limits, kind in ((INT_LIMITS, int), (FLOAT_LIMITS, float)):
        for key, (lo, hi) in limits.items():
            try:
                out[key] = _clamped(data[key], lo, hi, kind)
            except (KeyError, TypeError, ValueError):
                pass
    if out["range_min"] >= out["range_max"]:
        out["range_min"], out["range_max"] = DEFAULTS["range_min"], DEFAULTS["range_max"]
    return out


def load_settings(path=None) -> dict:
    path = path or SETTINGS_FILE
    try:
        with open(path, encoding="utf-8") as fh:
            return sanitize(json.load(fh))
    except FileNotFoundError:
        return default_settings()
    except (OSError, ValueError):
        logger.warning("HOMA Analyzer: ignoring unreadable %s", path, exc_info=True)
        return default_settings()


def save_settings(settings: dict, path=None) -> None:
    path = path or SETTINGS_FILE
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(sanitize(settings), fh, indent=2)
    except OSError:
        logger.warning("HOMA Analyzer: could not save %s", path, exc_info=True)
