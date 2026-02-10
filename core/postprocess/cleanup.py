import open3d as o3d

def clean_mesh(mesh):
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.remove_non_manifold_edges()
    mesh.compute_vertex_normals()
    mesh = mesh.filter_smooth_simple(5)
    return mesh
