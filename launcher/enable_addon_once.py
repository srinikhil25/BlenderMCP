"""
Blender startup script: enable AI Scene Builder addon and save preferences.

Run Blender with: blender -P enable_addon_once.py

Then Blender continues to open as usual; on first run the addon is enabled.
"""

import bpy
import addon_utils

# Enable by module name (folder name in addons)
MODULE = "addon_ai_scene"
if not addon_utils.check(MODULE)[1]:
    addon_utils.enable(MODULE, default_set=True)
    bpy.ops.wm.save_userpref()
    print("AI Scene Builder addon enabled and preferences saved.")
