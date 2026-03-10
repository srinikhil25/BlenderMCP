import textwrap


def home_script() -> str:
    """
    Return a Blender Python script (as text) that:
    - Clears the scene.
    - Creates a simple house: foundation, walls, roof.
    - Adds boolean cutouts for windows and doors.
    - Applies simple BSDF materials.

    This script is intended to run INSIDE Blender (bpy available).
    """
    # NOTE: This is written as a raw string so it can be passed to Blender.
    return textwrap.dedent(
        r'''
        import bpy
        import bmesh
        from mathutils import Vector


        def setup_scene():
            # Clear existing mesh objects
            bpy.ops.object.select_all(action='SELECT')
            bpy.ops.object.delete(use_global=False)

            # Remove orphan data blocks
            for block in bpy.data.meshes:
                if block.users == 0:
                    bpy.data.meshes.remove(block)
            for mat in bpy.data.materials:
                if mat.users == 0:
                    bpy.data.materials.remove(mat)


        def get_or_create_material(name, base_color):
            mat = bpy.data.materials.get(name)
            if mat is None:
                mat = bpy.data.materials.new(name=name)
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs["Base Color"].default_value = (
                        base_color[0],
                        base_color[1],
                        base_color[2],
                        1.0,
                    )
            return mat


        def create_foundation(width=8.0, depth=6.0, thickness=0.2):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, thickness / 2.0))
            obj = bpy.context.active_object
            obj.name = "Foundation"
            obj.scale = (width / 2.0, depth / 2.0, thickness / 2.0)

            mat = get_or_create_material("Foundation_Mat", (0.6, 0.6, 0.6))
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

            return obj


        def create_walls(width=8.0, depth=6.0, height=3.0, thickness=0.2):
            # Use a cube scaled to outer dimensions then boolean out interior
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, height / 2.0))
            outer = bpy.context.active_object
            outer.name = "Walls_Outer"
            outer.scale = (width / 2.0, depth / 2.0, height / 2.0)

            # Inner volume to subtract
            inset = 0.2
            bpy.ops.mesh.primitive_cube_add(
                size=1.0, location=(0.0, 0.0, height / 2.0)
            )
            inner = bpy.context.active_object
            inner.name = "Walls_Inner"
            inner.scale = (
                width / 2.0 - thickness,
                depth / 2.0 - thickness,
                height / 2.0 - thickness,
            )

            bool_mod = outer.modifiers.new(name="Walls_Hollow", type="BOOLEAN")
            bool_mod.operation = "DIFFERENCE"
            bool_mod.object = inner
            bpy.context.view_layer.objects.active = outer
            bpy.ops.object.modifier_apply(modifier=bool_mod.name)

            # Cleanup inner helper
            bpy.data.objects.remove(inner, do_unlink=True)

            outer.name = "Walls"
            mat = get_or_create_material("Walls_Mat", (0.9, 0.9, 0.9))
            if outer.data.materials:
                outer.data.materials[0] = mat
            else:
                outer.data.materials.append(mat)

            return outer


        def create_roof(width=8.0, depth=6.0, wall_height=3.0, overhang=0.3, pitch=0.8):
            # Simple gabled roof using a cube and bmesh
            mesh = bpy.data.meshes.new("RoofMesh")
            obj = bpy.data.objects.new("Roof", mesh)
            bpy.context.collection.objects.link(obj)

            bm = bmesh.new()

            half_w = width / 2.0 + overhang
            half_d = depth / 2.0 + overhang
            base_z = wall_height + 0.1
            ridge_z = base_z + pitch

            # Define 6 vertices (rectangular base + 2 ridge points)
            v0 = bm.verts.new(Vector((-half_w, -half_d, base_z)))
            v1 = bm.verts.new(Vector((half_w, -half_d, base_z)))
            v2 = bm.verts.new(Vector((half_w, half_d, base_z)))
            v3 = bm.verts.new(Vector((-half_w, half_d, base_z)))
            vr1 = bm.verts.new(Vector((0.0, -half_d, ridge_z)))
            vr2 = bm.verts.new(Vector((0.0, half_d, ridge_z)))

            bm.faces.new((v0, v1, vr1))
            bm.faces.new((v1, v2, vr2, vr1))
            bm.faces.new((v2, v3, vr2))
            bm.faces.new((v3, v0, vr1, vr2))
            bm.to_mesh(mesh)
            bm.free()

            mat = get_or_create_material("Roof_Mat", (0.8, 0.2, 0.2))
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

            return obj


        def add_window_cutouts(walls_obj, width=1.0, height=1.2, sill_height=1.0):
            # Create a few simple rectangular windows as boolean cutters
            cutter_objs = []
            positions = [
                (0.0, -3.0, sill_height + height / 2.0),
                (2.5, 3.0, sill_height + height / 2.0),
                (-2.5, 3.0, sill_height + height / 2.0),
            ]
            depth = 0.4

            for idx, (x, y, z) in enumerate(positions):
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
                cutter = bpy.context.active_object
                cutter.name = f"WindowCutter_{idx}"
                cutter.scale = (width / 2.0, depth / 2.0, height / 2.0)
                cutter_objs.append(cutter)

            for cutter in cutter_objs:
                mod = walls_obj.modifiers.new(name=cutter.name, type="BOOLEAN")
                mod.operation = "DIFFERENCE"
                mod.object = cutter
                bpy.context.view_layer.objects.active = walls_obj
                bpy.ops.object.modifier_apply(modifier=mod.name)

            for cutter in cutter_objs:
                bpy.data.objects.remove(cutter, do_unlink=True)


        def add_door_cutout(walls_obj, width=1.0, height=2.2):
            bpy.ops.mesh.primitive_cube_add(
                size=1.0, location=(0.0, -3.0, height / 2.0)
            )
            cutter = bpy.context.active_object
            cutter.name = "DoorCutter"
            depth = 0.5
            cutter.scale = (width / 2.0, depth / 2.0, height / 2.0)

            mod = walls_obj.modifiers.new(name="DoorCutout", type="BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.object = cutter
            bpy.context.view_layer.objects.active = walls_obj
            bpy.ops.object.modifier_apply(modifier=mod.name)

            bpy.data.objects.remove(cutter, do_unlink=True)


        def main():
            setup_scene()
            foundation = create_foundation()
            walls = create_walls()
            roof = create_roof()
            add_window_cutouts(walls)
            add_door_cutout(walls)
            print("SUCCESS: Home created.")


        if __name__ == "__main__":
            try:
                main()
            except Exception as e:
                print(f"ERROR: {e}")
        '''
    )


def script_for_prompt(prompt: str) -> str:
    """
    Very simple router from natural language prompt to a Blender script string.
    Currently:
    - If the prompt mentions 'home' or 'house', returns the home script.
    - Otherwise defaults to the same home script as a placeholder.
    """
    text = prompt.lower()
    if "home" in text or "house" in text:
        return home_script()
    # Fallback for now
    return home_script()

