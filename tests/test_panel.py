"""The dock with a real Qt widget tree, a fake host and a recording plotter."""

import csv
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvista")
Chem = pytest.importorskip("rdkit.Chem")
from rdkit.Chem import AllChem

import homa_analyzer
from homa_analyzer import panel as panel_mod
from homa_analyzer.settings import default_settings

_REAL_HOST_SYNCS_METHOD = panel_mod.host_syncs_method  # before the autouse patch


class FakePlotter:
    """Records what the panel adds; like pyvista, a scalar bar is keyed by title."""

    def __init__(self):
        self.actors = {}
        self.meshes = {}
        self.scalar_bars = {}

    def add_actor(self, actor, name=None, **kwargs):
        self.actors[name] = actor

    def add_mesh(self, mesh, name=None, **kwargs):
        self.actors[name] = object()
        self.meshes[name] = SimpleNamespace(mesh=mesh, kwargs=kwargs)
        if kwargs.get("show_scalar_bar"):
            title = kwargs["scalar_bar_args"]["title"]
            if title in self.scalar_bars:
                raise ValueError("duplicate scalar bar")  # what pyvista would do
            self.scalar_bars[title] = kwargs["scalar_bar_args"]

    def remove_actor(self, name):
        self.actors.pop(name, None)
        self.meshes.pop(name, None)

    def remove_scalar_bar(self, title):
        del self.scalar_bars[title]

    def clear(self):
        self.actors.clear()
        self.meshes.clear()
        self.scalar_bars.clear()

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


def _embed(smiles):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=3)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _benzene():
    return _embed("c1ccccc1")


def _labels(plotter):
    return sorted(n for n in plotter.actors if n.startswith(panel_mod.LABEL_ACTOR))


@pytest.fixture(autouse=True)
def older_host(monkeypatch):
    """Panel tests describe a host before 5.1.2 unless they say otherwise."""
    monkeypatch.setattr(panel_mod, "host_syncs_method", lambda version=None: False)


@pytest.fixture
def make_panel(qapp):
    made = []

    def make(mol=None, method=None, **overrides):
        if mol is not None and method and method.endswith("(RDKit)"):
            mol.SetProp(panel_mod.HOST_OPT_TAG, "MMFF_RDKIT")  # as the host does
        ctx = FakeContext(mol, method)
        settings = default_settings()
        settings.update(overrides)
        p = panel_mod.HomaPanel(ctx, settings)
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
    assert _labels(ctx.plotter) == [f"{panel_mod.LABEL_ACTOR}-1"]
    assert p.label_texts() == [p.table.item(0, 3).text()]
    assert p.label_colors() == ["#ffffff"]
    assert panel_mod.SPHERE_ACTOR not in ctx.plotter.actors  # off by default
    assert not ctx.plotter.scalar_bars  # fixed label color: no legend
    assert p.warning_label.isHidden()


def test_one_label_per_ring(make_panel):
    p, ctx = make_panel(_embed("c1ccc2ccccc2c1"))
    p.refresh()
    assert len(_labels(ctx.plotter)) == 2


def test_force_field_geometry_shows_warning(make_panel):
    p, _ = make_panel(_benzene(), "MMFF94s (RDKit)")
    p.refresh()
    assert not p.warning_label.isHidden()
    assert "MMFF94s (RDKit)" in p.warning_label.text()


def test_no_warning_and_no_overlay_without_rings(make_panel):
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    p, ctx = make_panel(mol, "UFF (RDKit)", show_spheres=True)
    p.refresh()
    assert p.table.rowCount() == 0 and "no rings" in p.status_label.text()
    assert p.warning_label.isHidden() and ctx.plotter.actors == {}


def test_no_3d_structure(make_panel):
    p, _ = make_panel(Chem.MolFromSmiles("c1ccccc1"))
    p.refresh()
    assert "No 3D structure" in p.status_label.text()


def test_label_settings_redraw_and_save(make_panel):
    saved = []
    p, ctx = make_panel(_benzene())
    p.on_settings_change = lambda s: saved.append(dict(s))
    p.refresh()
    first = ctx.plotter.actors[f"{panel_mod.LABEL_ACTOR}-1"]
    p.size_spin.setValue(30)
    p.italic_button.setChecked(True)
    p.underline_button.setChecked(True)
    p.decimals_spin.setValue(2)
    assert ctx.plotter.actors[f"{panel_mod.LABEL_ACTOR}-1"] is not first
    assert saved[-1]["font_size"] == 30
    assert saved[-1]["italic"] is True and saved[-1]["underline"] is True
    assert len(p.label_texts()[0].split(".")[1]) == 2
    assert len(p.table.item(0, 3).text().split(".")[1]) == 2
    p.show_check.setChecked(False)
    assert _labels(ctx.plotter) == []


def test_font_family_from_the_combo(make_panel):
    from PySide6.QtGui import QFont

    p, _ = make_panel(_benzene())
    p.font_combo.setCurrentFont(QFont("Courier New"))
    assert p.settings["font_family"] == p.font_combo.currentFont().family()


def test_style_buttons_reflect_settings(make_panel):
    p, _ = make_panel(_benzene(), bold=False, italic=True, underline=True)
    assert not p.bold_button.isChecked()
    assert p.italic_button.isChecked() and p.underline_button.isChecked()
    assert p.underline_button.font().underline()


def test_fixed_color_spheres(make_panel):
    p, ctx = make_panel(_benzene(), show_spheres=True, sphere_color_mode="fixed")
    p.refresh()
    sphere = ctx.plotter.meshes[panel_mod.SPHERE_ACTOR]
    assert sphere.kwargs["color"] == "#3070ff"
    assert sphere.kwargs["opacity"] == 0.6
    assert "scalars" not in sphere.kwargs
    assert not ctx.plotter.scalar_bars


def test_gradient_spheres_and_legend(make_panel):
    p, ctx = make_panel(_embed("c1ccc2ccccc2c1"), show_spheres=True)
    p.refresh()
    sphere = ctx.plotter.meshes[panel_mod.SPHERE_ACTOR]
    assert sphere.kwargs["scalars"] == "HOMA" and sphere.kwargs["cmap"] == "coolwarm"
    assert sphere.kwargs["clim"] == [0.0, 1.0]
    values = set(sphere.mesh.point_data["HOMA"].round(6))
    assert values == {round(r.homa, 6) for r in p.results}
    assert list(ctx.plotter.scalar_bars) == ["HOMA"]


def test_gradient_label_colors_follow_the_value(make_panel):
    p, ctx = make_panel(_benzene(), label_color_mode="gradient")
    p.refresh()
    p.set_range(-10.0, -9.0)  # benzene far above the range: top color
    top = p.label_colors()[0]
    p.set_range(1.5, 2.0)  # far below: bottom color
    assert p.label_colors()[0] != top
    assert list(ctx.plotter.scalar_bars) == ["HOMA"]


def test_legend_settings(make_panel):
    p, ctx = make_panel(_benzene(), show_spheres=True)
    p.refresh()
    p.legend_title_edit.setText("HOMA index")
    p._legend_title_changed()
    p.orientation_combo.setCurrentIndex(1)
    p.legend_labels_spin.setValue(3)
    p.legend_size_spin.setValue(20)
    (args,) = ctx.plotter.scalar_bars.values()
    assert args["title"] == "HOMA index" and args["vertical"] is False
    assert args["n_labels"] == 3 and args["label_font_size"] == 20
    p.legend_check.setChecked(False)
    assert not ctx.plotter.scalar_bars


def test_empty_legend_title_falls_back(make_panel):
    p, _ = make_panel(_benzene())
    p.legend_title_edit.setText("   ")
    p._legend_title_changed()
    assert p.settings["legend_title"] == "HOMA"


def test_fit_range_and_reset(make_panel):
    p, _ = make_panel(_embed("c1ccc2[nH]ccc2c1"), label_color_mode="gradient")
    p.refresh()
    p.fit_button.click()
    values = [r.homa for r in p.results]
    assert p.settings["range_min"] == pytest.approx(min(values), abs=1e-3)
    assert p.settings["range_max"] == pytest.approx(max(values), abs=1e-3)
    p.reset_range_button.click()
    assert (p.settings["range_min"], p.settings["range_max"]) == (0.0, 1.0)


def test_fit_range_widens_a_single_value(make_panel):
    p, _ = make_panel(_benzene())
    p.refresh()
    p.fit_range()
    assert p.settings["range_max"] - p.settings["range_min"] == pytest.approx(0.1)


def test_inverted_range_is_refused(make_panel):
    p, _ = make_panel(_benzene())
    p.min_spin.setValue(1.5)
    assert (p.settings["range_min"], p.settings["range_max"]) == (0.0, 1.0)
    assert "minimum" in p.status_label.text()


def test_poll_redraws_after_host_clear(make_panel):
    p, ctx = make_panel(_benzene(), show_spheres=True)
    p.show()
    p.refresh()
    ctx.plotter.clear()  # the host's plotter.clear() on redraw
    p._poll()
    assert panel_mod.SPHERE_ACTOR in ctx.plotter.actors
    assert _labels(ctx.plotter) and list(ctx.plotter.scalar_bars) == ["HOMA"]
    actors = dict(ctx.plotter.actors)
    p._poll()  # nothing changed: no work
    assert ctx.plotter.actors == actors


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


def test_shutdown_removes_the_overlay(make_panel):
    p, ctx = make_panel(_benzene(), show_spheres=True)
    p.refresh()
    p.shutdown()
    assert ctx.plotter.actors == {} and not ctx.plotter.scalar_bars
    assert not p.timer.isActive()


def test_initialize_and_open_panel(qapp):
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


def test_open_panel_replaces_a_deleted_dock(qapp):
    import shiboken6
    from PySide6.QtWidgets import QMainWindow

    mw = QMainWindow()
    ctx = FakeContext(_benzene())
    ctx.mw = mw
    mw.compute_manager = SimpleNamespace(last_successful_optimization_method=None)
    ctx.add_analysis_tool = lambda *a: None
    ctx.register_document_reset_handler = lambda *a: None
    homa_analyzer.initialize(ctx)
    old = homa_analyzer.open_panel()
    old.panel.shutdown()
    shiboken6.delete(old)
    new = homa_analyzer.open_panel()
    assert shiboken6.isValid(new) and new is not old
    new.panel.shutdown()
    mw.deleteLater()


def test_metadata():
    assert homa_analyzer.PLUGIN_VERSION == "0.1.4"
    assert homa_analyzer.PLUGIN_CATEGORY == "Analysis"
    assert "numpy" in homa_analyzer.PLUGIN_DEPENDENCIES


def test_bond_export_all_or_selected(make_panel, tmp_path, monkeypatch):
    p, _ = make_panel(_embed("c1ccc2[nH]ccc2c1"), "GFN2-xTB")
    p.refresh()
    sizes = [r.size for r in p.results]
    target = tmp_path / "bonds"
    monkeypatch.setattr(
        panel_mod.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(target), "")),
    )
    assert p.export_bonds()
    rows = list(csv.reader((tmp_path / "bonds.csv").open(encoding="utf-8")))
    assert rows[0][0] == "# Last optimization" and rows[1][0] == "Ring"
    assert len(rows) - 2 == sum(sizes)
    p.table.selectRow(1)
    assert p.export_bonds()
    rows = list(csv.reader((tmp_path / "bonds.csv").open(encoding="utf-8")))
    assert len(rows) - 2 == sizes[1]
    assert {r[0] for r in rows[2:]} == {str(p.results[1].index)}


def test_bond_export_without_rings(make_panel, monkeypatch):
    shown = []
    monkeypatch.setattr(
        panel_mod.QMessageBox, "information", staticmethod(lambda *a: shown.append(a))
    )
    p, _ = make_panel(None)
    assert not p.export_bonds() and shown


def test_selection_highlights_rings_in_3d(make_panel):
    p, ctx = make_panel(_embed("c1ccc2[nH]ccc2c1"))
    p.show()
    p.refresh()
    assert panel_mod.HIGHLIGHT_ACTOR not in ctx.plotter.actors
    assert not p.clear_selection_button.isEnabled()
    assert "all rings" in p.selection_label.text()
    p.table.selectRow(0)
    hl = ctx.plotter.meshes[panel_mod.HIGHLIGHT_ACTOR]
    assert hl.kwargs["color"] == panel_mod.HIGHLIGHT_COLOR
    ring = p.results[0]
    lo = hl.mesh.bounds[0]
    assert lo <= min(c[0] for c in ring.coords)  # the tube wraps the ring atoms
    assert p.clear_selection_button.isEnabled()
    assert "1 ring(s) selected" in p.selection_label.text()
    ctx.plotter.clear()
    p._poll()  # a host redraw brings the highlight back
    assert panel_mod.HIGHLIGHT_ACTOR in ctx.plotter.actors
    p.clear_selection_button.click()
    assert panel_mod.HIGHLIGHT_ACTOR not in ctx.plotter.actors
    assert not p.clear_selection_button.isEnabled()


def test_unparameterized_ring_can_be_highlighted(make_panel):
    p, ctx = make_panel(_embed("C1=CC=C[SiH2]1"))
    p.show()
    p.refresh()
    p.table.selectRow(0)
    assert panel_mod.HIGHLIGHT_ACTOR in ctx.plotter.actors
    ctx.plotter.clear()
    p._poll()
    assert panel_mod.HIGHLIGHT_ACTOR in ctx.plotter.actors


def test_stale_rdkit_label_on_a_loaded_structure(make_panel):
    """The host keeps the previous molecule's label when a file is loaded."""
    p, ctx = make_panel(_benzene(), "MMFF94s (RDKit)")
    p.show()
    p.refresh()
    assert not p.warning_label.isHidden()
    ctx.current_mol = _benzene()  # loaded from a file: no host tag, same label
    p._poll()
    assert p.warning_label.isHidden()
    assert "none recorded" in p.method_label.text()


def test_plugin_label_is_dropped_when_the_structure_is_replaced(make_panel):
    mol = _benzene()
    p, ctx = make_panel(mol)
    p.show()
    p.refresh()
    ctx.mw.compute_manager.last_successful_optimization_method = "GAFF (Open Babel)"
    p._poll()  # the plugin optimized the current molecule in place
    assert "GAFF" in p.warning_label.text() and not p.warning_label.isHidden()
    ctx.current_mol = _benzene()  # then a file was loaded
    p._poll()
    assert p.warning_label.isHidden()


def test_tracker_rules():
    t = panel_mod.MethodTracker(trust_host=False)
    tagged, plain, other = _benzene(), _benzene(), _benzene()
    tagged.SetProp(panel_mod.HOST_OPT_TAG, "UFF_RDKIT")
    assert t.effective(tagged, "UFF (RDKit)") == "UFF (RDKit)"
    assert t.effective(plain, "UFF (RDKit)") is None
    assert t.effective(plain, None) is None
    assert t.effective(None, "PMEFF (v1)") is None
    assert t.effective(plain, "PMEFF (v1)") == "PMEFF (v1)"
    assert t.effective(plain, "PMEFF (v1)") == "PMEFF (v1)"
    assert t.effective(other, "PMEFF (v1)") is None
    assert t.effective(other, "GFN2-xTB") == "GFN2-xTB"
    assert t.effective(object(), "x (RDKit)") is None  # not an RDKit molecule


def test_host_5_1_2_label_is_trusted_after_redo_or_project_load(
    make_panel, monkeypatch
):
    """Undo/redo and project files drop the RDKit tag; 5.1.2 keeps the label right."""
    monkeypatch.setattr(panel_mod, "host_syncs_method", lambda version=None: True)
    untagged = _benzene()  # as rebuilt from a snapshot or a .pmeprj
    p, _ = make_panel()
    p.context.current_mol = untagged
    p.context.mw.compute_manager.last_successful_optimization_method = "MMFF94s (RDKit)"
    p.refresh()
    assert not p.warning_label.isHidden()
    assert "MMFF94s (RDKit)" in p.warning_label.text()


def test_tracker_trusting_the_host():
    t = panel_mod.MethodTracker(trust_host=True)
    a, b = _benzene(), _benzene()
    assert t.effective(a, "UFF (RDKit)") == "UFF (RDKit)"  # untagged, still trusted
    assert t.effective(b, "UFF (RDKit)") == "UFF (RDKit)"  # replaced, host said so
    assert t.effective(a, None) is None
    assert t.effective(None, "UFF (RDKit)") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5.1.2", (5, 1, 2)),
        ("5.2.0rc1", (5, 2, 0)),
        ("6.0", (6, 0)),
        ("5.1.2.dev3", (5, 1, 2)),
        ("dev", None),
    ],
)
def test_host_version_parsing(monkeypatch, text, expected):
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "version", lambda name: text)
    assert panel_mod.host_version() == expected


def test_host_version_when_not_installed(monkeypatch):
    import importlib.metadata

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert panel_mod.host_version() is None


@pytest.mark.parametrize(
    "version, syncs",
    [((5, 1, 1), False), ((5, 1, 2), True), ((5, 2, 0), True), ((6, 0), True)],
)
def test_host_syncs_method_from_5_1_2(version, syncs):
    assert _REAL_HOST_SYNCS_METHOD(version) is syncs
