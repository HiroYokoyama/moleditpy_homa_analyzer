"""Label preferences, kept in settings.json beside the package.

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

# VTK text actors support exactly these three families.
FONT_FAMILIES = ("arial", "courier", "times")

DEFAULTS = {
    "show_labels": True,
    "label_color": "#d03000",
    "font_family": "arial",
    "font_size": 18,
    "bold": True,
    "decimals": 3,
}

LIMITS = {"font_size": (6, 72), "decimals": (1, 4)}


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


def sanitize(data) -> dict:
    """Defaults merged with the valid, clamped entries of ``data``."""
    out = default_settings()
    if not isinstance(data, dict):
        return out
    for key in ("show_labels", "bold"):
        if isinstance(data.get(key), bool):
            out[key] = data[key]
    if _is_hex_color(data.get("label_color")):
        out["label_color"] = data["label_color"].lower()
    if data.get("font_family") in FONT_FAMILIES:
        out["font_family"] = data["font_family"]
    for key, (lo, hi) in LIMITS.items():
        value = data.get(key)
        if isinstance(value, bool):
            continue
        try:
            out[key] = min(max(int(value), lo), hi)
        except (TypeError, ValueError):
            pass
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
