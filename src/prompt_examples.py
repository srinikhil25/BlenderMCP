"""Curated example prompts for BlenderMCP, grouped by difficulty."""

from __future__ import annotations

EXAMPLES: dict[str, list[str]] = {
    "Simple": [
        "A red apple on a wooden table",
        "A snowman with a top hat and scarf",
        "A wooden chair with armrests",
        "A stack of three books on a shelf",
    ],
    "Intermediate": [
        "A desk with a computer monitor, keyboard, and coffee mug",
        "A park bench under a street lamp at night",
        "A Japanese torii gate with stone lanterns",
        "A campfire surrounded by logs with a tent nearby",
    ],
    "Complex": [
        "A medieval castle tower with a wooden door and wall torches",
        "A living room with couch, coffee table, floor lamp, and TV on a stand",
        "A lighthouse on a rocky cliff overlooking the sea",
        "A low-poly mountain landscape with pine trees and a cabin",
    ],
    "Chemistry": [
        "A water molecule H2O in ball-and-stick model with red oxygen and white hydrogen",
        "A methane molecule CH4 in tetrahedral ball-and-stick model",
        "A DNA double helix with two colored strands",
        "A chemistry lab with Erlenmeyer flask, test tubes, and Bunsen burner",
    ],
}


def get_all_examples() -> list[str]:
    """Return a flat list of all example prompts."""
    return [prompt for group in EXAMPLES.values() for prompt in group]


def get_categories() -> list[str]:
    """Return category names."""
    return list(EXAMPLES.keys())
