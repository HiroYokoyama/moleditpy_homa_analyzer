"""HOMA Analyzer - ring aromaticity (HOMA) of the MoleditPy 3D structure.

Analysis > "HOMA Analyzer" opens a dock on the right listing the HOMA index of
every ring, with the EN/GEO split for rings of one bond type, and exports the
list as CSV.  In the 3D view each ring center gets its value as a label and,
optionally, a sphere; both can be colored by HOMA on a gradient with a legend.
Fonts, colors, sizes and the gradient are set in the dock.  A warning appears when the structure was
last optimized with a force field, whose bond lengths do not suit HOMA.

Source code, README, and full license (GNU GPL):
    https://github.com/HiroYokoyama/moleditpy_homa_analyzer
Copyright (c) HiroYokoyama. Licensed under the GNU Lesser General Public License;
see the LICENSE file in the repository above for the full terms.
"""

import logging

logger = logging.getLogger(__name__)

PLUGIN_NAME = "HOMA Analyzer"
PLUGIN_VERSION = "0.1.0"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = (
    "Compute the HOMA aromaticity index of each ring in the 3D structure, "
    "label it at the ring centers and export the list as CSV."
)
PLUGIN_CATEGORY = "Analysis"
PLUGIN_TAGS = ["Analysis", "Visualization"]
PLUGIN_DEPENDENCIES = ["numpy", "PySide6-Essentials", "pyvista", "rdkit"]
PLUGIN_OPTIONAL_DEPENDENCIES = []
PLUGIN_SUPPORTED_MOLEDITPY_VERSION = ">=5.0.0, <6.0.0"
PLUGIN_SUPPORTED_PYTHON_VERSION = ">=3.9, <3.15"

MENU_LABEL = "HOMA Analyzer"
WINDOW_ID = "homa_analyzer_dock"

_context = None
current_settings = {}


def _settings() -> dict:
    if not current_settings:
        from .settings import load_settings

        current_settings.update(load_settings())
    return current_settings


def open_panel(*_args):
    """Analysis-menu action: show the dock (one at a time) and analyze."""
    import shiboken6
    from PySide6.QtCore import Qt

    from .panel import HomaDock, HomaPanel
    from .settings import save_settings

    existing = _context.get_window(WINDOW_ID)
    if existing is not None and not shiboken6.isValid(existing):
        existing = None  # deleted behind our back; build a new one
    if existing is not None:
        existing.show()
        existing.raise_()
        existing.panel.timer.start()
        existing.panel.refresh()
        return existing
    mw = _context.get_main_window()
    panel = HomaPanel(_context, _settings(), on_settings_change=save_settings)
    dock = HomaDock(panel, mw)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    _context.register_window(WINDOW_ID, dock)
    dock.show()
    panel.refresh()
    return dock


def _on_document_reset():
    dock = _context.get_window(WINDOW_ID) if _context is not None else None
    if dock is not None:
        dock.close()


def initialize(context):
    """The dock opens from the Analysis menu and closes on File > New."""
    global _context
    _context = context
    current_settings.clear()
    context.add_analysis_tool(MENU_LABEL, open_panel)
    context.register_document_reset_handler(_on_document_reset)
