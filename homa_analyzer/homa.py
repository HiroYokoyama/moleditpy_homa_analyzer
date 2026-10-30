"""HOMA (Harmonic Oscillator Model of Aromaticity) for the rings of a 3D structure.

    HOMA = 1 - (1/n) * sum_i alpha_ij * (R_opt,ij - R_i)**2

over the n bonds of a ring, with the bond-type parameters of Krygowski,
J. Chem. Inf. Comput. Sci. 1993, 33, 70-78.  For rings whose bonds are all of
one type, HOMA splits into EN + GEO (Krygowski and Cyranski, Tetrahedron 1996,
52, 1713-1722):

    EN  = alpha * (R_opt - R_av)**2              bond-length elongation
    GEO = (alpha/n) * sum_i (R_av - R_i)**2      bond-length alternation

Pure Python: the RDKit molecule is only read through its own methods.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

# (alpha, R_opt in angstrom), keyed by the alphabetically sorted element pair.
PARAMETERS: dict[tuple[str, str], tuple[float, float]] = {
    ("C", "C"): (257.7, 1.388),
    ("C", "N"): (93.52, 1.334),
    ("C", "O"): (157.38, 1.265),
    ("C", "P"): (118.91, 1.698),
    ("C", "S"): (94.09, 1.677),
    ("N", "N"): (130.33, 1.309),
    ("N", "O"): (57.21, 1.248),
}


def bond_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


@dataclass
class RingResult:
    index: int  # 1-based, as shown in the panel and the 3D labels
    atoms: list[int]  # 0-based atom indices around the ring
    symbols: list[str]
    lengths: list[float]
    center: tuple[float, float, float]
    aromatic: bool = False
    homa: float | None = None
    en: float | None = None
    geo: float | None = None
    missing: list[str] = field(default_factory=list)  # bond types without parameters

    @property
    def size(self) -> int:
        return len(self.atoms)

    @property
    def label(self) -> str:
        return "".join(self.symbols)


def _distance(p, q) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))


def ring_homa(
    symbols: Sequence[str], coords: Sequence[Sequence[float]]
) -> tuple[float | None, float | None, float | None, list[float], list[str]]:
    """HOMA, EN, GEO, bond lengths and unparameterized bond types of one ring.

    ``symbols`` and ``coords`` run around the ring in order; the last atom bonds
    back to the first.  HOMA is None when any bond type has no parameters; EN
    and GEO are None unless every bond is of the same type.
    """
    n = len(symbols)
    if n < 3 or len(coords) != n:
        raise ValueError("A ring needs at least three atoms with coordinates")
    lengths: list[float] = []
    keys: list[tuple[str, str]] = []
    for i in range(n):
        j = (i + 1) % n
        lengths.append(_distance(coords[i], coords[j]))
        keys.append(bond_key(symbols[i], symbols[j]))
    missing = sorted({f"{a}-{b}" for a, b in keys if (a, b) not in PARAMETERS})
    if missing:
        return None, None, None, lengths, missing
    dev = sum(
        PARAMETERS[k][0] * (PARAMETERS[k][1] - r) ** 2 for k, r in zip(keys, lengths)
    )
    homa = 1.0 - dev / n
    en = geo = None
    if len(set(keys)) == 1:
        alpha, r_opt = PARAMETERS[keys[0]]
        r_av = sum(lengths) / n
        en = alpha * (r_opt - r_av) ** 2
        geo = alpha / n * sum((r_av - r) ** 2 for r in lengths)
    return homa, en, geo, lengths, missing


def _ordered_ring(mol, atoms: Sequence[int]) -> list[int]:
    """Ring atoms in bonded order (RDKit's AtomRings already are; keep it explicit)."""
    ring = set(atoms)
    order = [atoms[0]]
    prev = None
    while len(order) < len(atoms):
        cur = order[-1]
        nxt = [
            nb.GetIdx()
            for nb in mol.GetAtomWithIdx(cur).GetNeighbors()
            if nb.GetIdx() in ring and nb.GetIdx() != prev and nb.GetIdx() not in order
        ]
        if not nxt:
            return list(atoms)
        prev = cur
        order.append(nxt[0])
    return order


def analyze_mol(mol) -> list[RingResult]:
    """HOMA of every ring (RDKit's SSSR) of a molecule with a 3D conformer."""
    if mol is None or mol.GetNumConformers() == 0:
        raise ValueError("No 3D structure")
    conf = mol.GetConformer()
    results: list[RingResult] = []
    for atoms in mol.GetRingInfo().AtomRings():
        order = _ordered_ring(mol, list(atoms))
        symbols = [mol.GetAtomWithIdx(i).GetSymbol() for i in order]
        coords = []
        for i in order:
            p = conf.GetAtomPosition(i)
            coords.append((p.x, p.y, p.z))
        homa, en, geo, lengths, missing = ring_homa(symbols, coords)
        center = tuple(sum(c[k] for c in coords) / len(coords) for k in range(3))
        results.append(
            RingResult(
                index=len(results) + 1,
                atoms=order,
                symbols=symbols,
                lengths=lengths,
                center=center,
                aromatic=all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in order),
                homa=homa,
                en=en,
                geo=geo,
                missing=missing,
            )
        )
    return results


# Substrings (upper case) that identify a force-field optimization label.  The
# host records labels such as "MMFF94s (RDKit)", "UFF (RDKit)",
# "Constrained_MMFF94s", "GAFF (Open Babel)" and "PMEFF (v1.0.0)".
FORCE_FIELD_MARKERS = ("MMFF", "UFF", "GAFF", "GHEMICAL", "PMEFF", "CONSTRAINED_")
UNOPTIMIZED = "Unoptimized"


def geometry_warning(method: str | None) -> str | None:
    """Warning for the last successful optimization method, or None if HOMA is meaningful."""
    if not method:
        return None
    if method == UNOPTIMIZED:
        return (
            "This 3D structure was generated without optimization. Its bond lengths "
            "are not reliable for HOMA; load or compute a quantum-chemically "
            "optimized geometry."
        )
    upper = method.upper()
    if any(marker in upper for marker in FORCE_FIELD_MARKERS):
        return (
            f"This 3D structure was optimized with a force field ({method}). "
            "Force-field bond lengths are not reliable for HOMA; load or compute a "
            "quantum-chemically optimized geometry (e.g. DFT)."
        )
    return None


CSV_HEADER = ["Ring", "Atoms", "Size", "Aromatic", "HOMA", "EN", "GEO", "Bond lengths"]


def csv_rows(results: Sequence[RingResult]) -> list[list[str]]:
    def fmt(v: float | None) -> str:
        return "" if v is None else f"{v:.4f}"

    rows = [list(CSV_HEADER)]
    for r in results:
        rows.append(
            [
                str(r.index),
                " ".join(f"{s}{i + 1}" for s, i in zip(r.symbols, r.atoms)),
                str(r.size),
                "yes" if r.aromatic else "no",
                fmt(r.homa)
                if r.homa is not None
                else "n/a (" + ", ".join(r.missing) + ")",
                fmt(r.en),
                fmt(r.geo),
                " ".join(f"{x:.4f}" for x in r.lengths),
            ]
        )
    return rows


BOND_CSV_HEADER = [
    "Ring",
    "Bond",
    "Atom 1",
    "Atom 2",
    "Type",
    "Length (A)",
    "R_opt (A)",
    "alpha",
    "alpha*(R_opt-R)^2/n",
]


def bond_rows(results: Sequence[RingResult]) -> list[list[str]]:
    """One row per ring bond, with its share of the HOMA deviation sum."""
    rows = [list(BOND_CSV_HEADER)]
    for r in results:
        n = r.size
        for k in range(n):
            a, b = r.atoms[k], r.atoms[(k + 1) % n]
            sa, sb = r.symbols[k], r.symbols[(k + 1) % n]
            length = r.lengths[k]
            params = PARAMETERS.get(bond_key(sa, sb))
            if params is None:
                alpha = r_opt = term = ""
            else:
                alpha = f"{params[0]:g}"
                r_opt = f"{params[1]:.3f}"
                term = f"{params[0] * (params[1] - length) ** 2 / n:.5f}"
            rows.append(
                [
                    str(r.index),
                    str(k + 1),
                    f"{sa}{a + 1}",
                    f"{sb}{b + 1}",
                    f"{sa}-{sb}",
                    f"{length:.4f}",
                    r_opt,
                    alpha,
                    term,
                ]
            )
    return rows
