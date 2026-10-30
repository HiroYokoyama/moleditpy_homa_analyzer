# HOMA Analyzer

[![CI](https://github.com/HiroYokoyama/moleditpy_homa_analyzer/actions/workflows/test.yml/badge.svg)](https://github.com/HiroYokoyama/moleditpy_homa_analyzer/actions/workflows/test.yml)
[![GitHub tag](https://img.shields.io/github/v/tag/HiroYokoyama/moleditpy_homa_analyzer?label=version)](https://github.com/HiroYokoyama/moleditpy_homa_analyzer/tags)
![License](https://img.shields.io/badge/license-LGPL--3.0--or--later-blue)

A [MoleditPy](https://github.com/HiroYokoyama/python_molecular_editor) plugin that computes the
**HOMA** (Harmonic Oscillator Model of Aromaticity) index of every ring in the 3D structure. It
shows the value at each ring center in the 3D view, lists the rings in a panel on the right, and
exports the list as CSV.

## Usage

1. Build or load a structure and show it in 3D. Use a quantum-chemically optimized geometry (see
   [Geometry warning](#geometry-warning)).
2. Choose **Analysis ▸ HOMA Analyzer**. A panel opens on the right of the main window.
3. Read the values in the panel or at the ring centers in the 3D view. The panel recalculates
   automatically when the structure is redrawn or re-optimized. **Recalculate** forces it.
4. **Export CSV...** saves the list.

| Column | Meaning |
| :--- | :--- |
| Ring | Ring number, also used for the 3D label |
| Atoms | Ring atoms in bonded order, with 1-based atom numbers |
| Size | Number of ring atoms |
| HOMA | The HOMA index; *n/a* when a ring bond has no parameters (the tooltip names it) |
| EN, GEO | The decomposition HOMA = 1 − EN − GEO, for rings whose bonds are all of one type |

The CSV file also records the aromaticity flag from RDKit, every ring bond length and, in its
first lines, the last optimization method and the geometry warning.

## 3D labels

The **3D labels** box in the panel sets how the values appear at the ring centers. Changes apply
immediately and are kept for later sessions.

| Setting | Default |
| :--- | :--- |
| Show HOMA at ring centers | On |
| Color | `#d03000` |
| Font | Arial (Courier and Times are also available) |
| Size | 18 pt |
| Bold | On |
| Decimals | 3 (also used in the table) |

## Geometry warning

HOMA is computed from bond lengths, so it is only as good as the geometry. The panel reads the
method MoleditPy recorded for the last successful optimization of the structure, and shows a
warning when that method is a force field (MMFF94, MMFF94s, UFF, GAFF, Ghemical, PMEFF or a
constrained force-field optimization) or when the structure was embedded without optimization.
Force fields reproduce conjugated bond lengths only roughly, which shifts HOMA noticeably. No
warning is shown for structures loaded from a file, or optimized by a quantum-chemical plugin.

## Method

For a ring of *n* bonds,

HOMA = 1 − (1/*n*) Σ α<sub>j</sub> (R<sub>opt,j</sub> − R<sub>i</sub>)²

where R<sub>i</sub> are the ring bond lengths and α<sub>j</sub>, R<sub>opt,j</sub> are the
parameters of the bond type *j*. HOMA is 1 for a ring whose bonds all have the optimal aromatic
length, and 0 for a hypothetical Kekulé structure. Negative values indicate antiaromatic or
strongly alternating rings.

Rings are RDKit's smallest set of smallest rings. Bond lengths come from the 3D coordinates,
including bonds that RDKit does not mark as aromatic.

### Parameters

| Bond | α | R<sub>opt</sub> (Å) |
| :--- | ---: | ---: |
| C–C | 257.7 | 1.388 |
| C–N | 93.52 | 1.334 |
| C–O | 157.38 | 1.265 |
| C–P | 118.91 | 1.698 |
| C–S | 94.09 | 1.677 |
| N–N | 130.33 | 1.309 |
| N–O | 57.21 | 1.248 |

These are the parameters of Krygowski (1993) [1], as tabulated in the review by Krygowski and
Szatyłowicz [3]. Rings containing any other bond (for example C–Si, B–N or C–Se) show *n/a*.

For rings whose bonds are all of one type, HOMA is split into an energetic and a geometric term
[2]:

EN = α (R<sub>opt</sub> − R<sub>av</sub>)², GEO = (α/*n*) Σ (R<sub>av</sub> − R<sub>i</sub>)²,
HOMA = 1 − EN − GEO

EN measures how far the mean bond length is from the optimal value, and GEO measures bond-length
alternation. For rings with mixed bond types, EN and GEO are left empty.

### Validation

The formula, every parameter, the EN/GEO split and the citations below were checked independently
against the literature and Crossref DOI records. The test suite reproduces the published value
for benzene with all C–C bonds at 1.397 Å: HOMA 0.979, EN 0.021, GEO 0.000 ([3], Table 4).

### References

1. Krygowski, T. M. Crystallographic Studies of Inter- and Intramolecular Interactions Reflected
   in Aromatic Character of π-Electron Systems. *J. Chem. Inf. Comput. Sci.* **1993**, *33* (1),
   70–78. <https://doi.org/10.1021/ci00011a011>
2. Krygowski, T. M.; Cyrański, M. Separation of the Energetic and Geometric Contributions to the
   Aromaticity of π-Electron Carbocyclics. *Tetrahedron* **1996**, *52* (5), 1713–1722.
   <https://doi.org/10.1016/0040-4020(95)01007-6>
3. Krygowski, T. M.; Szatyłowicz, H. Aromaticity: What Does It Mean? *ChemTexts* **2015**, *1* (3),
   12. <https://doi.org/10.1007/s40828-015-0012-2>
4. Krygowski, T. M.; Szatyłowicz, H.; Stasyuk, O. A.; Dominikowska, J.; Palusiak, M. Aromaticity
   from the Viewpoint of Molecular Geometry: Application to Planar Systems. *Chem. Rev.* **2014**,
   *114* (12), 6383–6422. <https://doi.org/10.1021/cr400252h>
5. Andrzejak, M.; Kubisiak, P.; Zborowski, K. K. Avoiding Pitfalls of a Theoretical Approach: The
   Harmonic Oscillator Measure of Aromaticity Index from Quantum Chemistry Calculations.
   *Struct. Chem.* **2013**, *24* (4), 1171–1184. <https://doi.org/10.1007/s11224-012-0148-2>

Reference [5] shows how strongly HOMA depends on the method used to obtain the geometry, which is
the reason for the [geometry warning](#geometry-warning).

## Installation

Install it from the Plugin Installer in MoleditPy, or copy the `homa_analyzer` folder into the
MoleditPy plugin directory. It needs no packages beyond MoleditPy itself.

## Development

```bash
python -m pytest tests -v
```

The tests use RDKit and PySide6 (offscreen). The API test checks every host access against the
MoleditPy source when `python_molecular_editor` is checked out next to this repository.

## License

LGPL-3.0-or-later. See [LICENSE](LICENSE), [COPYING](COPYING) and [LICENSING.md](LICENSING.md).
