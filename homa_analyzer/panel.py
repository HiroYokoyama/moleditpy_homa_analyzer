"""Right-hand dock: the ring list, CSV export, and the 3D label style."""

import csv
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .homa import analyze_mol, csv_rows, geometry_warning
from .settings import FONT_FAMILIES

logger = logging.getLogger(__name__)

LABEL_ACTOR = "homa_analyzer_ring_labels"
POLL_MS = 800
COLUMNS = ["Ring", "Atoms", "Size", "HOMA", "EN", "GEO"]

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
    """Lists the HOMA of every ring and labels the ring centers in the 3D view."""

    def __init__(self, context, settings: dict, on_settings_change=None, parent=None):
        super().__init__(parent)
        self.context = context
        self.settings = settings
        self.on_settings_change = on_settings_change
        self.results = []
        self.method = None
        self._signature = None

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
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

        layout.addWidget(self._build_label_box())

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    # -- label settings ----------------------------------------------------
    def _build_label_box(self) -> QGroupBox:
        box = QGroupBox("3D labels")
        form = QFormLayout(box)

        self.show_check = QCheckBox("Show HOMA at ring centers")
        self.show_check.setChecked(self.settings["show_labels"])
        self.show_check.toggled.connect(lambda v: self._set("show_labels", v))
        form.addRow(self.show_check)

        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._pick_color)
        self._paint_color_button()
        form.addRow("Color:", self.color_button)

        self.font_combo = QComboBox()
        for family in FONT_FAMILIES:
            self.font_combo.addItem(family.capitalize(), family)
        self.font_combo.setCurrentIndex(
            FONT_FAMILIES.index(self.settings["font_family"])
        )
        self.font_combo.currentIndexChanged.connect(
            lambda i: self._set("font_family", self.font_combo.itemData(i))
        )
        form.addRow("Font:", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setSuffix(" pt")
        self.size_spin.setValue(self.settings["font_size"])
        self.size_spin.valueChanged.connect(lambda v: self._set("font_size", v))
        form.addRow("Size:", self.size_spin)

        self.bold_check = QCheckBox("Bold")
        self.bold_check.setChecked(self.settings["bold"])
        self.bold_check.toggled.connect(lambda v: self._set("bold", v))
        form.addRow(self.bold_check)

        self.decimals_spin = QSpinBox()
        self.decimals_spin.setRange(1, 4)
        self.decimals_spin.setValue(self.settings["decimals"])
        self.decimals_spin.valueChanged.connect(lambda v: self._set("decimals", v))
        form.addRow("Decimals:", self.decimals_spin)
        return box

    def _paint_color_button(self) -> None:
        color = self.settings["label_color"]
        self.color_button.setText(color)
        text = "#000000" if QColor(color).lightness() > 128 else "#ffffff"
        self.color_button.setStyleSheet(f"background: {color}; color: {text};")

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.settings["label_color"]), self, "HOMA label color"
        )
        if color.isValid():
            self._set("label_color", color.name())
            self._paint_color_button()

    def _set(self, key, value) -> None:
        self.settings[key] = value
        if self.on_settings_change is not None:
            self.on_settings_change(self.settings)
        if key == "decimals":
            self._fill_table()
        self.draw_labels()

    # -- analysis ----------------------------------------------------------
    def _main_window(self):
        return self.context.get_main_window() if self.context is not None else None

    def refresh(self) -> None:
        """Recompute HOMA for the current molecule and redraw table and labels."""
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
        self.draw_labels()

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
            homa = format_value(r.homa, decimals)
            values = [
                str(r.index),
                " ".join(f"{s}{i + 1}" for s, i in zip(r.symbols, r.atoms)),
                str(r.size),
                homa,
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

    # -- 3D labels ---------------------------------------------------------
    def _plotter(self):
        return self.context.plotter if self.context is not None else None

    def label_points(self):
        decimals = self.settings["decimals"]
        shown = [r for r in self.results if r.homa is not None]
        return [r.center for r in shown], [f"{r.homa:.{decimals}f}" for r in shown]

    def clear_labels(self, render: bool = True) -> None:
        plotter = self._plotter()
        if plotter is None:
            return
        try:
            plotter.remove_actor(LABEL_ACTOR)
            if render:
                plotter.render()
        except Exception:
            logger.debug("HOMA Analyzer: could not remove labels", exc_info=True)

    def draw_labels(self) -> None:
        plotter = self._plotter()
        if plotter is None:
            return
        self.clear_labels(render=False)
        points, labels = self.label_points()
        try:
            if self.settings["show_labels"] and points:
                plotter.add_point_labels(
                    points,
                    labels,
                    name=LABEL_ACTOR,
                    font_size=self.settings["font_size"],
                    font_family=self.settings["font_family"],
                    bold=self.settings["bold"],
                    text_color=self.settings["label_color"],
                    shape=None,
                    show_points=False,
                    always_visible=True,
                    pickable=False,
                    reset_camera=False,
                )
            plotter.render()
        except Exception:
            logger.exception("HOMA Analyzer: could not draw labels")

    def _labels_missing(self) -> bool:
        plotter = self._plotter()
        actors = getattr(plotter, "actors", None)
        if actors is None:
            return False
        return LABEL_ACTOR not in actors

    def _poll(self) -> None:
        """The host clears the plotter on every redraw; recompute and relabel then."""
        if not self.isVisible():
            return
        mol = self.context.current_mol if self.context is not None else None
        signature = (id(mol), last_optimization_method(self._main_window()))
        wants_labels = self.settings["show_labels"] and self.label_points()[0]
        if signature != self._signature or (wants_labels and self._labels_missing()):
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

    def write_csv(self, path: str) -> bool:
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["# Last optimization", self.method or "none recorded"])
                warning = geometry_warning(self.method)
                if warning:
                    writer.writerow(["# Warning", warning])
                writer.writerows(csv_rows(self.results))
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
        self.clear_labels()


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
