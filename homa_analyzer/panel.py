"""Right-hand dock: the ring list, CSV export, and the 3D overlay style."""

import csv
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import overlay
from .homa import analyze_mol, bond_rows, csv_rows, geometry_warning
from .settings import COLORMAPS

logger = logging.getLogger(__name__)

LABEL_ACTOR = "homa_analyzer_label"
SPHERE_ACTOR = "homa_analyzer_spheres"
LEGEND_ACTOR = "homa_analyzer_legend"
POLL_MS = 800
COLUMNS = ["Ring", "Atoms", "Size", "HOMA", "EN", "GEO"]
COLOR_MODES = [("Fixed color", "fixed"), ("HOMA gradient", "gradient")]

WARNING_STYLE = (
    "QLabel { background: #fff3cd; color: #664d03; border: 1px solid #e0b000;"
    " border-radius: 4px; padding: 6px; }"
)


def last_optimization_method(main_window):
    compute = getattr(main_window, "compute_manager", None)
    return getattr(compute, "last_successful_optimization_method", None)


def format_value(value, decimals: int) -> str:
    return "n/a" if value is None else f"{value:.{decimals}f}"


class HomaPanel(QWidget):
    """Lists the HOMA of every ring and marks the ring centers in the 3D view."""

    def __init__(self, context, settings: dict, on_settings_change=None, parent=None):
        super().__init__(parent)
        self.context = context
        self.settings = settings
        self.on_settings_change = on_settings_change
        self.results = []
        self.method = None
        self._signature = None
        self._actor_names = []
        self._legend_title = None

        layout = QVBoxLayout(self)

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(WARNING_STYLE)
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

        self.method_label = QLabel()
        self.method_label.setWordWrap(True)
        layout.addWidget(self.method_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Recalculate")
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button = QPushButton("Export CSV...")
        self.export_button.clicked.connect(self.export_csv)
        self.export_bonds_button = QPushButton("Export bond lengths...")
        self.export_bonds_button.setToolTip(
            "One row per ring bond, for the selected rings or, with none "
            "selected, for every ring"
        )
        self.export_bonds_button.clicked.connect(self.export_bonds)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.export_bonds_button)
        layout.addLayout(buttons)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_label_tab(), "Labels")
        self.tabs.addTab(self._build_sphere_tab(), "Spheres")
        self.tabs.addTab(self._build_gradient_tab(), "Gradient")
        layout.addWidget(self.tabs)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    # -- settings widgets --------------------------------------------------
    def _color_button(self, key: str, title: str) -> QPushButton:
        button = QPushButton()

        def paint():
            color = self.settings[key]
            text = "#000000" if QColor(color).lightness() > 128 else "#ffffff"
            button.setText(color)
            button.setStyleSheet(f"background: {color}; color: {text};")

        def pick():
            color = QColorDialog.getColor(QColor(self.settings[key]), self, title)
            if color.isValid():
                self._set(key, color.name())
                paint()

        paint()
        button.clicked.connect(pick)
        button.repaint_color = paint
        return button

    def _style_button(self, text: str, key: str, attr: str) -> QPushButton:
        """A B / I / U toggle, as in the host's 2D label settings."""
        button = QPushButton(text)
        button.setCheckable(True)
        button.setFixedSize(28, 24)
        font = QFont()
        getattr(font, attr)(True)
        button.setFont(font)
        button.setChecked(self.settings[key])
        button.toggled.connect(lambda v: self._set(key, v))
        return button

    def _check(self, text: str, key: str) -> QCheckBox:
        check = QCheckBox(text)
        check.setChecked(self.settings[key])
        check.toggled.connect(lambda v: self._set(key, v))
        return check

    def _mode_combo(self, key: str) -> QComboBox:
        combo = QComboBox()
        for label, value in COLOR_MODES:
            combo.addItem(label, value)
        combo.setCurrentIndex([v for _, v in COLOR_MODES].index(self.settings[key]))
        combo.currentIndexChanged.connect(lambda i: self._set(key, combo.itemData(i)))
        return combo

    def _build_label_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.show_check = self._check("Show HOMA at ring centers", "show_labels")
        form.addRow(self.show_check)

        self.font_combo = QFontComboBox()
        self.font_combo.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        self.font_combo.setCurrentFont(QFont(self.settings["font_family"]))
        self.font_combo.currentFontChanged.connect(
            lambda f: self._set("font_family", f.family())
        )
        form.addRow("Font:", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setSuffix(" pt")
        self.size_spin.setValue(self.settings["font_size"])
        self.size_spin.valueChanged.connect(lambda v: self._set("font_size", v))
        form.addRow("Size:", self.size_spin)

        self.bold_button = self._style_button("B", "bold", "setBold")
        self.italic_button = self._style_button("I", "italic", "setItalic")
        self.underline_button = self._style_button("U", "underline", "setUnderline")
        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0)
        style_row.setSpacing(4)
        for button in (self.bold_button, self.italic_button, self.underline_button):
            style_row.addWidget(button)
        style_row.addStretch()
        style_widget = QWidget()
        style_widget.setLayout(style_row)
        form.addRow("Style:", style_widget)

        self.label_mode_combo = self._mode_combo("label_color_mode")
        form.addRow("Coloring:", self.label_mode_combo)
        self.color_button = self._color_button("label_color", "HOMA label color")
        form.addRow("Fixed color:", self.color_button)

        self.decimals_spin = QSpinBox()
        self.decimals_spin.setRange(1, 4)
        self.decimals_spin.setValue(self.settings["decimals"])
        self.decimals_spin.valueChanged.connect(lambda v: self._set("decimals", v))
        form.addRow("Decimals:", self.decimals_spin)
        return tab

    def _build_sphere_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.sphere_check = self._check("Show a sphere at ring centers", "show_spheres")
        form.addRow(self.sphere_check)

        self.sphere_mode_combo = self._mode_combo("sphere_color_mode")
        form.addRow("Coloring:", self.sphere_mode_combo)
        self.sphere_color_button = self._color_button(
            "sphere_color", "Ring-center sphere color"
        )
        form.addRow("Fixed color:", self.sphere_color_button)

        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.05, 2.0)
        self.radius_spin.setSingleStep(0.05)
        self.radius_spin.setDecimals(2)
        self.radius_spin.setSuffix(" Å")
        self.radius_spin.setValue(self.settings["sphere_radius"])
        self.radius_spin.valueChanged.connect(lambda v: self._set("sphere_radius", v))
        form.addRow("Radius:", self.radius_spin)

        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(5, 100)
        self.opacity_spin.setSingleStep(5)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.setValue(round(self.settings["sphere_opacity"] * 100))
        self.opacity_spin.valueChanged.connect(
            lambda v: self._set("sphere_opacity", v / 100)
        )
        form.addRow("Opacity:", self.opacity_spin)
        return tab

    def _build_gradient_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(COLORMAPS)
        self.cmap_combo.setCurrentText(self.settings["colormap"])
        self.cmap_combo.currentTextChanged.connect(lambda t: self._set("colormap", t))
        form.addRow("Colormap:", self.cmap_combo)

        self.min_spin = self._range_spin("range_min")
        self.max_spin = self._range_spin("range_max")
        range_row = QHBoxLayout()
        range_row.setContentsMargins(0, 0, 0, 0)
        range_row.addWidget(self.min_spin)
        range_row.addWidget(QLabel("to"))
        range_row.addWidget(self.max_spin)
        range_widget = QWidget()
        range_widget.setLayout(range_row)
        form.addRow("Range:", range_widget)

        fit_row = QHBoxLayout()
        fit_row.setContentsMargins(0, 0, 0, 0)
        self.fit_button = QPushButton("Fit to rings")
        self.fit_button.clicked.connect(self.fit_range)
        self.reset_range_button = QPushButton("0 to 1")
        self.reset_range_button.clicked.connect(lambda: self.set_range(0.0, 1.0))
        fit_row.addWidget(self.fit_button)
        fit_row.addWidget(self.reset_range_button)
        fit_widget = QWidget()
        fit_widget.setLayout(fit_row)
        form.addRow(fit_widget)

        self.legend_check = self._check("Show legend", "show_legend")
        form.addRow(self.legend_check)

        self.legend_title_edit = QLineEdit(self.settings["legend_title"])
        self.legend_title_edit.setMaxLength(40)
        self.legend_title_edit.editingFinished.connect(self._legend_title_changed)
        form.addRow("Legend title:", self.legend_title_edit)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Vertical", "Horizontal"])
        self.orientation_combo.setCurrentIndex(
            0 if self.settings["legend_vertical"] else 1
        )
        self.orientation_combo.currentIndexChanged.connect(
            lambda i: self._set("legend_vertical", i == 0)
        )
        form.addRow("Orientation:", self.orientation_combo)

        self.legend_labels_spin = QSpinBox()
        self.legend_labels_spin.setRange(2, 11)
        self.legend_labels_spin.setValue(self.settings["legend_labels"])
        self.legend_labels_spin.valueChanged.connect(
            lambda v: self._set("legend_labels", v)
        )
        form.addRow("Tick labels:", self.legend_labels_spin)

        self.legend_size_spin = QSpinBox()
        self.legend_size_spin.setRange(6, 48)
        self.legend_size_spin.setSuffix(" pt")
        self.legend_size_spin.setValue(self.settings["legend_font_size"])
        self.legend_size_spin.valueChanged.connect(
            lambda v: self._set("legend_font_size", v)
        )
        form.addRow("Legend font size:", self.legend_size_spin)

        self.legend_color_button = self._color_button(
            "legend_color", "Legend text color"
        )
        form.addRow("Legend text color:", self.legend_color_button)
        return tab

    def _range_spin(self, key: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-10.0, 2.0)
        spin.setDecimals(3)
        spin.setSingleStep(0.05)
        spin.setKeyboardTracking(False)
        spin.setValue(self.settings[key])
        spin.valueChanged.connect(lambda _v: self._range_changed())
        return spin

    def _range_changed(self) -> None:
        lo, hi = self.min_spin.value(), self.max_spin.value()
        if lo >= hi:
            self.status_label.setText("The gradient minimum must be below the maximum.")
            return
        self.settings["range_min"], self.settings["range_max"] = lo, hi
        self._settings_changed()

    def set_range(self, lo: float, hi: float) -> None:
        for spin, value in ((self.min_spin, lo), (self.max_spin, hi)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._range_changed()

    def fit_range(self) -> None:
        """Stretch the gradient over the HOMA values of the current rings."""
        values = [r.homa for r in self._shown_rings()]
        if not values:
            return
        lo, hi = min(values), max(values)
        if hi - lo < 1e-3:
            lo, hi = lo - 0.05, hi + 0.05
        self.set_range(max(lo, -10.0), min(hi, 2.0))

    def _legend_title_changed(self) -> None:
        title = self.legend_title_edit.text().strip() or "HOMA"
        self.legend_title_edit.setText(title)
        self._set("legend_title", title)

    def _set(self, key, value) -> None:
        self.settings[key] = value
        self._settings_changed(key)

    def _settings_changed(self, key=None) -> None:
        if self.on_settings_change is not None:
            self.on_settings_change(self.settings)
        if key == "decimals":
            self._fill_table()
        self.draw_overlay()

    # -- analysis ----------------------------------------------------------
    def _main_window(self):
        return self.context.get_main_window() if self.context is not None else None

    def refresh(self) -> None:
        """Recompute HOMA for the current molecule and redraw table and overlay."""
        mol = self.context.current_mol if self.context is not None else None
        self.method = last_optimization_method(self._main_window())
        self._signature = (id(mol), self.method)
        self.results = []
        try:
            self.results = analyze_mol(mol)
        except ValueError:
            self.status_label.setText(
                "No 3D structure. Convert the molecule to 3D first."
            )
        except Exception:
            logger.exception("HOMA Analyzer: analysis failed")
            self.status_label.setText("HOMA could not be computed (see log).")
        else:
            if not self.results:
                self.status_label.setText("The molecule has no rings.")
            else:
                n = sum(r.homa is not None for r in self.results)
                self.status_label.setText(
                    f"{len(self.results)} ring(s), {n} with HOMA parameters."
                )
        self._show_warning()
        self._fill_table()
        self.draw_overlay()

    def _show_warning(self) -> None:
        self.method_label.setText(
            f"Last optimization: {self.method}"
            if self.method
            else "Last optimization: none recorded (e.g. loaded from a file)"
        )
        warning = geometry_warning(self.method) if self.results else None
        self.warning_label.setText(warning or "")
        self.warning_label.setVisible(bool(warning))

    def _fill_table(self) -> None:
        decimals = self.settings["decimals"]
        self.table.setRowCount(len(self.results))
        for row, r in enumerate(self.results):
            values = [
                str(r.index),
                " ".join(f"{s}{i + 1}" for s, i in zip(r.symbols, r.atoms)),
                str(r.size),
                format_value(r.homa, decimals),
                format_value(r.en, decimals) if r.en is not None else "",
                format_value(r.geo, decimals) if r.geo is not None else "",
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3 and r.missing:
                    item.setToolTip("No HOMA parameters for " + ", ".join(r.missing))
                self.table.setItem(row, col, item)

    # -- 3D overlay --------------------------------------------------------
    def _plotter(self):
        return self.context.plotter if self.context is not None else None

    def _shown_rings(self):
        return [r for r in self.results if r.homa is not None]

    def label_texts(self):
        decimals = self.settings["decimals"]
        return [f"{r.homa:.{decimals}f}" for r in self._shown_rings()]

    def label_colors(self):
        rings = self._shown_rings()
        if self.settings["label_color_mode"] == "gradient":
            return [overlay.value_color(r.homa, self.settings) for r in rings]
        return [self.settings["label_color"]] * len(rings)

    def _uses_gradient(self) -> bool:
        s = self.settings
        return (s["show_labels"] and s["label_color_mode"] == "gradient") or (
            s["show_spheres"] and s["sphere_color_mode"] == "gradient"
        )

    def _wanted_actor_names(self):
        rings = self._shown_rings()
        if not rings:
            return []
        names = []
        if self.settings["show_labels"]:
            names += [f"{LABEL_ACTOR}-{r.index}" for r in rings]
        if self.settings["show_spheres"]:
            names.append(SPHERE_ACTOR)
        if self.settings["show_legend"] and self._uses_gradient():
            names.append(LEGEND_ACTOR)
        return names

    def clear_overlay(self, render: bool = True) -> None:
        plotter = self._plotter()
        if plotter is None:
            return
        try:
            for name in self._actor_names:
                plotter.remove_actor(name)
            self._actor_names = []
            if self._legend_title is not None:
                try:
                    plotter.remove_scalar_bar(self._legend_title)
                except (KeyError, ValueError, AttributeError):
                    pass  # already gone with the host's plotter.clear()
                self._legend_title = None
            if render:
                plotter.render()
        except Exception:
            logger.debug("HOMA Analyzer: could not remove the overlay", exc_info=True)

    def draw_overlay(self) -> None:
        """Labels, spheres and the legend at the ring centers, as set."""
        plotter = self._plotter()
        if plotter is None:
            return
        self.clear_overlay(render=False)
        rings = self._shown_rings()
        s = self.settings
        try:
            if s["show_spheres"] and rings:
                self._draw_spheres(plotter, rings)
            if s["show_labels"] and rings:
                self._draw_labels(plotter, rings)
            if s["show_legend"] and rings and self._uses_gradient():
                self._draw_legend(plotter, rings)
            plotter.render()
        except Exception:
            logger.exception("HOMA Analyzer: could not draw the 3D overlay")

    def _draw_spheres(self, plotter, rings) -> None:
        s = self.settings
        gradient = s["sphere_color_mode"] == "gradient"
        mesh = overlay.sphere_mesh(
            [r.center for r in rings],
            s["sphere_radius"],
            [r.homa for r in rings] if gradient else None,
        )
        kwargs = {"color": s["sphere_color"]}
        if gradient:
            kwargs = {
                "scalars": overlay.SCALARS,
                "cmap": s["colormap"],
                "clim": [s["range_min"], s["range_max"]],
                "show_scalar_bar": False,
            }
        plotter.add_mesh(
            mesh,
            name=SPHERE_ACTOR,
            opacity=s["sphere_opacity"],
            smooth_shading=True,
            pickable=False,
            reset_camera=False,
            **kwargs,
        )
        self._actor_names.append(SPHERE_ACTOR)

    def _draw_labels(self, plotter, rings) -> None:
        scale = getattr(plotter, "devicePixelRatioF", lambda: 1.0)()
        for ring, text, color in zip(rings, self.label_texts(), self.label_colors()):
            name = f"{LABEL_ACTOR}-{ring.index}"
            pixels = overlay.render_label(text, color, self.settings, scale)
            plotter.add_actor(
                overlay.label_actor(ring.center, pixels),
                name=name,
                reset_camera=False,
                pickable=False,
            )
            self._actor_names.append(name)

    def _draw_legend(self, plotter, rings) -> None:
        s = self.settings
        args = overlay.legend_args(s)
        plotter.add_mesh(
            overlay.legend_mesh(rings[0].center, s),
            name=LEGEND_ACTOR,
            scalars=overlay.SCALARS,
            cmap=s["colormap"],
            clim=[s["range_min"], s["range_max"]],
            opacity=0.0,
            pickable=False,
            reset_camera=False,
            show_scalar_bar=True,
            scalar_bar_args=args,
        )
        self._actor_names.append(LEGEND_ACTOR)
        self._legend_title = args["title"]

    def _overlay_missing(self) -> bool:
        actors = getattr(self._plotter(), "actors", None)
        if actors is None:
            return False
        return any(name not in actors for name in self._wanted_actor_names())

    def _poll(self) -> None:
        """The host clears the plotter on every redraw; recompute and redraw then."""
        if not self.isVisible():
            return
        mol = self.context.current_mol if self.context is not None else None
        signature = (id(mol), last_optimization_method(self._main_window()))
        if signature != self._signature or self._overlay_missing():
            self.refresh()

    # -- export ------------------------------------------------------------
    def export_csv(self) -> bool:
        if not self.results:
            QMessageBox.information(
                self, "HOMA Analyzer", "There are no rings to export."
            )
            return False
        path, _ = QFileDialog.getSaveFileName(
            self, "Export HOMA", "homa.csv", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return False
        if not path.lower().endswith(".csv"):
            path += ".csv"
        return self.write_csv(path)

    def selected_results(self):
        """Rings selected in the table, or every ring when none is selected."""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return list(self.results)
        return [self.results[r] for r in rows if r < len(self.results)]

    def export_bonds(self) -> bool:
        rings = self.selected_results()
        if not rings:
            QMessageBox.information(
                self, "HOMA Analyzer", "There are no rings to export."
            )
            return False
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Bond Lengths",
            "homa_bonds.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return False
        if not path.lower().endswith(".csv"):
            path += ".csv"
        return self.write_csv(path, bond_rows(rings))

    def write_csv(self, path: str, rows=None) -> bool:
        """Write the ring list, or the given ``rows``, under the geometry notes."""
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["# Last optimization", self.method or "none recorded"])
                warning = geometry_warning(self.method)
                if warning:
                    writer.writerow(["# Warning", warning])
                writer.writerows(rows if rows is not None else csv_rows(self.results))
        except OSError as exc:
            QMessageBox.warning(
                self, "HOMA Analyzer", f"Could not write {path}:\n{exc}"
            )
            return False
        if self.context is not None:
            self.context.show_status_message(f"HOMA exported to {path}", 5000)
        return True

    def shutdown(self) -> None:
        self.timer.stop()
        self.clear_overlay()


class HomaDock(QDockWidget):
    def __init__(self, panel: HomaPanel, parent=None):
        super().__init__("HOMA Analyzer", parent)
        self.panel = panel
        self.setObjectName("HomaAnalyzerDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setWidget(panel)

    def closeEvent(self, event):
        self.panel.shutdown()
        super().closeEvent(event)
