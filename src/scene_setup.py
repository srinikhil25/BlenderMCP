"""Auto camera, lighting, and ground plane setup for Blender scenes.

Generates a self-contained bpy script that analyzes the current scene
and adds camera, three-point lighting, ground plane, and render settings.
"""

from __future__ import annotations


def generate_camera_lighting_code() -> str:
    """Return a bpy script string that sets up camera, lights, ground, and render."""
    return _SETUP_SCRIPT


_SETUP_SCRIPT = '''\
import bpy
import mathutils

def setup_scene():
    """Add camera, lighting, ground, and render settings based on scene content."""
    try:
        # --- Compute scene bounding box (exclude ground/floor) ---
        ground_keywords = {"ground", "floor", "plane", "base"}
        scene_coords = []

        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            name_lower = obj.name.lower()
            if any(kw in name_lower for kw in ground_keywords):
                continue
            # Skip flat objects at z~0 (likely ground planes)
            dims = obj.dimensions
            if dims.z < 0.02 and abs(obj.location.z) < 0.05:
                continue
            for corner in obj.bound_box:
                world_pt = obj.matrix_world @ mathutils.Vector(corner)
                scene_coords.append(world_pt)

        if not scene_coords:
            # Fallback: use all mesh objects
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    for corner in obj.bound_box:
                        world_pt = obj.matrix_world @ mathutils.Vector(corner)
                        scene_coords.append(world_pt)

        if not scene_coords:
            center = mathutils.Vector((0, 0, 1))
            diag = 5.0
        else:
            bbox_min = mathutils.Vector((
                min(c.x for c in scene_coords),
                min(c.y for c in scene_coords),
                min(c.z for c in scene_coords),
            ))
            bbox_max = mathutils.Vector((
                max(c.x for c in scene_coords),
                max(c.y for c in scene_coords),
                max(c.z for c in scene_coords),
            ))
            center = (bbox_min + bbox_max) / 2
            diag = (bbox_max - bbox_min).length
            diag = max(diag, 2.0)  # minimum 2m diagonal

        # --- Ground plane (sized to scene footprint, not dominant) ---
        ground_size = max(diag * 1.5, 3.0)
        bpy.ops.mesh.primitive_plane_add(size=ground_size, location=(center.x, center.y, 0))
        ground = bpy.context.active_object
        ground.name = "Ground"
        ground_mat = bpy.data.materials.new("GroundMat")
        ground_mat.use_nodes = True
        bsdf = ground_mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (0.35, 0.38, 0.3, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.95
        ground.data.materials.append(ground_mat)
        # Subtle viewport display so ground doesn't dominate
        ground.display_type = 'WIRE'
        try:
            ground.is_shadow_catcher = True
        except Exception:
            pass

        # --- Camera ---
        cam_offset = mathutils.Vector((diag * 1.2, -diag * 1.2, diag * 0.7))
        cam_location = center + cam_offset
        bpy.ops.object.camera_add(location=cam_location)
        cam = bpy.context.active_object
        cam.name = "Camera"
        cam.data.lens = 50  # 50mm standard lens

        # Track-to constraint pointing at scene center
        bpy.ops.object.empty_add(location=center)
        target = bpy.context.active_object
        target.name = "CameraTarget"
        target.hide_viewport = True
        target.hide_render = True

        track = cam.constraints.new(type='TRACK_TO')
        track.target = target
        track.track_axis = 'TRACK_NEGATIVE_Z'
        track.up_axis = 'UP_Y'
        bpy.context.scene.camera = cam

        # --- Three-point lighting ---
        # Key light: Sun from upper-right-front
        bpy.ops.object.light_add(type='SUN', location=(center.x + diag, center.y - diag * 0.5, center.z + diag * 1.5))
        sun = bpy.context.active_object
        sun.name = "KeyLight"
        sun.data.energy = 3.0
        sun.data.color = (1.0, 0.95, 0.9)
        sun.rotation_euler = (0.8, 0.1, 0.6)

        # Fill light: Area from left side
        bpy.ops.object.light_add(type='AREA', location=(center.x - diag * 0.8, center.y + diag * 0.3, center.z + diag * 0.5))
        fill = bpy.context.active_object
        fill.name = "FillLight"
        fill.data.energy = 100
        fill.data.size = diag * 0.5
        fill.data.color = (0.9, 0.93, 1.0)
        fill.rotation_euler = (1.0, 0.0, -0.7)

        # Rim light: Point from behind/above
        bpy.ops.object.light_add(type='POINT', location=(center.x - diag * 0.3, center.y + diag, center.z + diag * 0.8))
        rim = bpy.context.active_object
        rim.name = "RimLight"
        rim.data.energy = 200
        rim.data.color = (1.0, 1.0, 1.0)

        # --- Render settings ---
        scene = bpy.context.scene
        # Blender 5.0+: EEVEE_NEXT was renamed back to BLENDER_EEVEE
        try:
            scene.render.engine = 'BLENDER_EEVEE'
        except Exception:
            try:
                scene.render.engine = 'BLENDER_EEVEE_NEXT'
            except Exception:
                pass
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080

        try:
            scene.eevee.use_gtao = True
            scene.eevee.gtao_distance = 1.0
            scene.eevee.use_ssr = True
            scene.eevee.use_ssr_refraction = True
        except Exception:
            pass

        try:
            scene.view_settings.view_transform = 'Filmic'
            scene.view_settings.look = 'Medium High Contrast'
        except Exception:
            pass

        scene.render.film_transparent = False

        # --- World environment (gradient sky) ---
        world = bpy.data.worlds.get("World")
        if not world:
            world = bpy.data.worlds.new("World")
        scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        nodes.clear()

        bg = nodes.new('ShaderNodeBackground')
        bg.inputs['Strength'].default_value = 1.0
        output = nodes.new('ShaderNodeOutputWorld')
        output.location = (300, 0)

        # Sky gradient: mix light blue top with white horizon
        mix = nodes.new('ShaderNodeMixRGB')
        mix.location = (-200, 0)
        mix.inputs[1].default_value = (0.85, 0.92, 1.0, 1.0)  # horizon white-blue
        mix.inputs[2].default_value = (0.4, 0.6, 0.9, 1.0)    # zenith blue

        coord = nodes.new('ShaderNodeTexCoord')
        coord.location = (-600, 0)
        sep = nodes.new('ShaderNodeSeparateXYZ')
        sep.location = (-400, 0)

        links.new(coord.outputs['Generated'], sep.inputs['Vector'])
        links.new(sep.outputs['Z'], mix.inputs['Fac'])
        links.new(mix.outputs['Color'], bg.inputs['Color'])
        links.new(bg.outputs['Background'], output.inputs['Surface'])

        # --- Frame viewport ---
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.name != "Ground":
                    obj.select_set(True)
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            with bpy.context.temp_override(area=area, region=region):
                                bpy.ops.view3d.view_selected()
                            break
                    break
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            pass

        print("SUCCESS: Camera, lighting, and ground added")

    except Exception as e:
        print(f"ERROR in scene setup: {e}")
        raise

setup_scene()
'''
