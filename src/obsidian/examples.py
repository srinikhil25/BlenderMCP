"""Example prompts for Obsidian note generation."""

from __future__ import annotations

from collections import OrderedDict

EXAMPLES: OrderedDict[str, list[str]] = OrderedDict({
    "Knowledge Notes": [
        "Explain quantum computing: qubits, superposition, and entanglement",
        "Overview of machine learning: supervised, unsupervised, and reinforcement learning",
        "History of the internet from ARPANET to modern web",
        "How photosynthesis works at the molecular level",
    ],
    "Study & Research": [
        "Research note: recent advances in CRISPR gene editing (2024-2025)",
        "Cornell notes on the theory of relativity",
        "Zettelkasten note: The concept of emergence in complex systems",
        "Compare and contrast: SQL vs NoSQL databases",
    ],
    "Project & Planning": [
        "Meeting notes template for a weekly sprint review",
        "Project plan: Building a personal knowledge base",
        "Decision matrix: Choosing a programming language for a new project",
        "Brainstorm: Ideas for a mobile app that helps with habit tracking",
    ],
    "Creative & Writing": [
        "Character profile for a sci-fi novel protagonist",
        "World-building notes for a fantasy setting with floating islands",
        "Recipe note: Traditional Japanese ramen with detailed steps",
        "Travel planning notes for a 2-week trip to Japan",
    ],
    "Topic Clusters": [
        "Machine Learning — from basics to deep learning",
        "Ancient Rome — politics, culture, engineering, and legacy",
        "Web Development — frontend, backend, and DevOps",
        "Climate Change — science, impacts, and solutions",
        "Human Psychology — cognition, behavior, and mental health",
        "Blockchain Technology — crypto, smart contracts, and DeFi",
    ],
})
