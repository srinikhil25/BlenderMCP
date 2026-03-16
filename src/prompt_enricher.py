"""Prompt enrichment layer — detects domain keywords and injects precise data.

Before sending to the LLM, this module analyzes the user's prompt and
enriches it with domain-specific knowledge:
- Chemistry: fetches exact 3D coordinates from PubChem
- Architecture: adds standard proportions and dimensions
- More domains can be added here.
"""

from __future__ import annotations

import re
from typing import Optional

# Chemistry keywords that suggest molecular/crystal structures
_CHEMISTRY_KEYWORDS = [
    "molecule", "molecular", "atom", "bond", "crystal", "unit cell",
    "ball-and-stick", "ball and stick", "space-filling", "CPK",
    "H2O", "CO2", "CH4", "NH3", "C2H", "C6H", "NaCl",
    "DNA", "helix", "benzene", "methane", "ethanol", "caffeine",
    "aspirin", "glucose", "dopamine", "serotonin", "adrenaline",
    "penicillin", "cholesterol", "acetaminophen", "ibuprofen",
    "MAX phase", "Ti3AlC2", "Ti2AlC", "crystal structure",
    "tetrahedral", "octahedral", "hexagonal",
]

# Common molecule names we can look up on PubChem
_MOLECULE_NAMES = {
    "water": "water",
    "h2o": "water",
    "carbon dioxide": "carbon dioxide",
    "co2": "carbon dioxide",
    "methane": "methane",
    "ch4": "methane",
    "ammonia": "ammonia",
    "nh3": "ammonia",
    "ethanol": "ethanol",
    "benzene": "benzene",
    "caffeine": "caffeine",
    "aspirin": "aspirin",
    "glucose": "glucose",
    "dopamine": "dopamine",
    "serotonin": "serotonin",
    "adrenaline": "epinephrine",
    "epinephrine": "epinephrine",
    "acetaminophen": "acetaminophen",
    "paracetamol": "acetaminophen",
    "ibuprofen": "ibuprofen",
    "penicillin": "penicillin G",
    "cholesterol": "cholesterol",
    "acetic acid": "acetic acid",
    "sulfuric acid": "sulfuric acid",
    "nicotine": "nicotine",
    "morphine": "morphine",
    "sucrose": "sucrose",
    "urea": "urea",
    "glycine": "glycine",
    "alanine": "alanine",
    "toluene": "toluene",
    "acetone": "acetone",
    "formaldehyde": "formaldehyde",
    "methanol": "methanol",
    "propane": "propane",
    "butane": "butane",
}


def enrich_prompt(prompt: str) -> tuple[str, str]:
    """Analyze and enrich a user prompt with domain-specific data.

    Args:
        prompt: The raw user prompt.

    Returns:
        Tuple of (enriched_prompt, enrichment_log).
        enrichment_log describes what was added (for the GUI log).
    """
    lower = prompt.lower()

    # Check for chemistry content
    is_chemistry = any(kw.lower() in lower for kw in _CHEMISTRY_KEYWORDS)

    if is_chemistry:
        enriched, log = _enrich_chemistry(prompt, lower)
        if enriched != prompt:
            return enriched, log

    # No enrichment needed
    return prompt, ""


def _enrich_chemistry(prompt: str, lower: str) -> tuple[str, str]:
    """Enrich chemistry-related prompts with PubChem data."""
    # Try to find a molecule name in the prompt
    molecule_name = _detect_molecule(lower)

    if molecule_name:
        try:
            from src.pubchem import fetch_molecule, molecule_to_bpy_instructions

            mol = fetch_molecule(molecule_name)
            if mol and mol.atoms:
                instructions = molecule_to_bpy_instructions(mol)
                enriched = (
                    f"{prompt}\n\n"
                    f"=== PRECISE STRUCTURAL DATA (from PubChem) ===\n"
                    f"{instructions}\n"
                    f"=== END STRUCTURAL DATA ===\n\n"
                    f"Use the EXACT coordinates and colors from the structural data above. "
                    f"Do NOT guess positions — use the provided coordinates."
                )
                log = (
                    f"PubChem: Found {mol.formula} — "
                    f"{len(mol.atoms)} atoms, {len(mol.bonds)} bonds"
                )
                return enriched, log
        except Exception as e:
            return prompt, f"PubChem lookup failed: {e}"

    return prompt, ""


def _detect_molecule(lower: str) -> Optional[str]:
    """Try to detect a molecule name from the prompt text."""
    # Check direct name matches (longest first to avoid partial matches)
    sorted_names = sorted(_MOLECULE_NAMES.keys(), key=len, reverse=True)
    for keyword in sorted_names:
        if keyword in lower:
            return _MOLECULE_NAMES[keyword]

    # Try to extract a chemical formula pattern and look it up
    # Match patterns like C2H5OH, H2SO4, CH3COOH, etc.
    formula_match = re.search(r'\b([A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*)\b', lower)
    if formula_match:
        formula = formula_match.group(1)
        # Only try if it looks like a formula (has at least one uppercase letter)
        if len(formula) >= 2 and any(c.isupper() for c in formula):
            try:
                from src.pubchem import fetch_molecule
                mol = fetch_molecule(formula)
                if mol:
                    return formula
            except Exception:
                pass

    return None
