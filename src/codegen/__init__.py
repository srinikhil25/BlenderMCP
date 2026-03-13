"""
Code generator package.

Responsible for turning a `GeometryPlan` into executable, Blender 4.0+-
compatible `bpy` scripts that respect the architectural rules in
`.cursorrules` (try/except wrapping, sanity checks, unit scale, etc.).
"""

