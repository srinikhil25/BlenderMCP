"""Operator: Plan & Build from prompt via local API and exec script in Blender."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import bpy


# Default URL for the plan-build API (launcher starts this)
DEFAULT_API_URL = "http://127.0.0.1:8765"


def get_api_url() -> str:
    return getattr(bpy.context.scene, "ai_scene_builder_api_url", None) or DEFAULT_API_URL


def plan_build_via_api(prompt: str, api_url: str) -> dict:
    """POST prompt to /plan_build; return parsed JSON."""
    url = f"{api_url.rstrip('/')}/plan_build"
    data = json.dumps({"prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def exec_bpy_script(script: str) -> None:
    """Run the generated bpy script in the current Blender context."""
    safe_globals = {
        "bpy": bpy,
        "math": __import__("math"),
    }
    exec(compile(script, "<plan_build>", "exec"), safe_globals)


class AI_SCENE_OT_plan_build(bpy.types.Operator):
    bl_idname = "ai_scene.plan_build"
    bl_label = "Plan & Build"
    bl_description = "Send prompt to local API, then run the generated script in Blender"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        prompt = getattr(context.scene, "ai_scene_builder_prompt", "").strip()
        if not prompt:
            self.report({"WARNING"}, "Enter a prompt first (e.g. 'Create a house with plants')")
            return {"CANCELLED"}

        api_url = get_api_url()
        try:
            result = plan_build_via_api(prompt, api_url)
        except urllib.error.URLError as e:
            self.report(
                {"ERROR"},
                "Cannot reach plan-build API. Start the launcher first (one-click app).",
            )
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        if not result.get("ok") and not result.get("script"):
            self.report({"ERROR"}, result.get("error", "Plan/build failed") or "Unknown error")
            return {"CANCELLED"}

        script = result.get("script", "")
        if not script:
            self.report({"ERROR"}, "No script returned from API")
            return {"CANCELLED"}

        try:
            exec_bpy_script(script)
        except Exception as e:
            self.report({"ERROR"}, f"Script error: {e}")
            return {"CANCELLED"}

        plan_name = result.get("plan_name", "scene")
        count = result.get("component_count", 0)
        self.report({"INFO"}, f"Built {plan_name}: {count} objects")
        return {"FINISHED"}


def register():
    bpy.types.Scene.ai_scene_builder_prompt = bpy.props.StringProperty(
        name="Prompt",
        description="Describe the scene (e.g. 'Create a house with plants')",
        default="",
        maxlen=2000,
    )
    bpy.types.Scene.ai_scene_builder_api_url = bpy.props.StringProperty(
        name="API URL",
        description="URL of the plan-build API (default: launcher)",
        default=DEFAULT_API_URL,
        maxlen=256,
    )
    bpy.utils.register_class(AI_SCENE_OT_plan_build)


def unregister():
    bpy.utils.unregister_class(AI_SCENE_OT_plan_build)
    del bpy.types.Scene.ai_scene_builder_api_url
    del bpy.types.Scene.ai_scene_builder_prompt
