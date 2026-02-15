"""
API Platform Features Configuration

Dynamically configures available features based on detected platform.
Tripo3D is primary, Hitem3D is fallback.
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field


class GenerationMode(str, Enum):
    """Available generation modes."""

    IMAGE_TO_3D = "image_to_3d"
    TEXT_TO_3D = "text_to_3d"
    MULTIVIEW_TO_3D = "multiview_to_3d"


class OutputFormat(str, Enum):
    """Available output formats."""

    OBJ = "obj"
    GLB = "glb"
    STL = "stl"
    FBX = "fbx"
    USDZ = "usdz"


@dataclass
class ModelInfo:
    """Information about a model/algorithm."""

    id: str
    name: str
    description: str
    resolutions: List[str] = field(default_factory=list)
    default_resolution: str = "1024"
    features: List[str] = field(default_factory=list)


@dataclass
class PlatformFeatures:
    """Features available for a platform."""

    name: str
    supports_text_to_3d: bool = False
    supports_image_to_3d: bool = False
    supports_multiview: bool = False
    supports_animation: bool = False
    supports_rigging: bool = False
    supports_stylization: bool = False
    supports_refinement: bool = False
    supports_pbr: bool = False
    formats: List[str] = field(default_factory=lambda: ["glb", "obj"])
    models: Dict[str, ModelInfo] = field(default_factory=dict)
    max_wait_time: int = 3600  # seconds


# Tripo3D Features Configuration
TRIPO3D_FEATURES = PlatformFeatures(
    name="Cloud 3D Generator",
    supports_text_to_3d=True,
    supports_image_to_3d=True,
    supports_multiview=True,
    supports_animation=True,
    supports_rigging=True,
    supports_stylization=True,
    supports_refinement=True,
    supports_pbr=True,
    formats=["glb", "obj", "stl", "fbx", "usdz"],
    models={
        "v2_5": ModelInfo(
            id="v2.5-20250123",
            name="v2.5 (Latest - Balanced)",
            description="Latest model with best balance of speed and quality",
            resolutions=["512", "1024", "2048"],
            default_resolution="1024",
            features=["pbr", "texture"],
        ),
        "v2_0": ModelInfo(
            id="v2.0-20240919",
            name="v2.0 (PBR Quality)",
            description="High-quality PBR materials and detailed geometry",
            resolutions=["1024", "2048"],
            default_resolution="1024",
            features=["pbr", "texture", "high_quality"],
        ),
        "v1_4": ModelInfo(
            id="v1.4-20240625",
            name="v1.4 (Fast)",
            description="Fast generation with good quality",
            resolutions=["512", "1024"],
            default_resolution="512",
            features=["fast"],
        ),
    },
    max_wait_time=3600,
)

# Hitem3D Features Configuration
HITEM3D_FEATURES = PlatformFeatures(
    name="Cloud 3D Generator",
    supports_text_to_3d=False,
    supports_image_to_3d=True,
    supports_multiview=False,
    supports_animation=False,
    supports_rigging=False,
    supports_stylization=False,
    supports_refinement=False,
    supports_pbr=False,
    formats=["obj", "glb", "stl", "fbx", "usdz"],
    models={
        "standard_v1_5": ModelInfo(
            id="hitem3dv1.5",
            name="Standard v1.5",
            description="General purpose 3D generation",
            resolutions=["512", "1024", "1536", "1536pro"],
            default_resolution="1024",
            features=[],
        ),
        "standard_v2_0": ModelInfo(
            id="hitem3dv2.0",
            name="Standard v2.0",
            description="Enhanced 3D generation",
            resolutions=["1536", "1536pro"],
            default_resolution="1536",
            features=["enhanced"],
        ),
        "portrait_v1_5": ModelInfo(
            id="scene-portraitv1.5",
            name="Portrait v1.5",
            description="Specialized for portraits",
            resolutions=["1536"],
            default_resolution="1536",
            features=["portrait"],
        ),
        "portrait_v2_0": ModelInfo(
            id="scene-portraitv2.0",
            name="Portrait v2.0",
            description="Enhanced portrait generation",
            resolutions=["1536pro"],
            default_resolution="1536pro",
            features=["portrait"],
        ),
        "portrait_v2_1": ModelInfo(
            id="scene-portraitv2.1",
            name="Portrait v2.1",
            description="Latest portrait model",
            resolutions=["1536pro"],
            default_resolution="1536pro",
            features=["portrait"],
        ),
    },
    max_wait_time=3600,
)


def get_platform_features(platform_type: str) -> PlatformFeatures:
    """
    Get features configuration for a platform.

    Args:
        platform_type: 'tripo3d' or 'hitem3d'

    Returns:
        PlatformFeatures configuration
    """
    if platform_type.lower() == "tripo3d":
        return TRIPO3D_FEATURES
    else:
        return HITEM3D_FEATURES


def get_available_generation_modes(platform_type: str) -> List[Dict[str, Any]]:
    """
    Get available generation modes for a platform.

    Args:
        platform_type: 'tripo3d' or 'hitem3d'

    Returns:
        List of generation mode configurations
    """
    features = get_platform_features(platform_type)
    modes = []

    if features.supports_image_to_3d:
        modes.append(
            {
                "id": "image_to_3d",
                "name": "Image to 3D",
                "description": "Generate 3D model from single image",
                "icon": "🖼️",
            }
        )

    if features.supports_text_to_3d:
        modes.append(
            {
                "id": "text_to_3d",
                "name": "Text to 3D",
                "description": "Generate 3D model from text description",
                "icon": "📝",
            }
        )

    if features.supports_multiview:
        modes.append(
            {
                "id": "multiview_to_3d",
                "name": "Multi-view to 3D",
                "description": "Generate 3D model from multiple views",
                "icon": "📸",
            }
        )

    return modes


def get_available_models(platform_type: str) -> Dict[str, Any]:
    """
    Get available models for a platform in standardized format.

    Args:
        platform_type: 'tripo3d' or 'hitem3d'

    Returns:
        Dictionary with model information
    """
    features = get_platform_features(platform_type)

    return {
        "api": {
            "name": features.name,
            "description": "Cloud-based 3D generation service",
            "models": {
                model_id: {
                    "name": model.name,
                    "description": model.description,
                    "resolutions": model.resolutions,
                    "default_resolution": model.default_resolution,
                    "features": model.features,
                }
                for model_id, model in features.models.items()
            },
        },
        "features": {
            "supports_text_to_3d": features.supports_text_to_3d,
            "supports_image_to_3d": features.supports_image_to_3d,
            "supports_multiview": features.supports_multiview,
            "supports_animation": features.supports_animation,
            "supports_pbr": features.supports_pbr,
        },
        "formats": features.formats,
    }
