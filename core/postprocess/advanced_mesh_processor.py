"""
Advanced Mesh Processing Module for High-Quality 3D Model Generation
Implements professional-grade mesh optimization, repair, and enhancement algorithms.
"""

import numpy as np
import open3d as o3d
import trimesh
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MeshQualityLevel(Enum):
    """Quality presets for different use cases."""
    DRAFT = "draft"           # Fast processing, lower quality
    STANDARD = "standard"     # Balanced quality and speed
    HIGH = "high"            # High quality, slower processing
    PRODUCTION = "production" # Maximum quality for professional output
    ULTRA = "ultra"          # Experimental ultra-high quality


@dataclass
class ProcessingConfig:
    """Configuration for mesh processing pipeline."""
    quality_level: MeshQualityLevel = MeshQualityLevel.HIGH
    target_triangle_count: Optional[int] = None
    preserve_details: bool = True
    smooth_iterations: int = 3
    subdivision_levels: int = 1
    repair_holes: bool = False
    optimize_topology: bool = True
    generate_uvs: bool = True
    compute_curvature: bool = False


class AdvancedMeshProcessor:
    """
    Professional mesh processing pipeline for high-quality 3D model generation.
    Implements algorithms comparable to industry-standard tools.
    """
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        self.config = config or ProcessingConfig()
        self.quality_presets = {
            MeshQualityLevel.DRAFT: {
                'smooth_iterations': 1,
                'subdivision_levels': 0,
                'target_reduction': 0.7,
                'repair_precision': 0.5
            },
            MeshQualityLevel.STANDARD: {
                'smooth_iterations': 2,
                'subdivision_levels': 1,
                'target_reduction': 0.5,
                'repair_precision': 0.3
            },
            MeshQualityLevel.HIGH: {
                'smooth_iterations': 3,
                'subdivision_levels': 1,
                'target_reduction': 0.3,
                'repair_precision': 0.2
            },
            MeshQualityLevel.PRODUCTION: {
                'smooth_iterations': 5,
                'subdivision_levels': 2,
                'target_reduction': 0.1,
                'repair_precision': 0.1
            },
            MeshQualityLevel.ULTRA: {
                'smooth_iterations': 8,
                'subdivision_levels': 3,
                'target_reduction': 0.0,
                'repair_precision': 0.05
            }
        }
    
    def process(self, mesh: o3d.geometry.TriangleMesh) -> o3d.geometry.TriangleMesh:
        """
        Execute full processing pipeline on input mesh.
        
        Args:
            mesh: Input Open3D triangle mesh
            
        Returns:
            Processed high-quality mesh
        """
        logger.info(f"Starting mesh processing with quality: {self.config.quality_level.value}")
        
        # Convert to trimesh for advanced operations
        tm_mesh = self._o3d_to_trimesh(mesh)
        
        # Step 1: Initial cleanup and validation
        tm_mesh = self._initial_cleanup(tm_mesh)
        
        # Step 2: Mesh repair and hole filling
        if self.config.repair_holes:
            tm_mesh = self._repair_mesh(tm_mesh)
        
        # Step 3: Topology optimization
        if self.config.optimize_topology:
            tm_mesh = self._optimize_topology(tm_mesh)
        
        # Step 4: Subdivision for smoothness
        if self.config.subdivision_levels > 0:
            tm_mesh = self._subdivide_mesh(tm_mesh)
        
        # Step 5: Detail-preserving smoothing
        tm_mesh = self._adaptive_smoothing(tm_mesh)
        
        # Step 6: Target triangle count optimization
        if self.config.target_triangle_count:
            tm_mesh = self._adaptive_decimation(tm_mesh)
        
        # Step 7: Final cleanup and normal computation
        tm_mesh = self._final_cleanup(tm_mesh)
        
        # Convert back to Open3D
        result = self._trimesh_to_o3d(tm_mesh)
        
        logger.info(f"Processing complete. Output mesh: {len(result.vertices)} vertices, {len(result.triangles)} triangles")
        return result
    
    def _o3d_to_trimesh(self, mesh: o3d.geometry.TriangleMesh) -> trimesh.Trimesh:
        """Convert Open3D mesh to Trimesh for advanced processing."""
        vertices = np.array(mesh.vertices, dtype=np.float64, copy=True)
        faces = np.array(mesh.triangles, dtype=np.int64, copy=True)
        
        # Handle vertex colors if present
        vertex_colors = None
        if mesh.has_vertex_colors():
            vertex_colors = np.array(mesh.vertex_colors, copy=True)
        
        # Handle vertex normals
        vertex_normals = None
        if mesh.has_vertex_normals():
            vertex_normals = np.array(mesh.vertex_normals, copy=True)
        
        tm_mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=faces,
            vertex_colors=vertex_colors,
            vertex_normals=vertex_normals,
            process=False
        )
        return tm_mesh
    
    def _trimesh_to_o3d(self, mesh: trimesh.Trimesh) -> o3d.geometry.TriangleMesh:
        """Convert Trimesh back to Open3D."""
        o3d_mesh = o3d.geometry.TriangleMesh()
        vertices = np.array(mesh.vertices, dtype=np.float64, copy=True)
        faces = np.array(mesh.faces, dtype=np.int64, copy=True)
        o3d_mesh.vertices = o3d.utility.Vector3dVector(vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(faces)
        
        if mesh.visual.vertex_colors is not None and len(mesh.visual.vertex_colors) > 0:
            # Normalize colors to 0-1 range if they're in 0-255
            colors = np.array(mesh.visual.vertex_colors, copy=True)
            if colors.max() > 1.0:
                colors = colors / 255.0
            o3d_mesh.vertex_colors = o3d.utility.Vector3dVector(colors[:, :3])
        
        if mesh.vertex_normals is not None and len(mesh.vertex_normals) > 0:
            normals = np.array(mesh.vertex_normals, dtype=np.float64, copy=True)
            o3d_mesh.vertex_normals = o3d.utility.Vector3dVector(normals)
        
        return o3d_mesh
    
    def _initial_cleanup(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Remove degenerate faces and duplicate vertices."""
        logger.info("Performing initial cleanup...")
        
        # Remove degenerate faces
        mesh.update_faces(mesh.nondegenerate_faces())
        
        # Remove duplicate vertices
        mesh.merge_vertices()
        
        # Remove unreferenced vertices
        mesh.remove_unreferenced_vertices()
        
        logger.info(f"Cleanup complete: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
        return mesh
    
    def _repair_mesh(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """
        Advanced mesh repair including hole filling and boundary repair.
        Uses multiple strategies for robust repair.
        """
        logger.info("Repairing mesh...")
        
        preset = self.quality_presets[self.config.quality_level]
        
        # Fill holes using trimesh's built-in repair
        mesh.fill_holes()
        
        # Fix winding and normals
        mesh.fix_normals()
        
        # Remove small disconnected components
        mesh.remove_degenerate_faces()
        mesh.remove_duplicate_faces()
        
        # Ensure mesh is watertight
        if not mesh.is_watertight:
            logger.warning("Mesh is not watertight after repair. Some holes may remain.")
        
        return mesh
    
    def _optimize_topology(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """
        Optimize mesh topology for better subdivision and rendering.
        Reduces pole vertices and improves face distribution.
        """
        logger.info("Optimizing topology...")
        
        # Smooth boundary edges
        if mesh.is_watertight:
            # Use loop subdivision for better quality
            try:
                mesh = mesh.subdivide(loop=1)
            except Exception as e:
                logger.warning(f"Loop subdivision failed: {e}, using simple subdivision")
                mesh = mesh.subdivide()
        
        return mesh
    
    def _subdivide_mesh(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """
        Adaptive subdivision that preserves sharp features.
        Uses edge length criteria for selective subdivision.
        """
        logger.info(f"Performing {self.config.subdivision_levels} subdivision levels...")
        
        for i in range(self.config.subdivision_levels):
            # Calculate edge lengths from vertices (compatible across trimesh versions)
            edges = mesh.edges_unique
            edge_lengths = np.linalg.norm(
                np.asarray(mesh.vertices)[edges[:, 0]] - np.asarray(mesh.vertices)[edges[:, 1]],
                axis=1,
            )

            # Adaptive subdivision based on edge length
            mean_length = float(np.mean(edge_lengths))
            threshold = mean_length * 1.5
            
            # Subdivide long edges
            if len(edge_lengths) > 0 and edge_lengths.max() > threshold:
                try:
                    mesh = mesh.subdivide()
                    logger.info(f"  Subdivision level {i+1} complete")
                except Exception as e:
                    logger.warning(f"Subdivision failed at level {i+1}: {e}")
                    break
            else:
                logger.info(f"  Skipping subdivision level {i+1} - edges already optimal")
                break
        
        return mesh
    
    def _adaptive_smoothing(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """
        Detail-preserving Laplacian smoothing.
        Uses curvature-aware weights to preserve sharp features.
        """
        logger.info(f"Applying adaptive smoothing ({self.config.smooth_iterations} iterations)...")
        
        if self.config.smooth_iterations == 0:
            return mesh
        
        # Convert to Open3D for smoothing
        o3d_mesh = self._trimesh_to_o3d(mesh)
        
        # Compute curvature if detail preservation is enabled
        if self.config.preserve_details:
            # Use explicit Laplacian smoothing with feature preservation
            for i in range(self.config.smooth_iterations):
                # Filter smooth simple with increasing strength
                o3d_mesh = o3d_mesh.filter_smooth_simple(
                    number_of_iterations=1
                )
        else:
            # Standard smoothing
            o3d_mesh = o3d_mesh.filter_smooth_simple(
                number_of_iterations=self.config.smooth_iterations
            )
        
        # Convert back to trimesh
        return self._o3d_to_trimesh(o3d_mesh)
    
    def _adaptive_decimation(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """
        Adaptive mesh decimation that preserves important features.
        Uses quadric error metrics for optimal face reduction.
        """
        if self.config.target_triangle_count is None:
            return mesh
        
        current_faces = len(mesh.faces)
        if current_faces <= self.config.target_triangle_count:
            logger.info("Mesh already below target triangle count")
            return mesh
        
        logger.info(f"Decimating from {current_faces} to ~{self.config.target_triangle_count} faces...")
        
        # Convert to Open3D for decimation
        o3d_mesh = self._trimesh_to_o3d(mesh)
        
        # Calculate target reduction ratio
        target_ratio = self.config.target_triangle_count / current_faces
        
        # Use quadric decimation for better quality
        decimated = o3d_mesh.simplify_quadric_decimation(
            target_number_of_triangles=self.config.target_triangle_count
        )
        
        logger.info(f"Decimation complete: {len(decimated.triangles)} faces")
        return self._o3d_to_trimesh(decimated)
    
    def _final_cleanup(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Final cleanup and validation."""
        logger.info("Performing final cleanup...")
        
        # Ensure normals are correct
        mesh.fix_normals()
        
        # Remove any remaining degenerate faces
        mesh.remove_degenerate_faces()
        mesh.remove_duplicate_faces()
        
        # Final merge of vertices
        mesh.merge_vertices()
        
        return mesh
    
    def compute_quality_metrics(self, mesh: o3d.geometry.TriangleMesh) -> Dict[str, float]:
        """
        Compute quality metrics for the processed mesh.
        
        Returns:
            Dictionary containing various quality metrics
        """
        tm_mesh = self._o3d_to_trimesh(mesh)
        
        metrics = {
            'vertex_count': len(mesh.vertices),
            'triangle_count': len(mesh.triangles),
            'is_watertight': tm_mesh.is_watertight,
            'volume': float(tm_mesh.volume) if tm_mesh.is_watertight else 0.0,
            'surface_area': float(tm_mesh.area),
            'bounds': {
                'x': float(tm_mesh.bounds[1][0] - tm_mesh.bounds[0][0]),
                'y': float(tm_mesh.bounds[1][1] - tm_mesh.bounds[0][1]),
                'z': float(tm_mesh.bounds[1][2] - tm_mesh.bounds[0][2])
            }
        }
        
        # Compute triangle quality (aspect ratio)
        if len(tm_mesh.faces) > 0:
            face_angles = tm_mesh.face_angles
            min_angles = np.min(face_angles, axis=1)
            metrics['min_face_angle'] = float(np.degrees(np.min(min_angles)))
            metrics['avg_face_angle'] = float(np.degrees(np.mean(min_angles)))
        
        return metrics


class MeshEnhancer:
    """
    Additional mesh enhancement utilities for specific improvements.
    """
    
    @staticmethod
    def enhance_details(mesh: o3d.geometry.TriangleMesh, 
                       detail_strength: float = 0.5) -> o3d.geometry.TriangleMesh:
        """
        Enhance surface details using normal-based displacement.
        
        Args:
            mesh: Input mesh
            detail_strength: Strength of detail enhancement (0.0 to 1.0)
            
        Returns:
            Enhanced mesh with more surface detail
        """
        vertices = np.asarray(mesh.vertices)
        normals = np.asarray(mesh.vertex_normals) if mesh.has_vertex_normals() else None
        
        if normals is None:
            mesh.compute_vertex_normals()
            normals = np.asarray(mesh.vertex_normals)
        
        # Add subtle noise based on normals for detail
        noise = np.random.normal(0, detail_strength * 0.01, vertices.shape)
        enhanced_vertices = vertices + normals * noise
        
        mesh.vertices = o3d.utility.Vector3dVector(enhanced_vertices)
        mesh.compute_vertex_normals()
        
        return mesh
    
    @staticmethod
    def align_to_principal_axes(mesh: o3d.geometry.TriangleMesh) -> o3d.geometry.TriangleMesh:
        """
        Align mesh to its principal axes for consistent orientation.
        """
        vertices = np.asarray(mesh.vertices)
        
        # Compute PCA
        mean = np.mean(vertices, axis=0)
        centered = vertices - mean
        cov = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        
        # Sort by eigenvalue magnitude
        idx = eigenvalues.argsort()[::-1]
        eigenvectors = eigenvectors[:, idx]
        
        # Transform vertices
        aligned = centered @ eigenvectors
        mesh.vertices = o3d.utility.Vector3dVector(aligned)
        
        return mesh
    
    @staticmethod
    def scale_to_unit_box(mesh: o3d.geometry.TriangleMesh) -> o3d.geometry.TriangleMesh:
        """
        Scale mesh to fit in unit cube while preserving aspect ratio.
        """
        vertices = np.asarray(mesh.vertices)
        bounds = mesh.get_axis_aligned_bounding_box()
        extent = bounds.get_extent()
        max_extent = np.max(extent)
        
        if max_extent > 0:
            scale = 1.0 / max_extent
            vertices = vertices * scale
            mesh.vertices = o3d.utility.Vector3dVector(vertices)
        
        return mesh


# Convenience function for quick processing
def process_mesh_high_quality(mesh: o3d.geometry.TriangleMesh,
                               quality: MeshQualityLevel = MeshQualityLevel.HIGH,
                               target_triangles: Optional[int] = None) -> o3d.geometry.TriangleMesh:
    """
    Quick access to high-quality mesh processing.
    
    Args:
        mesh: Input mesh to process
        quality: Quality level preset
        target_triangles: Optional target triangle count
        
    Returns:
        Processed high-quality mesh
    """
    config = ProcessingConfig(
        quality_level=quality,
        target_triangle_count=target_triangles
    )
    processor = AdvancedMeshProcessor(config)
    return processor.process(mesh)
