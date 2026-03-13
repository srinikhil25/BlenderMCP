"""
Blender `bpy` code generator.

Consumes `GeometryPlan` instances from the planner layer and produces
Python source strings that can be executed inside Blender (via Blender MCP).
"""

from typing import Protocol

from src.planner.geometry_planner import GeometryPlan


class CodeGenerator(Protocol):
    """Protocol for code generators that map plans to bpy scripts."""

    def generate(self, plan: GeometryPlan) -> str:  # pragma: no cover - protocol
        ...


def generate_bpy_script(plan: GeometryPlan) -> str:
    """
    Stub implementation that returns a minimal, rules-compliant bpy script.

    The script:
    - Sets unit scale to meters
    - Creates a simple cube as a placeholder structure
    - Wraps all logic in try/except
    - Includes a basic sanity check.
    """
    return f'''import bpy
import bmesh

def sanity_check(obj):
    if obj is None:
        raise ValueError("No object created")
    if obj.dimensions.length == 0:
        raise ValueError("Object has zero volume or dimensions")


def build():
    try:
        scene = bpy.context.scene
        scene.unit_settings.scale_length = {plan.parameters.get("unit_scale", 1.0)}

        mesh = bpy.data.meshes.new("{plan.name}_mesh")
        obj = bpy.data.objects.new("{plan.name}", mesh)
        scene.collection.objects.link(obj)

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(mesh)
        bm.free()

        sanity_check(obj)
        return obj
    except Exception as e:
        print("Error while building structure:", e)
        raise


if __name__ == "__main__":
    build()
'''

