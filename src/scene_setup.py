"""Auto camera, lighting, and ground plane setup for Blender scenes.

Generates a self-contained bpy script that analyzes the current scene
and adds camera, three-point lighting, ground plane, and render settings.
Supports both Cycles (photorealistic) and EEVEE (fast preview).
"""

from __future__ import annotations


def generate_camera_lighting_code(renderer: str = "cycles", quality: str = "standard") -> str:
    """Return a bpy script string that sets up camera, lights, ground, and render.

    Args:
        renderer: 'cycles' for photorealistic, 'eevee' for fast preview.
        quality: 'draft', 'standard', or 'high' — controls samples, bounces, etc.
    """
    from src.config import QUALITY_PRESETS
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["standard"])
    code = _SETUP_SCRIPT.replace("__RENDERER__", renderer)
    code = code.replace("__SAMPLES__", str(preset["samples"]))
    code = code.replace("__PREVIEW_SAMPLES__", str(max(preset["samples"] // 4, 16)))
    code = code.replace("__BOUNCES__", str(preset["bounces"]))
    code = code.replace("__DIFFUSE_BOUNCES__", str(preset["bounces"] // 2))
    code = code.replace("__GLOSSY_BOUNCES__", str(preset["bounces"] // 2))
    code = code.replace("__DENOISER__", str(preset["denoiser"]))
    code = code.replace("__RESOLUTION_PCT__", str(preset["resolution_pct"]))
    return code


_SETUP_SCRIPT = '''\
import bpy
import mathutils
import math

RENDERER = "__RENDERER__"  # "cycles" or "eevee"

def setup_scene():
    """Add camera, lighting, ground, and render settings based on scene content.
    Safe to call multiple times — removes old setup objects first."""
    try:
        # --- Remove previous setup objects (safe for re-runs / modify mode) ---
        setup_names = {"Ground", "Camera", "CameraTarget", "KeyLight", "FillLight", "RimLight"}
        for name in setup_names:
            obj = bpy.data.objects.get(name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)

        # --- Compute scene bounding box (exclude ground/floor/infra) ---
        skip_keywords = {"ground", "floor", "plane", "base", "camera", "light",
                         "sun", "keylight", "filllight", "rimlight", "target"}
        scene_coords = []

        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            name_lower = obj.name.lower()
            if any(kw in name_lower for kw in skip_keywords):
                continue
            # Skip flat objects at z~0 (likely ground planes)
            dims = obj.dimensions
            if dims.z < 0.02 and abs(obj.location.z) < 0.05:
                continue
            for corner in obj.bound_box:
                world_pt = obj.matrix_world @ mathutils.Vector(corner)
                scene_coords.append(world_pt)

        if not scene_coords:
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
            diag = max(diag, 0.5)

        # =========================================================
        # GROUND PLANE — procedural PBR material
        # =========================================================
        ground_size = max(diag * 3.0, 3.0)
        bpy.ops.mesh.primitive_plane_add(size=ground_size, location=(center.x, center.y, 0))
        ground = bpy.context.active_object
        ground.name = "Ground"

        # Procedural ground material (subtle concrete/studio floor look)
        gmat = bpy.data.materials.new("GroundPBR")
        gmat.use_nodes = True
        gnodes = gmat.node_tree.nodes
        glinks = gmat.node_tree.links
        gbsdf = gnodes["Principled BSDF"]

        # Base color: warm gray
        gbsdf.inputs["Base Color"].default_value = (0.28, 0.27, 0.26, 1.0)
        gbsdf.inputs["Roughness"].default_value = 0.85
        gbsdf.inputs["Metallic"].default_value = 0.0

        # Add subtle noise to roughness for realism
        noise = gnodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 8.0
        noise.inputs['Detail'].default_value = 6.0
        noise.inputs['Roughness'].default_value = 0.6
        noise.location = (gbsdf.location.x - 400, gbsdf.location.y - 200)

        # Map noise to slight roughness variation
        map_range = gnodes.new('ShaderNodeMapRange')
        map_range.inputs['From Min'].default_value = 0.0
        map_range.inputs['From Max'].default_value = 1.0
        map_range.inputs['To Min'].default_value = 0.75
        map_range.inputs['To Max'].default_value = 0.95
        map_range.location = (gbsdf.location.x - 200, gbsdf.location.y - 200)

        glinks.new(noise.outputs['Fac'], map_range.inputs['Value'])
        glinks.new(map_range.outputs['Result'], gbsdf.inputs['Roughness'])

        # Subtle bump for surface texture
        bump = gnodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = 0.03
        bump.inputs['Distance'].default_value = 0.01
        bump.location = (gbsdf.location.x - 200, gbsdf.location.y - 400)

        noise2 = gnodes.new('ShaderNodeTexNoise')
        noise2.inputs['Scale'].default_value = 20.0
        noise2.inputs['Detail'].default_value = 8.0
        noise2.location = (gbsdf.location.x - 400, gbsdf.location.y - 400)

        glinks.new(noise2.outputs['Fac'], bump.inputs['Height'])
        glinks.new(bump.outputs['Normal'], gbsdf.inputs['Normal'])

        ground.data.materials.append(gmat)
        ground.display_type = 'WIRE'
        try:
            ground.is_shadow_catcher = True
        except Exception:
            pass

        # =========================================================
        # CAMERA — adaptive framing (handles objects in any quadrant)
        # =========================================================
        # Compute max extent from center to ensure ALL objects are visible
        if scene_coords:
            max_extent = max(
                max(abs(c.x - center.x) for c in scene_coords),
                max(abs(c.y - center.y) for c in scene_coords),
                max(abs(c.z - center.z) for c in scene_coords),
            )
        else:
            max_extent = diag / 2

        # Camera distance based on the larger of diag or max single-axis extent
        # This ensures objects far from center in any direction are captured
        cam_radius = max(diag, max_extent * 2.0)
        dist_mult = 1.8 if cam_radius > 1.0 else 2.5
        cam_dist = cam_radius * dist_mult

        # Position camera at 45° azimuth, 30° elevation from center
        # Using spherical coordinates so it works regardless of where objects are
        azimuth = math.radians(45)
        elevation = math.radians(30)
        cam_offset = mathutils.Vector((
            cam_dist * math.cos(elevation) * math.cos(azimuth),
            cam_dist * math.cos(elevation) * math.sin(azimuth),
            cam_dist * math.sin(elevation),
        ))
        cam_location = center + cam_offset
        bpy.ops.object.camera_add(location=cam_location)
        cam = bpy.context.active_object
        cam.name = "Camera"
        cam.data.lens = 85 if cam_radius < 1.0 else 50

        # Depth of field for photorealism (subtle)
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = 5.6 if cam_radius > 1.0 else 2.8
        cam.data.dof.focus_distance = (cam_location - center).length

        # Track-to constraint
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

        # Set DOF focus to target
        cam.data.dof.focus_object = target

        # =========================================================
        # LIGHTING — studio three-point + environment
        # =========================================================
        # Key light: Sun (warm, strong, directional)
        bpy.ops.object.light_add(
            type='SUN',
            location=(center.x + diag, center.y - diag * 0.5, center.z + diag * 1.5)
        )
        sun = bpy.context.active_object
        sun.name = "KeyLight"
        sun.data.energy = 4.0
        sun.data.color = (1.0, 0.95, 0.88)
        sun.data.angle = math.radians(2.0)  # soft sun shadows
        sun.rotation_euler = (0.8, 0.1, 0.6)

        # Fill light: Area (cool, softer)
        fill_dist = max(diag * 0.8, 0.5)
        bpy.ops.object.light_add(
            type='AREA',
            location=(center.x - fill_dist, center.y + fill_dist * 0.4, center.z + fill_dist * 0.6)
        )
        fill = bpy.context.active_object
        fill.name = "FillLight"
        fill.data.energy = max(30, diag * diag * 20)
        fill.data.size = max(diag * 0.6, 0.4)
        fill.data.color = (0.85, 0.9, 1.0)
        fill.rotation_euler = (1.0, 0.0, -0.7)

        # Rim light: Point (backlight for edge definition)
        rim_dist = max(diag * 0.5, 0.3)
        bpy.ops.object.light_add(
            type='POINT',
            location=(center.x - rim_dist * 0.3, center.y + rim_dist * 1.2, center.z + rim_dist * 1.0)
        )
        rim = bpy.context.active_object
        rim.name = "RimLight"
        rim.data.energy = max(60, diag * diag * 30)
        rim.data.color = (1.0, 0.98, 0.95)
        rim.data.shadow_soft_size = 0.5  # soft shadows

        # =========================================================
        # RENDER ENGINE
        # =========================================================
        scene = bpy.context.scene

        if RENDERER == "cycles":
            scene.render.engine = 'CYCLES'

            # GPU if available, else CPU
            prefs = bpy.context.preferences.addons.get('cycles')
            if prefs:
                try:
                    prefs.preferences.compute_device_type = 'CUDA'
                    bpy.context.preferences.addons['cycles'].preferences.get_devices()
                    for device in prefs.preferences.devices:
                        device.use = True
                    scene.cycles.device = 'GPU'
                except Exception:
                    scene.cycles.device = 'CPU'

            # Quality settings (from preset: draft / standard / high)
            scene.cycles.samples = __SAMPLES__
            scene.cycles.preview_samples = __PREVIEW_SAMPLES__
            scene.cycles.use_denoising = __DENOISER__
            try:
                scene.cycles.denoiser = 'OPENIMAGEDENOISE'
            except Exception:
                pass

            # Light paths for realism
            scene.cycles.max_bounces = __BOUNCES__
            scene.cycles.diffuse_bounces = __DIFFUSE_BOUNCES__
            scene.cycles.glossy_bounces = __GLOSSY_BOUNCES__
            scene.cycles.transmission_bounces = __BOUNCES__
            scene.cycles.transparent_max_bounces = __BOUNCES__
            scene.cycles.caustics_reflective = False
            scene.cycles.caustics_refractive = False

            # Film
            scene.cycles.film_exposure = 1.0
            scene.render.film_transparent = False

        else:
            # EEVEE fallback (fast)
            try:
                scene.render.engine = 'BLENDER_EEVEE'
            except Exception:
                try:
                    scene.render.engine = 'BLENDER_EEVEE_NEXT'
                except Exception:
                    pass
            try:
                scene.eevee.use_gtao = True
                scene.eevee.gtao_distance = 1.0
                scene.eevee.use_ssr = True
                scene.eevee.use_ssr_refraction = True
            except Exception:
                pass

        # Resolution
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = __RESOLUTION_PCT__

        # Color management — Filmic for photorealism
        try:
            scene.view_settings.view_transform = 'Filmic'
            scene.view_settings.look = 'Medium High Contrast'
            scene.view_settings.exposure = 0.0
            scene.view_settings.gamma = 1.0
        except Exception:
            pass

        # =========================================================
        # WORLD — procedural sky environment
        # =========================================================
        world = bpy.data.worlds.get("World")
        if not world:
            world = bpy.data.worlds.new("World")
        scene.world = world
        world.use_nodes = True
        wnodes = world.node_tree.nodes
        wlinks = world.node_tree.links
        wnodes.clear()

        # Sky Texture node (physically-based sky) for Cycles
        if RENDERER == "cycles":
            try:
                sky = wnodes.new('ShaderNodeTexSky')
                sky.sky_type = 'NISHITA'
                sky.sun_elevation = math.radians(30)
                sky.sun_rotation = math.radians(45)
                sky.altitude = 0
                sky.air_density = 1.0
                sky.dust_density = 0.5
                sky.ozone_density = 1.0
                sky.location = (-400, 0)

                bg = wnodes.new('ShaderNodeBackground')
                bg.inputs['Strength'].default_value = 1.2
                bg.location = (0, 0)

                output = wnodes.new('ShaderNodeOutputWorld')
                output.location = (300, 0)

                wlinks.new(sky.outputs['Color'], bg.inputs['Color'])
                wlinks.new(bg.outputs['Background'], output.inputs['Surface'])
            except Exception:
                # Fallback to gradient sky
                _gradient_sky(wnodes, wlinks)
        else:
            _gradient_sky(wnodes, wlinks)

        # =========================================================
        # VIEWPORT — frame scene objects
        # =========================================================
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


def _gradient_sky(nodes, links):
    """Fallback gradient sky for EEVEE or when Sky Texture is unavailable."""
    bg = nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = 1.0
    output = nodes.new('ShaderNodeOutputWorld')
    output.location = (300, 0)

    mix = nodes.new('ShaderNodeMixRGB')
    mix.location = (-200, 0)
    mix.inputs[1].default_value = (0.85, 0.92, 1.0, 1.0)
    mix.inputs[2].default_value = (0.4, 0.6, 0.9, 1.0)

    coord = nodes.new('ShaderNodeTexCoord')
    coord.location = (-600, 0)
    sep = nodes.new('ShaderNodeSeparateXYZ')
    sep.location = (-400, 0)

    links.new(coord.outputs['Generated'], sep.inputs['Vector'])
    links.new(sep.outputs['Z'], mix.inputs['Fac'])
    links.new(mix.outputs['Color'], bg.inputs['Color'])
    links.new(bg.outputs['Background'], output.inputs['Surface'])


setup_scene()
'''
