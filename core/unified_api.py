"""
Unified 3D Generation API Client

Provides a single interface for multiple 3D generation APIs.
Priority: Tripo3D (primary), Hitem3D (fallback)

Hides platform-specific details from users.
"""

import os
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
import time
import json


class APIPlatform(Enum):
    """Internal platform identifiers - hidden from users."""

    TRIPO3D = "tripo3d"
    HITEM3D = "hitem3d"
    NONE = "none"


@dataclass
class APICredentials:
    """Generic credentials that work with any platform."""

    api_key: Optional[str] = None
    access_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    platform: APIPlatform = APIPlatform.NONE

    @classmethod
    def from_string(cls, credential_string: str) -> "APICredentials":
        """Parse credential string and detect platform."""
        cred_str = (credential_string or "").strip()

        if not cred_str:
            return cls(platform=APIPlatform.NONE)

        # Check for Hitem3D format (contains colon)
        if ":" in cred_str:
            parts = cred_str.split(":", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                return cls(
                    client_id=parts[0].strip(),
                    client_secret=parts[1].strip(),
                    platform=APIPlatform.HITEM3D,
                )

        # Check for Tripo3D format (starts with specific prefixes)
        # Tripo3D keys are typically longer and don't contain colons
        if len(cred_str) > 20 and not ":" in cred_str:
            return cls(api_key=cred_str, platform=APIPlatform.TRIPO3D)

        # Try as generic API key for Tripo3D
        return cls(api_key=cred_str, platform=APIPlatform.TRIPO3D)

    def is_valid(self) -> bool:
        """Check if credentials are valid for any platform."""
        if self.platform == APIPlatform.TRIPO3D:
            return bool(self.api_key)
        elif self.platform == APIPlatform.HITEM3D:
            return bool(self.client_id and self.client_secret)
        return False


@dataclass
class GenerationResult:
    """Unified result from any platform."""

    success: bool
    model_path: Optional[str] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    platform_used: Optional[str] = None  # Generic name, not actual platform

    # Additional metadata
    format_type: Optional[str] = None
    resolution: Optional[str] = None


class Unified3DAPI:
    """
    Unified 3D generation API client.

    Automatically selects the best available platform:
    1. Tripo3D (priority)
    2. Hitem3D (fallback)

    Platform details are hidden from the user.
    """

    def __init__(self, credentials: Optional[APICredentials] = None):
        self.credentials = credentials or APICredentials()
        self._tripo_client = None
        self._hitem3d_client = None
        self._primary_platform: Optional[APIPlatform] = None

    async def _get_tripo_client(self):
        """Get or create Tripo3D client."""
        if self._tripo_client is None:
            try:
                from core.tripo3d_client import Tripo3DClient
                import os

                # Check for API key in priority order
                api_key = self.credentials.api_key
                if not api_key:
                    api_key = os.getenv("TRIPO_API_KEY") or os.getenv("API_KEY")

                if api_key:
                    print(
                        f"[API] Initializing Tripo3D client with API key: {api_key[:8]}..."
                    )
                    self._tripo_client = Tripo3DClient(api_key=api_key)
                else:
                    print(f"[API] No Tripo3D API key found")
                    return None

            except Exception as e:
                print(f"[API] Failed to initialize Tripo3D client: {e}")
                import traceback

                traceback.print_exc()
                return None
        return self._tripo_client

    async def _get_hitem3d_client(self):
        """Get or create Hitem3D client."""
        if self._hitem3d_client is None:
            try:
                from core.hitem3d_api import Hitem3DAPI

                self._hitem3d_client = Hitem3DAPI(
                    access_token=self.credentials.access_token,
                    client_id=self.credentials.client_id,
                    client_secret=self.credentials.client_secret,
                )
            except Exception as e:
                print(f"[API] Failed to initialize Hitem3D client: {e}")
                return None
        return self._hitem3d_client

    async def _detect_best_platform(self) -> APIPlatform:
        """Detect which platform to use based on credentials."""
        if self._primary_platform:
            return self._primary_platform

        # Priority 1: Tripo3D (if we have API key)
        if (
            self.credentials.platform == APIPlatform.TRIPO3D
            and self.credentials.api_key
        ):
            # Test if Tripo3D is available using proper async context
            try:
                from core.tripo3d_client import Tripo3DClient
                import os

                api_key = (
                    self.credentials.api_key
                    or os.getenv("TRIPO_API_KEY")
                    or os.getenv("API_KEY")
                )

                if api_key:
                    print(f"[API] Testing Tripo3D connection...")
                    client = Tripo3DClient(api_key=api_key)
                    balance = await client.get_balance()
                    print(f"[API] Tripo3D balance check successful: {balance}")
                    self._primary_platform = APIPlatform.TRIPO3D
                    print("[API] Using primary platform: Cloud 3D Generator")
                    return APIPlatform.TRIPO3D
            except ImportError as e:
                print(f"[API] Tripo3D module not installed: {e}")
                # Try fallback to Hitem3D with credentials
                api_key = self.credentials.api_key or ""
                if ":" in api_key:
                    parts = api_key.split(":", 1)
                    if len(parts) == 2 and parts[0] and parts[1]:
                        self.credentials.client_id = parts[0]
                        self.credentials.client_secret = parts[1]
                        self.credentials.platform = APIPlatform.HITEM3D
            except Exception as e:
                print(f"[API] Tripo3D validation failed: {e}")

        # Priority 2: Hitem3D (fallback)
        if (
            self.credentials.platform == APIPlatform.HITEM3D
            and self.credentials.is_valid()
        ):
            client = await self._get_hitem3d_client()
            if client:
                try:
                    is_valid = await client.validate_access_token()
                    if is_valid:
                        self._primary_platform = APIPlatform.HITEM3D
                        print("[API] Using fallback platform: Cloud 3D Generator")
                        return APIPlatform.HITEM3D
                except Exception as e:
                    print(f"[API] Hitem3D validation failed: {e}")

        # Fallback: If credentials look like AccessKey:SecretKey format but Tripo3D module not available
        if (
            self.credentials.platform == APIPlatform.TRIPO3D
            and self.credentials.api_key
        ):
            # Try to parse as Hitem3D format (might work if user saved AccessKey:SecretKey)
            if ":" in self.credentials.api_key:
                parts = self.credentials.api_key.split(":", 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    # Re-initialize as Hitem3D credentials
                    self.credentials.client_id = parts[0]
                    self.credentials.client_secret = parts[1]
                    self.credentials.platform = APIPlatform.HITEM3D
                    print("[API] Trying credentials as Hitem3D format...")

                    client = await self._get_hitem3d_client()
                    if client:
                        try:
                            is_valid = await client.validate_access_token()
                            if is_valid:
                                self._primary_platform = APIPlatform.HITEM3D
                                print(
                                    "[API] Using fallback platform: Cloud 3D Generator (Hitem3D)"
                                )
                                return APIPlatform.HITEM3D
                        except Exception as e:
                            print(f"[API] Hitem3D fallback validation failed: {e}")

        return APIPlatform.NONE

    async def generate_from_image(
        self,
        image_path: str,
        output_dir: str = "output",
        model_name: str = "model",
        quality: str = "standard",
        format_type: str = "glb",
        progress_callback=None,
        max_wait_time: int = 3600,
    ) -> GenerationResult:
        """
        Generate 3D model from image using best available platform.

        Args:
            image_path: Path to input image
            output_dir: Directory to save output
            model_name: Base name for output file
            quality: Quality preset (draft, standard, high, production)
            format_type: Output format (obj, glb, stl, fbx, usdz)
            progress_callback: Optional callback(percent, message)
            max_wait_time: Maximum time to wait for generation

        Returns:
            GenerationResult with success status and paths
        """
        platform = await self._detect_best_platform()

        if platform == APIPlatform.NONE:
            return GenerationResult(
                success=False,
                error_message="No valid API credentials found. Please enter and save your API key.",
            )

        # Generic platform name for user-facing messages
        platform_display = "Cloud Processing"

        try:
            if platform == APIPlatform.TRIPO3D:
                return await self._generate_with_tripo3d(
                    image_path=image_path,
                    output_dir=output_dir,
                    model_name=model_name,
                    format_type=format_type,
                    progress_callback=progress_callback,
                    max_wait_time=max_wait_time,
                    platform_display=platform_display,
                )
            elif platform == APIPlatform.HITEM3D:
                return await self._generate_with_hitem3d(
                    image_path=image_path,
                    output_dir=output_dir,
                    model_name=model_name,
                    quality=quality,
                    format_type=format_type,
                    progress_callback=progress_callback,
                    max_wait_time=max_wait_time,
                    platform_display=platform_display,
                )
        except Exception as e:
            return GenerationResult(
                success=False,
                error_message=f"Generation failed: {str(e)}",
                platform_used=platform_display,
            )

        # Fallback return in case no platform matched
        return GenerationResult(
            success=False,
            error_message="No processing platform available",
            platform_used=platform_display,
        )

    async def _generate_with_tripo3d(
        self,
        image_path: str,
        output_dir: str,
        model_name: str,
        format_type: str,
        progress_callback,
        max_wait_time: int,
        platform_display: str,
    ) -> GenerationResult:
        """Generate using Tripo3D API."""
        from core.tripo3d_client import Tripo3DClient, TaskStatus
        import os

        # Report initial progress
        if progress_callback:
            progress_callback(5, f"Initializing {platform_display}...")

        # Get API key
        api_key = (
            self.credentials.api_key
            or os.getenv("TRIPO_API_KEY")
            or os.getenv("API_KEY")
        )
        if not api_key:
            return GenerationResult(
                success=False,
                error_message="No Tripo3D API key found",
            )

        try:
            client = Tripo3DClient(api_key=api_key)

            # Create task with progress callback
            if progress_callback:
                progress_callback(8, f"Uploading image to {platform_display}...")

            # Generate from image
            result = await client.image_to_model(
                image_path=image_path,
                progress_callback=progress_callback,
            )

            if progress_callback:
                progress_callback(95, f"Downloading from {platform_display}...")

            # Convert to requested format if needed
            if result.status == TaskStatus.SUCCESS:
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)

                model_file = result.model_path

                # Convert to requested format if different
                if format_type.lower() != "glb" and model_file:
                    try:
                        from core.tripo3d_client import OutputFormat

                        convert_result = await client.convert_model(
                            task_id=result.task_id,
                            output_format=OutputFormat(format_type.lower()),
                        )
                        if convert_result and convert_result.model_path:
                            model_file = convert_result.model_path
                    except Exception as e:
                        print(f"[API] Format conversion failed, using original: {e}")

                if progress_callback:
                    progress_callback(100, "Processing complete!")

                return GenerationResult(
                    success=True,
                    model_path=model_file,
                    task_id=result.task_id,
                    platform_used=platform_display,
                    format_type=format_type,
                )
            else:
                # Task failed - get error from result metadata
                error_msg = "Unknown error"
                if hasattr(result, "metadata") and result.metadata:
                    error_msg = result.metadata.get("error", error_msg)
                return GenerationResult(
                    success=False,
                    error_message=f"{platform_display} processing failed: {error_msg}",
                    task_id=result.task_id,
                    platform_used=platform_display,
                )

        except Exception as e:
            print(f"[API] Tripo3D generation error: {e}")
            import traceback

            traceback.print_exc()
            return GenerationResult(
                success=False,
                error_message=f"{platform_display} generation failed: {str(e)}",
                platform_used=platform_display,
            )

    async def _generate_with_hitem3d(
        self,
        image_path: str,
        output_dir: str,
        model_name: str,
        quality: str,
        format_type: str,
        progress_callback,
        max_wait_time: int,
        platform_display: str,
    ) -> GenerationResult:
        """Generate using Cloud API."""
        client = await self._get_hitem3d_client()
        if not client:
            raise Exception("Failed to initialize Hitem3D client")

        # Map format string to Hitem3D format code
        format_map = {"obj": 1, "glb": 2, "stl": 3, "fbx": 4, "usdz": 5}
        format_code = format_map.get(format_type.lower(), 2)

        # Generate using existing Hitem3D implementation
        result = await client.generate_3d_model(
            image_path=image_path,
            output_dir=output_dir,
            model_name=model_name,
            format_type=format_code,
            progress_callback=progress_callback,
            max_wait_time=max_wait_time,
        )

        # Find the model file
        model_file = None
        for ext, path in result.items():
            if path and os.path.exists(path):
                model_file = path
                break

        return GenerationResult(
            success=bool(model_file),
            model_path=model_file,
            platform_used=platform_display,
            format_type=format_type,
        )

    async def get_balance(self) -> Optional[float]:
        """Get account balance from active platform."""
        platform = await self._detect_best_platform()

        try:
            if platform == APIPlatform.TRIPO3D:
                print(f"[API] Getting balance from Tripo3D...")
                try:
                    from core.tripo3d_client import Tripo3DClient
                    import os

                    # Get API key
                    api_key = (
                        self.credentials.api_key
                        or os.getenv("TRIPO_API_KEY")
                        or os.getenv("API_KEY")
                    )

                    if not api_key:
                        print("[API] No Tripo3D API key found")
                        return None

                    # Use our Tripo3D client
                    client = Tripo3DClient(api_key=api_key)
                    balance = await client.get_balance()
                    print(f"[API] Tripo3D balance response: {balance}")

                    # Handle Tripo3DBalance object - it has remaining_credits attribute
                    if balance and hasattr(balance, "remaining_credits"):
                        return float(balance.remaining_credits)
                    elif balance and hasattr(balance, "total_credits"):
                        return float(balance.total_credits)
                    else:
                        return None

                except Exception as e:
                    print(f"[API] Tripo3D balance error: {e}")
                    import traceback

                    traceback.print_exc()
                    return None

            elif platform == APIPlatform.HITEM3D:
                client = await self._get_hitem3d_client()
                if client:
                    try:
                        balance = await client.get_balance()
                        print(f"[API] Hitem3D balance response: {balance}")
                        if isinstance(balance, dict):
                            return balance.get("balance")
                        return balance
                    except Exception as e:
                        print(f"[API] Hitem3D balance error: {e}")

            # Fallback: if Tripo3D module not available, try Hitem3D with the same credentials
            if platform == APIPlatform.TRIPO3D:
                print("[API] Tripo3D failed, trying fallback to Hitem3D...")
                # Try to interpret the API key as Hitem3D credentials (AccessKey:SecretKey format)
                api_key = self.credentials.api_key or ""
                if ":" in api_key:
                    parts = api_key.split(":", 1)
                    if len(parts) == 2 and parts[0] and parts[1]:
                        # Re-initialize as Hitem3D credentials
                        self.credentials.client_id = parts[0]
                        self.credentials.client_secret = parts[1]
                        self.credentials.platform = APIPlatform.HITEM3D
                        print("[API] Retrying with Hitem3D credentials...")

                        client = await self._get_hitem3d_client()
                        if client:
                            try:
                                balance = await client.get_balance()
                                print(
                                    f"[API] Hitem3D fallback balance response: {balance}"
                                )
                                if isinstance(balance, dict):
                                    return balance.get("balance")
                                return balance
                            except Exception as e:
                                print(f"[API] Hitem3D fallback balance error: {e}")

        except Exception as e:
            print(f"[API] Failed to get balance: {e}")
            import traceback

            traceback.print_exc()

        return None

    async def generate_from_text(
        self,
        prompt: str,
        negative_prompt: str = "",
        output_dir: str = "output",
        model_name: str = "model",
        format_type: str = "glb",
        progress_callback=None,
        max_wait_time: int = 3600,
    ) -> GenerationResult:
        """
        Generate 3D model from text description using Tripo3D.

        Args:
            prompt: Text description of the 3D model to generate
            negative_prompt: Things to avoid in generation
            output_dir: Directory to save output
            model_name: Base name for output file
            format_type: Output format (obj, glb, stl, fbx, usdz)
            progress_callback: Optional callback(percent, message)
            max_wait_time: Maximum time to wait for generation

        Returns:
            GenerationResult with success status and paths
        """
        platform = await self._detect_best_platform()
        platform_display = "Cloud Processing"

        if platform != APIPlatform.TRIPO3D:
            return GenerationResult(
                success=False,
                error_message="Text-to-3D is only available with Tripo3D API. Please use a Tripo3D API key.",
                platform_used=platform_display,
            )

        try:
            from core.tripo3d_client import Tripo3DClient
            import os

            api_key = (
                self.credentials.api_key
                or os.getenv("TRIPO_API_KEY")
                or os.getenv("API_KEY")
            )
            if not api_key:
                return GenerationResult(
                    success=False,
                    error_message="No Tripo3D API key found",
                )

            client = Tripo3DClient(api_key=api_key)

            if progress_callback:
                progress_callback(5, f"Initializing {platform_display}...")

            # Generate from text
            result = await client.text_to_model(
                prompt=prompt,
                negative_prompt=negative_prompt,
                progress_callback=progress_callback,
            )

            if progress_callback:
                progress_callback(95, f"Downloading from {platform_display}...")

            if result.status.name == "SUCCESS":
                if progress_callback:
                    progress_callback(100, "Processing complete!")

                return GenerationResult(
                    success=True,
                    model_path=result.model_path,
                    task_id=result.task_id,
                    platform_used=platform_display,
                    format_type=format_type,
                )
            else:
                error_msg = "Unknown error"
                if hasattr(result, "metadata") and result.metadata:
                    error_msg = result.metadata.get("error", error_msg)
                return GenerationResult(
                    success=False,
                    error_message=f"{platform_display} processing failed: {error_msg}",
                    task_id=result.task_id,
                    platform_used=platform_display,
                )

        except Exception as e:
            print(f"[API] Text-to-3D generation error: {e}")
            import traceback

            traceback.print_exc()
            return GenerationResult(
                success=False,
                error_message=f"{platform_display} generation failed: {str(e)}",
                platform_used=platform_display,
            )

    async def generate_from_multiview(
        self,
        image_paths: List[str],
        output_dir: str = "output",
        model_name: str = "model",
        format_type: str = "glb",
        progress_callback=None,
        max_wait_time: int = 3600,
    ) -> GenerationResult:
        """
        Generate 3D model from multiple views using Tripo3D.

        Args:
            image_paths: List of paths to images (front, side, back views)
            output_dir: Directory to save output
            model_name: Base name for output file
            format_type: Output format (obj, glb, stl, fbx, usdz)
            progress_callback: Optional callback(percent, message)
            max_wait_time: Maximum time to wait for generation

        Returns:
            GenerationResult with success status and paths
        """
        platform = await self._detect_best_platform()
        platform_display = "Cloud Processing"

        if platform != APIPlatform.TRIPO3D:
            return GenerationResult(
                success=False,
                error_message="Multi-view generation is only available with Tripo3D API. Please use a Tripo3D API key.",
                platform_used=platform_display,
            )

        try:
            from core.tripo3d_client import Tripo3DClient
            import os

            api_key = (
                self.credentials.api_key
                or os.getenv("TRIPO_API_KEY")
                or os.getenv("API_KEY")
            )
            if not api_key:
                return GenerationResult(
                    success=False,
                    error_message="No Tripo3D API key found",
                )

            client = Tripo3DClient(api_key=api_key)

            if progress_callback:
                progress_callback(5, f"Initializing {platform_display}...")

            # Generate from multiview
            result = await client.multiview_to_model(
                image_paths=image_paths,
                progress_callback=progress_callback,
            )

            if progress_callback:
                progress_callback(95, f"Downloading from {platform_display}...")

            if result.status.name == "SUCCESS":
                if progress_callback:
                    progress_callback(100, "Processing complete!")

                return GenerationResult(
                    success=True,
                    model_path=result.model_path,
                    task_id=result.task_id,
                    platform_used=platform_display,
                    format_type=format_type,
                )
            else:
                error_msg = "Unknown error"
                if hasattr(result, "metadata") and result.metadata:
                    error_msg = result.metadata.get("error", error_msg)
                return GenerationResult(
                    success=False,
                    error_message=f"{platform_display} processing failed: {error_msg}",
                    task_id=result.task_id,
                    platform_used=platform_display,
                )

        except Exception as e:
            print(f"[API] Multi-view generation error: {e}")
            import traceback

            traceback.print_exc()
            return GenerationResult(
                success=False,
                error_message=f"{platform_display} generation failed: {str(e)}",
                platform_used=platform_display,
            )

    def get_platform_features(self) -> Dict[str, Any]:
        """
        Get features available for the currently configured platform.

        Returns:
            Dictionary with platform features and capabilities
        """
        from core.platform_features import (
            get_available_models,
            get_available_generation_modes,
        )

        # Detect platform without making API calls
        platform_type = "hitem3d"  # Default fallback

        if self.credentials.api_key and not ":" in self.credentials.api_key:
            # Looks like Tripo3D key (no colon)
            platform_type = "tripo3d"
        elif self.credentials.client_id and self.credentials.client_secret:
            # Hitem3D credentials
            platform_type = "hitem3d"

        return {
            "platform_type": platform_type,
            "models": get_available_models(platform_type),
            "generation_modes": get_available_generation_modes(platform_type),
        }

    async def detect_and_get_features(self) -> Dict[str, Any]:
        """
        Detect active platform and return its features.
        Makes API call to verify platform availability.

        Returns:
            Dictionary with detected platform features
        """
        from core.platform_features import (
            get_available_models,
            get_available_generation_modes,
        )

        platform = await self._detect_best_platform()

        if platform == APIPlatform.TRIPO3D:
            return {
                "platform_type": "tripo3d",
                "platform_name": "Cloud 3D Generator",
                "models": get_available_models("tripo3d"),
                "generation_modes": get_available_generation_modes("tripo3d"),
            }
        elif platform == APIPlatform.HITEM3D:
            return {
                "platform_type": "hitem3d",
                "platform_name": "Cloud 3D Generator",
                "models": get_available_models("hitem3d"),
                "generation_modes": get_available_generation_modes("hitem3d"),
            }
        else:
            return {
                "platform_type": "none",
                "platform_name": "No Platform Available",
                "models": {},
                "generation_modes": [],
            }

    async def close(self):
        """Close all API connections."""
        if self._tripo_client:
            try:
                await self._tripo_client.close()
            except:
                pass
            self._tripo_client = None

        if self._hitem3d_client:
            try:
                await self._hitem3d_client.close()
            except:
                pass
            self._hitem3d_client = None


# Backward compatibility wrapper
class Hitem3DAPI(Unified3DAPI):
    """Backward compatibility - redirects to unified API."""

    def __init__(self, *args, **kwargs):
        # Extract credentials from old-style parameters
        access_token = kwargs.get("access_token")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")

        if client_id and client_secret:
            creds = APICredentials(
                client_id=client_id,
                client_secret=client_secret,
                platform=APIPlatform.HITEM3D,
            )
        elif access_token:
            # Try to parse as combined token
            creds = APICredentials.from_string(access_token)
        else:
            creds = APICredentials()

        super().__init__(credentials=creds)

    async def generate_3d_model(self, **kwargs):
        """Backward compatible method."""
        result = await self.generate_from_image(**kwargs)

        # Convert to old format
        if result.success and result.model_path:
            ext = Path(result.model_path).suffix.lstrip(".")
            return {ext: result.model_path}
        return {}

    async def get_balance(self) -> Optional[float]:
        """Backward compatible method."""
        balance = await super().get_balance()
        return balance

    async def validate_access_token(self):
        """Backward compatible method."""
        platform = await self._detect_best_platform()
        return platform != APIPlatform.NONE


# Convenience function for quick access
async def generate_3d_from_image(
    credential_string: str, image_path: str, output_dir: str = "output", **kwargs
) -> GenerationResult:
    """
    Quick generation function.

    Args:
        credential_string: API key or "client_id:secret" format
        image_path: Path to input image
        output_dir: Output directory
        **kwargs: Additional options (quality, format_type, etc.)

    Returns:
        GenerationResult
    """
    credentials = APICredentials.from_string(credential_string)
    api = Unified3DAPI(credentials=credentials)

    try:
        result = await api.generate_from_image(
            image_path=image_path, output_dir=output_dir, **kwargs
        )
    finally:
        await api.close()

    return result
