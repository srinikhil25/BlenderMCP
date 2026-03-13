# AI Scene Builder addon – prompt in Blender, plan-build via local API, exec in Blender.

bl_info = {
    "name": "AI Scene Builder",
    "author": "BlenderMCP",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar (N) > AI Scene Builder",
    "description": "Describe a scene in text; build it with one click (uses local plan-build API).",
    "category": "Interface",
}

import bpy

from . import panel, operators


def register():
    panel.register()
    operators.register()


def unregister():
    panel.unregister()
    operators.unregister()
