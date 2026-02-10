import os
import numpy as np
import trimesh


def export_mesh(o3d_mesh, out, scale: float = 1.0):
    """
    Export Open3D mesh to OBJ, STL, or GLB.

    Args:
        o3d_mesh: Open3D TriangleMesh.
        out: Output file path (.obj, .stl, or .glb).
        scale: Scale factor applied to vertices (default 1.0).
    """
    vertices = np.array(o3d_mesh.vertices, dtype=np.float64, copy=True)
    if scale != 1.0:
        vertices = vertices * scale
    faces = np.array(o3d_mesh.triangles, dtype=np.int64, copy=True)

    vertex_colors = None
    if o3d_mesh.has_vertex_colors():
        cols = np.array(o3d_mesh.vertex_colors, copy=True)
        if cols.max() > 1.0:
            cols = np.clip(cols / 255.0, 0, 1)
        vertex_colors = cols[:, :3]

    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        vertex_colors=vertex_colors,
        process=False,
    )
    mesh.export(out)
