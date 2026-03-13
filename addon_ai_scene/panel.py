"""Sidebar panel for AI Scene Builder."""

import bpy


class AI_SCENE_PT_main(bpy.types.Panel):
    bl_label = "AI Scene Builder"
    bl_idname = "AI_SCENE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Scene Builder"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "ai_scene_builder_prompt", text="")
        layout.operator("ai_scene.plan_build", text="Plan & Build", icon="MOD_BUILD")
        layout.separator()
        layout.label(text="API (launcher):")
        layout.prop(scene, "ai_scene_builder_api_url", text="")


def register():
    bpy.utils.register_class(AI_SCENE_PT_main)


def unregister():
    bpy.utils.unregister_class(AI_SCENE_PT_main)
