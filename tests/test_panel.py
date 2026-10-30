"""The dock with a real Qt widget tree, a fake host and a recording plotter."""

import csv
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
Chem = pytest.importorskip("rdkit.Chem")
from rdkit.Chem import AllChem

import homa_analyzer
from homa_analyzer import panel as panel_mod
from homa_analyzer.settings import default_settings


class FakePlotter:
    def __init__(self):
        self.actors = {}
        self.calls = []

    def add_point_labels(self, points, labels, name=None, **kwargs):
        self.calls.append(SimpleNamespace(points=points, labels=labels, kwargs=kwargs))
        self.actors[name] = object()

    def remove_actor(self, name):
        self.actors.pop(name, None)

    def render(self):
        pass


class FakeContext:
    def __init__(self, mol=None, method=None):
        self.current_mol = mol
        self.plotter = FakePlotter()
        self.mw = SimpleNamespace(
            compute_manager=SimpleNamespace(last_successful_optimization_method=method)
        )
        self.messages = []
        self.windows = {}

    def get_main_window(self):
        return self.mw

    def show_status_message(self, message, timeout=3000):
        self.messages.append(message)

    def get_window(self, wid):
        return self.windows.get(wid)

    def register_window(self, wid, w):
        self.windows[wid] = w


def _benzene():
    mol = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1"))
    AllChem.EmbedMolecule(mol, randomSeed=3)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


@pytest.fixture
def make_panel(qapp):
    made = []

    def make(mol=None, method=None, settings=None):
        ctx = FakeContext(mol, method)
        p = panel_mod.HomaPanel(ctx, settings or default_settings())
        made.append(p)
        return p, ctx

    yield make
    for p in made:
        p.shutdown()
        p.deleteLater()


def test_refresh_fills_table_and_labels(make_panel):
    p, ctx = make_panel(_benzene(), "GFN2-xTB")
    p.refresh()
    assert p.table.rowCount() == 1
    assert p.table.item(0, 2).text() == "6"
    (call,) = ctx.plotter.calls
    assert len(call.points) == 1 and call.labels[0] == p.table.item(0, 3).text()
    assert call.kwargs["text_color"] == "#d03000"
    assert call.kwargs["font_family"] == "arial" and call.kwargs["font_size"] == 18
    assert p.warning_label.isHidden()


def test_force_field_geometry_shows_warning(make_panel):
    p, _ = make_panel(_benzene(), "MMFF94s (RDKit)")
    p.refresh()
    assert not p.warning_label.isHidden()
    assert "MMFF94s (RDKit)" in p.warning_label.text()


def test_no_warning_without_rings(make_panel):
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    p, ctx = make_panel(mol, "UFF (RDKit)")
    p.refresh()
    assert p.table.rowCount() == 0 and "no rings" in p.status_label.text()
    assert p.warning_label.isHidden() and ctx.plotter.calls == []


def test_no_3d_structure(make_panel):
    p, _ = make_panel(Chem.MolFromSmiles("c1ccccc1"))
    p.refresh()
    assert "No 3D structure" in p.status_label.text()


def test_label_settings_redraw_and_save(make_panel):
    saved = []
    p, ctx = make_panel(_benzene())
    p.on_settings_change = lambda s: saved.append(dict(s))
    p.refresh()
    p.size_spin.setValue(30)
    p.font_combo.setCurrentIndex(2)
    p.decimals_spin.setValue(2)
    last = ctx.plotter.calls[-1]
    assert last.kwargs["font_size"] == 30 and last.kwargs["font_family"] == "times"
    assert len(last.labels[0].split(".")[1]) == 2
    assert len(p.table.item(0, 3).text().split(".")[1]) == 2
    assert saved[-1]["decimals"] == 2
    p.show_check.setChecked(False)
    assert panel_mod.LABEL_ACTOR not in ctx.plotter.actors


def test_poll_relabels_after_host_redraw(make_panel):
    p, ctx = make_panel(_benzene())
    p.show()
    p.refresh()
    ctx.plotter.actors.clear()  # the host's plotter.clear() on redraw
    p._poll()
    assert panel_mod.LABEL_ACTOR in ctx.plotter.actors
    n = len(ctx.plotter.calls)
    p._poll()  # nothing changed: no work
    assert len(ctx.plotter.calls) == n


def test_poll_notices_new_optimization(make_panel):
    p, ctx = make_panel(_benzene(), "MMFF94s (RDKit)")
    p.show()
    p.refresh()
    ctx.mw.compute_manager.last_successful_optimization_method = "GFN2-xTB"
    p._poll()
    assert p.warning_label.isHidden()


def test_write_csv(make_panel, tmp_path):
    p, ctx = make_panel(_benzene(), "UFF (RDKit)")
    p.refresh()
    path = tmp_path / "out.csv"
    assert p.write_csv(str(path))
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == ["# Last optimization", "UFF (RDKit)"]
    assert rows[1][0] == "# Warning"
    assert rows[2][:5] == ["Ring", "Atoms", "Size", "Aromatic", "HOMA"]
    assert rows[3][2] == "6" and rows[3][3] == "yes"
    assert ctx.messages


def test_shutdown_removes_labels(make_panel):
    p, ctx = make_panel(_benzene())
    p.refresh()
    p.shutdown()
    assert panel_mod.LABEL_ACTOR not in ctx.plotter.actors
    assert not p.timer.isActive()


def test_initialize_and_open_panel(qapp, monkeypatch):
    from PySide6.QtWidgets import QMainWindow

    mw = QMainWindow()
    ctx = FakeContext(_benzene())
    ctx.mw = mw
    mw.compute_manager = SimpleNamespace(last_successful_optimization_method=None)
    registered = {}
    ctx.add_analysis_tool = lambda label, cb: registered.setdefault("tool", (label, cb))
    ctx.register_document_reset_handler = lambda cb: registered.setdefault("reset", cb)
    homa_analyzer.initialize(ctx)
    assert registered["tool"][0] == "HOMA Analyzer"
    dock = registered["tool"][1]()
    assert dock.panel.table.rowCount() == 1
    assert homa_analyzer.open_panel() is dock  # singleton
    registered["reset"]()
    assert dock.isHidden() and not dock.panel.timer.isActive()
    dock.deleteLater()
    mw.deleteLater()


def test_metadata():
    assert homa_analyzer.PLUGIN_VERSION == "0.1.0"
    assert homa_analyzer.PLUGIN_CATEGORY == "Analysis"
