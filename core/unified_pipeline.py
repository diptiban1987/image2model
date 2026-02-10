import os
import time
import platform
import psutil
from typing import Dict, Any, Optional
from pathlib import Path
import asyncio
import json

from core.pipeline import run_pipeline as local_pipeline
from core.hitem3d_api import Hitem3DAPI


def run_pipeline(
    image_path: str,
    name: str = "model",
    use_api: bool = False,
    api_token: Optional[str] = None,
    api_model: str = "hitem3dv1.5",
    api_resolution: str = "1024",
    api_format: str = "glb",
    output_dir: str = "output",
    quality: str = "standard",
    scale: float = 1.0,
    **kwargs
) -> dict:
    """
    Unified pipeline that supports both local processing and Hitem3D API.

    Args:
        image_path: Path to input image
        name: Base name for output files
        use_api: Whether to use Hitem3D API (True) or local processing (False)
        api_token: Hitem3D API access token (required if use_api=True)
        api_model: Hitem3D model to use (hitem3dv1.5, hitem3dv2.0, etc.)
        api_resolution: Output resolution for API (512, 1024, 1536, 1536pro)
        output_dir: Output directory for local pipeline (default "output")
        quality: Local mesh quality: "draft", "standard", "high", "production"
        scale: Scale factor for exported mesh (local only)
        **kwargs: Additional arguments passed to local pipeline or API

    Returns:
        Dict with paths to generated files and processing stats
    """
    if use_api:
        credentials = resolve_hitem3d_credentials(api_token)
        if not (credentials["access_token"] or (credentials["client_id"] and credentials["client_secret"])):
            raise ValueError("Hitem3D credentials are required when use_api=True")
        return asyncio.run(_run_api_pipeline(
            image_path, name, credentials, api_model, api_resolution, api_format, **kwargs
        ))
    else:
        return _run_local_pipeline(
            image_path, name,
            output_dir=output_dir, quality=quality, scale=scale,
            **kwargs
        )

async def run_pipeline_async(
    image_path: str,
    name: str = "model",
    use_api: bool = False,
    api_token: Optional[str] = None,
    api_model: str = "hitem3dv1.5",
    api_resolution: str = "1024",
    api_format: str = "glb",
    output_dir: str = "output",
    quality: str = "standard",
    scale: float = 1.0,
    **kwargs
) -> dict:
    """
    Async-safe pipeline entrypoint for FastAPI.
    """
    if use_api:
        credentials = resolve_hitem3d_credentials(api_token)
        if not (credentials["access_token"] or (credentials["client_id"] and credentials["client_secret"])):
            raise ValueError("Hitem3D credentials are required when use_api=True")
        return await _run_api_pipeline(
            image_path, name, credentials, api_model, api_resolution, api_format, **kwargs
        )
    else:
        return await asyncio.to_thread(
            _run_local_pipeline, image_path, name,
            output_dir=output_dir, quality=quality, scale=scale,
            **kwargs
        )


def _run_local_pipeline(
    image_path: str,
    name: str,
    output_dir: str = "output",
    quality: str = "standard",
    scale: float = 1.0,
    **kwargs
) -> dict:
    """
    Run the local processing pipeline with enhanced error handling.

    Args:
        image_path: Path to input image
        name: Base name for output files
        output_dir: Output directory for mesh files
        quality: Mesh quality preset (draft, standard, high, production)
        scale: Scale factor for export
        **kwargs: Additional arguments for local pipeline

    Returns:
        Dict with paths and stats
    """
    t0 = time.perf_counter()

    local_min_required = 6.0
    system_info: Dict[str, Any] = {}
    try:
        mem = psutil.virtual_memory()
        system_info = {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "ram_total_gb": round(mem.total / (1024 ** 3), 2),
            "ram_available_gb": round(mem.available / (1024 ** 3), 2),
            "ram_required_gb": local_min_required,
        }
    except Exception:
        system_info = {}

    pre_warning = None
    if system_info.get("ram_available_gb") is not None and system_info["ram_available_gb"] < local_min_required:
        pre_warning = (
            f"Low available RAM detected for local processing ({system_info['ram_available_gb']}GB available). "
            f"TripoSR requires at least {local_min_required}GB RAM. "
            "Processing will attempt to continue but may fall back to a basic mesh."
        )

    try:
        result = local_pipeline(
            image_path, name,
            output_dir=output_dir,
            quality=quality,
            scale=scale,
            **kwargs
        )
        
        fallback_info = result.get("fallback_info") if isinstance(result, dict) else None
        if isinstance(fallback_info, dict) and fallback_info.get("fallback"):
            reason = fallback_info.get("fallback_reason")
            if reason == "low_memory":
                available = fallback_info.get("available_gb")
                detail = f" ({available}GB available)" if isinstance(available, (int, float)) else ""
                result["warning"] = (
                    "Local processing fell back to a basic mesh due to low available RAM"
                    f"{detail}. TripoSR requires at least {local_min_required}GB RAM. "
                    "Upgrade the PC RAM or use Hitem3D API for better results."
                )
            elif reason == "memory_error":
                result["warning"] = (
                    "Local processing fell back to a basic mesh because TripoSR ran out of memory. "
                    "Upgrade the PC RAM or use Hitem3D API for better results."
                )
            else:
                result["warning"] = (
                    "Local processing fell back to a basic mesh because TripoSR failed. "
                    "Use Hitem3D API for better results."
                )
        if pre_warning and "warning" not in result:
            result["warning"] = pre_warning
        
        t1 = time.perf_counter()
        
        # Add processing method info
        result["processing_method"] = "local"
        result["api_used"] = False
        if system_info:
            result["system_info"] = system_info
        
        return result
        
    except Exception as e:
        return {
            "error": f"Local processing failed: {str(e)}",
            "obj": "",
            "stl": "",
            "glb": "",
            "stats": {"total_seconds": 0, "stages": {"load_and_infer": 0, "cleanup": 0, "export": 0}},
            "processing_method": "local",
            "api_used": False,
            "system_info": system_info
        }


async def _run_api_pipeline(
    image_path: str,
    name: str,
    credentials: Dict[str, Optional[str]],
    api_model: str,
    api_resolution: str,
    api_format: str,
    **kwargs
) -> dict:
    """
    Run the Hitem3D API pipeline.
    
    Args:
        image_path: Path to input image
        name: Base name for output files
        api_token: Hitem3D API access token
        api_model: Hitem3D model to use
        api_resolution: Output resolution
        **kwargs: Additional arguments for API
        
    Returns:
        Dict with paths and stats
    """
    t0 = time.perf_counter()
    
    # Initialize API client
    api = Hitem3DAPI(
        access_token=credentials["access_token"],
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"]
    )
    
    try:
        # Generate 3D model using API
        format_map = {
            "obj": 1,
            "glb": 2,
            "stl": 3,
            "fbx": 4,
            "usdz": 5
        }
        format_type = format_map.get((api_format or "").lower(), 2)
        result = await api.generate_3d_model(
            image_path=image_path,
            output_dir="output",
            model_name=name,
            model=api_model,
            resolution=api_resolution,
            format_type=format_type,
            **kwargs
        )
        
        t1 = time.perf_counter()
        
        # Add processing method info and stats
        result["processing_method"] = "hitem3d_api"
        result["api_used"] = True
        result["api_model"] = api_model
        result["api_resolution"] = api_resolution
        result["api_format"] = api_format
        result["stats"] = {
            "total_seconds": round(t1 - t0, 3),
            "stages": {
                "api_processing": round(t1 - t0, 3)
            }
        }
        
        return result
        
    finally:
        await api.close()


def get_available_models() -> Dict[str, Dict[str, Any]]:
    """
    Get available models for both local and API processing.
    
    Returns:
        Dict with model information
    """
    return {
        "local": {
            "name": "Local Processing",
            "description": "Process using local GPU/CPU resources",
            "models": {
                "default": {
                    "name": "Default Local Model",
                    "description": "Standard local 3D generation model"
                }
            }
        },
        "hitem3d": {
            "name": "Hitem3D API",
            "description": "Cloud-based 3D generation service",
            "models": {
                "hitem3dv1.5": {
                    "name": "HiTeM3D v1.5",
                    "description": "General purpose 3D generation model",
                    "resolutions": ["512", "1024", "1536", "1536pro"],
                    "default_resolution": "1024"
                },
                "hitem3dv2.0": {
                    "name": "HiTeM3D v2.0",
                    "description": "Enhanced 3D generation model",
                    "resolutions": ["1536", "1536pro"],
                    "default_resolution": "1536"
                },
                "scene-portraitv1.5": {
                    "name": "Scene Portrait v1.5",
                    "description": "Specialized portrait model",
                    "resolutions": ["1536"],
                    "default_resolution": "1536"
                },
                "scene-portraitv2.0": {
                    "name": "Scene Portrait v2.0",
                    "description": "Specialized portrait model",
                    "resolutions": ["1536pro"],
                    "default_resolution": "1536pro"
                },
                "scene-portraitv2.1": {
                    "name": "Scene Portrait v2.1",
                    "description": "Specialized portrait model",
                    "resolutions": ["1536pro"],
                    "default_resolution": "1536pro"
                }
            }
        }
    }


async def validate_api_token(token: str) -> bool:
    """
    Validate Hitem3D API token by making a test request.
    
    Args:
        token: API access token to validate
        
    Returns:
        True if token is valid, False otherwise
    """
    try:
        credentials = resolve_hitem3d_credentials(token)
        api = Hitem3DAPI(
            access_token=credentials["access_token"],
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"]
        )
        is_valid = await api.validate_access_token()
        await api.close()
        return is_valid
    except Exception:
        return False


def save_hitem3d_credentials(api_token: str) -> Dict[str, Optional[str]]:
    token_value = (api_token or "").strip()
    if not token_value:
        raise ValueError("API token is required")
    access_token = token_value
    client_id = None
    client_secret = None
    if ":" in access_token:
        parts = access_token.split(":", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            client_id, client_secret = parts[0].strip(), parts[1].strip()
            access_token = ""
    data = {
        "access_token": access_token,
        "client_id": client_id or "",
        "client_secret": client_secret or "",
    }
    config_dir = Path("config")
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "hitem3d_credentials.json"
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {"access_token": access_token or None, "client_id": client_id, "client_secret": client_secret}


def resolve_hitem3d_credentials(api_token: Optional[str]) -> Dict[str, Optional[str]]:
    token_value = (api_token or "").strip()
    if token_value:
        access_token = token_value
        client_id = None
        client_secret = None
        if ":" in access_token:
            parts = access_token.split(":", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                client_id, client_secret = parts[0].strip(), parts[1].strip()
                access_token = None
        return {"access_token": access_token, "client_id": client_id, "client_secret": client_secret}

    access_token = os.getenv("HITEM3D_ACCESS_TOKEN") or os.getenv("HITEM3D_API_TOKEN")
    client_id = os.getenv("HITEM3D_CLIENT_ID")
    client_secret = os.getenv("HITEM3D_CLIENT_SECRET")
    try_files = [
        Path("config") / "hitem3d_credentials.json",
        Path("hitem3d_credentials.json")
    ]
    for p in try_files:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                file_access_token = data.get("access_token") or data.get("token")
                file_client_id = data.get("client_id")
                file_client_secret = data.get("client_secret")
                access_token = access_token or file_access_token
                client_id = client_id or file_client_id
                client_secret = client_secret or file_client_secret
                break
            except Exception:
                pass
    if access_token and not (client_id or client_secret):
        if ":" in access_token:
            parts = access_token.split(":", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                client_id, client_secret = parts[0].strip(), parts[1].strip()
                access_token = None
    return {"access_token": access_token, "client_id": client_id, "client_secret": client_secret}
