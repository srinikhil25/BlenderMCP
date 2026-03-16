"""PubChem integration — fetch 3D molecular structures for accurate chemistry scenes.

Uses the PubChem PUG REST API (free, no auth needed) to get exact 3D atom
coordinates, bond information, and element data for any molecule by name.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# Element data: symbol -> (name, CPK color RGB 0-1, covalent radius in Angstroms)
ELEMENT_DATA = {
    "H":  ("Hydrogen",  (1.0, 1.0, 1.0),     0.31),
    "He": ("Helium",    (0.85, 1.0, 1.0),     0.28),
    "C":  ("Carbon",    (0.15, 0.15, 0.15),   0.76),
    "N":  ("Nitrogen",  (0.12, 0.31, 0.94),   0.71),
    "O":  ("Oxygen",    (0.85, 0.05, 0.05),   0.66),
    "F":  ("Fluorine",  (0.56, 0.88, 0.31),   0.57),
    "Na": ("Sodium",    (0.67, 0.36, 0.95),   1.66),
    "Mg": ("Magnesium", (0.54, 1.0, 0.0),     1.41),
    "Al": ("Aluminum",  (0.75, 0.65, 0.65),   1.21),
    "Si": ("Silicon",   (0.94, 0.78, 0.63),   1.11),
    "P":  ("Phosphorus",(1.0, 0.5, 0.0),      1.07),
    "S":  ("Sulfur",    (1.0, 1.0, 0.19),     1.05),
    "Cl": ("Chlorine",  (0.12, 0.94, 0.12),   1.02),
    "K":  ("Potassium", (0.56, 0.25, 0.83),   2.03),
    "Ca": ("Calcium",   (0.24, 1.0, 0.0),     1.76),
    "Ti": ("Titanium",  (0.75, 0.76, 0.78),   1.60),
    "Fe": ("Iron",      (0.88, 0.40, 0.20),   1.52),
    "Cu": ("Copper",    (0.78, 0.50, 0.20),   1.32),
    "Zn": ("Zinc",      (0.49, 0.50, 0.69),   1.22),
    "Br": ("Bromine",   (0.65, 0.16, 0.16),   1.20),
    "Ag": ("Silver",    (0.75, 0.75, 0.75),   1.45),
    "I":  ("Iodine",    (0.58, 0.0, 0.58),    1.39),
    "Au": ("Gold",      (1.0, 0.82, 0.14),    1.36),
}

# Fallback for unknown elements
_DEFAULT_ELEMENT = ("Unknown", (0.5, 0.5, 0.5), 1.0)


@dataclass
class Atom:
    index: int
    element: str
    x: float
    y: float
    z: float
    color: Tuple[float, float, float] = (0.5, 0.5, 0.5)
    radius: float = 0.3  # display radius in Blender units


@dataclass
class Bond:
    atom1_idx: int
    atom2_idx: int
    order: int = 1  # 1=single, 2=double, 3=triple


@dataclass
class Molecule:
    name: str
    formula: str
    atoms: List[Atom] = field(default_factory=list)
    bonds: List[Bond] = field(default_factory=list)


def fetch_molecule(name: str) -> Optional[Molecule]:
    """Fetch 3D structure from PubChem by molecule name.

    Args:
        name: Common or IUPAC name (e.g., "caffeine", "aspirin", "water")

    Returns:
        Molecule with 3D coordinates, or None if not found.
    """
    # Clean up name for URL
    query = name.strip().replace(" ", "%20")
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/JSON?record_type=3d"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BlenderMCP/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception:
        return None

    try:
        compound = data["PC_Compounds"][0]
        return _parse_compound(name, compound)
    except (KeyError, IndexError):
        return None


def _parse_compound(name: str, compound: dict) -> Molecule:
    """Parse PubChem compound JSON into our Molecule dataclass."""
    # Extract atoms
    atoms_section = compound.get("atoms", {})
    elements_list = atoms_section.get("element", [])
    aid_list = atoms_section.get("aid", [])

    # Extract 3D coordinates from first conformer
    coords = compound.get("coords", [{}])[0]
    conformers = coords.get("conformers", [{}])[0]
    xs = conformers.get("x", [])
    ys = conformers.get("y", [])
    zs = conformers.get("z", [])

    # Map PubChem element numbers to symbols
    ATOMIC_SYMBOLS = {
        1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O",
        9: "F", 10: "Ne", 11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P",
        16: "S", 17: "Cl", 18: "Ar", 19: "K", 20: "Ca", 22: "Ti", 26: "Fe",
        29: "Cu", 30: "Zn", 35: "Br", 47: "Ag", 53: "I", 79: "Au",
    }

    atoms = []
    for i, (aid, elem_num) in enumerate(zip(aid_list, elements_list)):
        symbol = ATOMIC_SYMBOLS.get(elem_num, "?")
        elem_info = ELEMENT_DATA.get(symbol, _DEFAULT_ELEMENT)

        x = xs[i] if i < len(xs) else 0
        y = ys[i] if i < len(ys) else 0
        z = zs[i] if i < len(zs) else 0

        # Scale: PubChem uses Angstroms, we use ~0.3m per Angstrom for visibility
        scale = 0.3
        atoms.append(Atom(
            index=aid,
            element=symbol,
            x=x * scale,
            y=y * scale,
            z=z * scale,
            color=elem_info[1],
            radius=elem_info[2] * 0.15,  # scale covalent radius for display
        ))

    # Extract bonds
    bonds_section = compound.get("bonds", {})
    aid1_list = bonds_section.get("aid1", [])
    aid2_list = bonds_section.get("aid2", [])
    order_list = bonds_section.get("order", [])

    bonds = []
    for i, (a1, a2) in enumerate(zip(aid1_list, aid2_list)):
        order = order_list[i] if i < len(order_list) else 1
        bonds.append(Bond(atom1_idx=a1, atom2_idx=a2, order=order))

    # Get molecular formula
    props = compound.get("props", [])
    formula = name
    for prop in props:
        urn = prop.get("urn", {})
        if urn.get("label") == "Molecular Formula":
            formula = prop.get("value", {}).get("sval", name)
            break

    return Molecule(name=name, formula=formula, atoms=atoms, bonds=bonds)


def molecule_to_bpy_instructions(mol: Molecule) -> str:
    """Convert a Molecule into precise instructions for the LLM prompt.

    Returns a text block with exact atom positions, colors, and bond connections
    that the LLM can use to generate accurate bpy code.
    """
    lines = [
        f"MOLECULAR STRUCTURE DATA for {mol.name} ({mol.formula}):",
        f"Total atoms: {len(mol.atoms)}, Total bonds: {len(mol.bonds)}",
        "",
        "ATOMS (create a sphere for each):",
    ]

    # Group atoms by element for clarity
    by_element: dict[str, list[Atom]] = {}
    for atom in mol.atoms:
        by_element.setdefault(atom.element, []).append(atom)

    for elem, atoms in by_element.items():
        elem_info = ELEMENT_DATA.get(elem, _DEFAULT_ELEMENT)
        lines.append(f"  {elem} ({elem_info[0]}): color=({atoms[0].color[0]:.2f}, {atoms[0].color[1]:.2f}, {atoms[0].color[2]:.2f}), "
                     f"display_radius={atoms[0].radius:.3f}m, count={len(atoms)}")

    lines.append("")
    lines.append("EXACT ATOM POSITIONS (index, element, x, y, z):")
    for atom in mol.atoms:
        lines.append(f"  Atom {atom.index}: {atom.element} at ({atom.x:.4f}, {atom.y:.4f}, {atom.z:.4f})")

    lines.append("")
    lines.append("BONDS (draw a cylinder between each pair):")
    lines.append("  Bond cylinder radius: 0.015m")
    for bond in mol.bonds:
        order_str = {1: "single", 2: "double", 3: "triple"}.get(bond.order, "single")
        lines.append(f"  Bond: Atom {bond.atom1_idx} -- Atom {bond.atom2_idx} ({order_str})")

    lines.append("")
    lines.append("INSTRUCTIONS:")
    lines.append("- Create each atom as a UV sphere at the EXACT coordinates above")
    lines.append("- Use the EXACT colors specified (CPK coloring)")
    lines.append("- Create bonds as thin cylinders connecting atom centers")
    lines.append("- For bond cylinder: calculate midpoint, length, and rotation between two atom positions")
    lines.append("- Use smooth shading on all atoms")
    lines.append("- Center the molecule above ground (shift all z coordinates up by 0.5m)")

    return "\n".join(lines)
