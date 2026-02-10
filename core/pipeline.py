import os
import time
from typing import Optional

from core.inference.model_manager import ModelManager
from core.postprocess.cleanup import clean_mesh
from core.exporter import export_mesh


# Quality presets: "draft" = fast cleanup only; others use AdvancedMeshProcessor
QUALITY_LEVELS = ("draft", "standard", "high", "production")


def run_pipeline(
    image,
    name: str = "model",
    output_dir: str = "output",
    quality: str = "standard",
    scale: float = 1.0,
) -> dict:
    """
    Run the full image → mesh → exports pipeline and return paths plus timing stats.

    Args:
        image: Input image path or loaded image for inference.
        name: Base name for output files (no extension).
        output_dir: Directory for OBJ, STL, GLB outputs.
        quality: Mesh quality preset: "draft", "standard", "high", "production".
                 "draft" = fast cleanup only; others use advanced mesh processing.
        scale: Scale factor applied to mesh before export (default 1.0).

    Returns:
        Dict with "obj", "stl", "glb" paths and "stats" (timing). JSON-serialisable.
    """
    if quality not in QUALITY_LEVELS:
        quality = "standard"
    os.makedirs(output_dir, exist_ok=True)

    t0 = time.perf_counter()
    manager = ModelManager()

    t_infer_start = time.perf_counter()
    infer_result = manager.run(image)
    fallback_info = None
    if isinstance(infer_result, dict) and "mesh" in infer_result:
        mesh = infer_result["mesh"]
        fallback_info = {k: v for k, v in infer_result.items() if k != "mesh"}
    else:
        mesh = infer_result
    t_infer_end = time.perf_counter()

    t_cleanup_start = time.perf_counter()
    mesh = clean_mesh(mesh)
    if quality != "draft":
        from core.postprocess.advanced_mesh_processor import (
            AdvancedMeshProcessor,
            ProcessingConfig,
            MeshQualityLevel,
        )
        level = MeshQualityLevel(quality)
        config = ProcessingConfig(quality_level=level)
        if quality in ("high", "production"):
            config.repair_holes = False
        processor = AdvancedMeshProcessor(config)
        mesh = processor.process(mesh)
    t_cleanup_end = time.perf_counter()

    t_export_start = time.perf_counter()
    obj_path = os.path.join(output_dir, f"{name}.obj")
    stl_path = os.path.join(output_dir, f"{name}.stl")
    glb_path = os.path.join(output_dir, f"{name}.glb")
    export_mesh(mesh, obj_path, scale=scale)
    export_mesh(mesh, stl_path, scale=scale)
    export_mesh(mesh, glb_path, scale=scale)
    missing = []
    for path in (obj_path, stl_path, glb_path):
        if not os.path.isfile(path):
            missing.append(path)
            continue
        if os.path.getsize(path) == 0:
            missing.append(path)
    if missing:
        raise RuntimeError(f"Export failed, missing outputs: {', '.join(missing)}")
    t_export_end = time.perf_counter()

    t1 = time.perf_counter()

    stats = {
        "total_seconds": round(t1 - t0, 3),
        "stages": {
            "load_and_infer": round(t_infer_end - t_infer_start, 3),
            "cleanup": round(t_cleanup_end - t_cleanup_start, 3),
            "export": round(t_export_end - t_export_start, 3),
        },
    }

    result = {
        "obj": obj_path,
        "stl": stl_path,
        "glb": glb_path,
        "stats": stats,
        "quality": quality,
    }
    if fallback_info:
        result["fallback_info"] = fallback_info
    return result
