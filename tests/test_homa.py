"""HOMA math, ring perception and the force-field warning."""

import math

import pytest

from homa_analyzer import homa


def _hexagon(lengths):
    """Planar ring whose consecutive bonds have the given lengths (approximately regular)."""
    n = len(lengths)
    r = sum(lengths) / n / (2 * math.sin(math.pi / n))
    return [
        (r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), 0.0)
        for i in range(n)
    ]


def test_ideal_benzene_is_one():
    coords = _hexagon([1.388] * 6)
    value, en, geo, lengths, missing = homa.ring_homa(["C"] * 6, coords)
    assert lengths == pytest.approx([1.388] * 6)
    assert value == pytest.approx(1.0)
    assert en == pytest.approx(0.0, abs=1e-12) and geo == pytest.approx(0.0, abs=1e-12)
    assert missing == []


def test_published_benzene_value():
    """Krygowski & Szatylowicz, ChemTexts 2015, Table 4: HOMA 0.979, EN 0.021, GEO 0.000."""
    value, en, geo, *_ = homa.ring_homa(["C"] * 6, _hexagon([1.397] * 6))
    assert round(value, 3) == 0.979
    assert round(en, 3) == 0.021 and round(geo, 3) == 0.0


def test_uniform_elongation_is_all_en():
    coords = _hexagon([1.397] * 6)
    value, en, geo, *_ = homa.ring_homa(["C"] * 6, coords)
    expected = 1 - 257.7 * (1.388 - 1.397) ** 2
    assert value == pytest.approx(expected)
    assert en == pytest.approx(1 - expected) and geo == pytest.approx(0.0, abs=1e-12)


def test_split_holds_for_an_irregular_ring():
    coords = [
        (0, 0, 0),
        (1.34, 0, 0),
        (2.0, 1.2, 0),
        (1.4, 2.4, 0),
        (0.0, 2.4, 0),
        (-0.7, 1.2, 0),
    ]
    value, en, geo, lengths, _ = homa.ring_homa(["C"] * 6, coords)
    assert value == pytest.approx(1 - en - geo)
    assert lengths[0] == pytest.approx(1.34)
    assert lengths[-1] == pytest.approx(math.dist(coords[-1], coords[0]))


def test_mixed_bond_types_have_no_split():
    coords = _hexagon([1.36] * 6)
    value, en, geo, _, missing = homa.ring_homa(["N", "C", "C", "C", "C", "C"], coords)
    assert value is not None and en is None and geo is None and missing == []
    dev = 2 * 93.52 * (1.334 - 1.36) ** 2 + 4 * 257.7 * (1.388 - 1.36) ** 2
    assert value == pytest.approx(1 - dev / 6, rel=1e-3)


def test_unparameterized_bond_gives_none():
    value, en, geo, _, missing = homa.ring_homa(
        ["C", "C", "Si", "C", "C"], _hexagon([1.5] * 5)
    )
    assert value is None and en is None and geo is None
    assert missing == ["C-Si"]


def test_ring_needs_three_atoms():
    with pytest.raises(ValueError):
        homa.ring_homa(["C", "C"], [(0, 0, 0), (1, 0, 0)])


@pytest.mark.parametrize(
    "method, warns",
    [
        (None, False),
        ("", False),
        ("MMFF94s (RDKit)", True),
        ("MMFF94 (RDKit)", True),
        ("UFF (RDKit)", True),
        ("Constrained_MMFF94s", True),
        ("GAFF (Open Babel)", True),
        ("Ghemical (Open Babel)", True),
        ("PMEFF (v1.2.0)", True),
        ("Unoptimized", True),
        ("GFN2-xTB", False),
        ("PySCF B3LYP/def2-SVP", False),
    ],
)
def test_geometry_warning(method, warns):
    assert (homa.geometry_warning(method) is not None) is warns


def test_force_field_warning_names_the_method():
    assert "UFF (RDKit)" in homa.geometry_warning("UFF (RDKit)")


class TestWithRDKit:
    @pytest.fixture(autouse=True)
    def _rdkit(self):
        self.Chem = pytest.importorskip("rdkit.Chem")
        from rdkit.Chem import AllChem

        self.AllChem = AllChem

    def _embed(self, smiles):
        mol = self.Chem.AddHs(self.Chem.MolFromSmiles(smiles))
        assert self.AllChem.EmbedMolecule(mol, randomSeed=7) == 0
        self.AllChem.MMFFOptimizeMolecule(mol)
        return mol

    def test_naphthalene_has_two_aromatic_rings(self):
        results = homa.analyze_mol(self._embed("c1ccc2ccccc2c1"))
        assert len(results) == 2
        for r in results:
            assert r.size == 6 and r.aromatic and r.label == "CCCCCC"
            assert 0.5 < r.homa <= 1.0
            assert r.homa == pytest.approx(1 - r.en - r.geo)
            assert len(r.center) == 3

    def test_ring_order_follows_bonds(self):
        mol = self._embed("c1ccncc1")
        (r,) = homa.analyze_mol(mol)
        for a, b in zip(r.atoms, r.atoms[1:] + r.atoms[:1]):
            assert mol.GetBondBetweenAtoms(a, b) is not None
        assert r.en is None and r.homa is not None

    def test_cyclohexane_is_far_from_aromatic(self):
        (r,) = homa.analyze_mol(self._embed("C1CCCCC1"))
        assert not r.aromatic and r.homa < 0

    def test_no_conformer_raises(self):
        with pytest.raises(ValueError):
            homa.analyze_mol(self.Chem.MolFromSmiles("c1ccccc1"))
        with pytest.raises(ValueError):
            homa.analyze_mol(None)

    def test_csv_rows(self):
        results = homa.analyze_mol(self._embed("C1=CC=C[SiH2]1"))
        rows = homa.csv_rows(results)
        assert rows[0] == homa.CSV_HEADER
        assert rows[1][4].startswith("n/a (C-Si")


def test_orca_optimized_benzene():
    """B3LYP/def2-SVP benzene from an ORCA optimization: every C-C is 1.3991 A."""
    rdkit = pytest.importorskip("rdkit")
    from pathlib import Path

    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    del rdkit
    path = Path(__file__).parent / "data" / "benzene_b3lyp_def2svp.xyz"
    mol = Chem.MolFromXYZFile(str(path))
    rdDetermineBonds.DetermineBonds(mol, charge=0)
    (ring,) = homa.analyze_mol(mol)
    assert ring.size == 6 and ring.aromatic and ring.label == "CCCCCC"
    assert ring.lengths == pytest.approx([1.3991] * 6, abs=5e-5)
    assert round(ring.homa, 3) == 0.968
    assert round(ring.en, 3) == 0.032 and round(ring.geo, 6) == 0.0
    assert ring.center == pytest.approx((0.0, 0.0, 0.0), abs=1e-5)
