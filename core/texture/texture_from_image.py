"""
Free Texture-from-Image Generator

Generates UV-ready textures from any image using CPU-only PIL operations.
Designed to run on Render free tier (512MB RAM, no GPU).

Methods:
    - tiling: Makes images seamlessly tileable
    - projection: Simple UV projection
    - color_extraction: Dominant color → gradient texture
    - normal_map: Generates normal/bump map from image
"""

import os
import io
import math
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

from PIL import Image, ImageFilter, ImageOps, ImageDraw


class TextureFromImage:
    """
    CPU-only texture generator. No GPU, no heavy dependencies.
    Works on Render free tier (512MB RAM).
    """

    SUPPORTED_METHODS = ("tiling", "projection", "color_extraction", "normal_map")
    MAX_INPUT_SIZE = 4096  # Max input dimension
    DEFAULT_OUTPUT_SIZE = (1024, 1024)

    def __init__(self, output_dir: str = "output/textures"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        image_path: str,
        method: str = "tiling",
        output_size: Tuple[int, int] = (1024, 1024),
        output_format: str = "PNG",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate a texture from an input image.

        Args:
            image_path: Path to input image
            method: Generation method (tiling, projection, color_extraction, normal_map)
            output_size: Output texture dimensions (width, height)
            output_format: Output format (PNG, JPEG, WEBP)
            **kwargs: Method-specific parameters

        Returns:
            dict with keys: output_path, method, size, format, processing_time_ms
        """
        if method not in self.SUPPORTED_METHODS:
            raise ValueError(f"Unknown method: {method}. Use one of: {self.SUPPORTED_METHODS}")

        start = datetime.now()

        # Load and validate input
        img = Image.open(image_path).convert("RGB")

        # Limit input size
        if max(img.size) > self.MAX_INPUT_SIZE:
            ratio = self.MAX_INPUT_SIZE / max(img.size)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Generate texture based on method
        if method == "tiling":
            result = self._make_tileable(img, output_size, **kwargs)
        elif method == "projection":
            result = self._uv_projection(img, output_size, **kwargs)
        elif method == "color_extraction":
            result = self._extract_colors(img, output_size, **kwargs)
        elif method == "normal_map":
            result = self._generate_normal_map(img, output_size, **kwargs)
        else:
            raise ValueError(f"Method not implemented: {method}")

        # Generate unique filename
        hash_key = hashlib.md5(f"{image_path}{method}{output_size}".encode()).hexdigest()[:8]
        ext = output_format.lower()
        if ext == "jpeg":
            ext = "jpg"
        filename = f"texture_{method}_{hash_key}.{ext}"
        output_path = self.output_dir / filename

        # Save result
        save_kwargs = {}
        if output_format.upper() == "JPEG":
            save_kwargs["quality"] = kwargs.get("quality", 95)
        elif output_format.upper() == "WEBP":
            save_kwargs["quality"] = kwargs.get("quality", 90)

        result.save(str(output_path), format=output_format, **save_kwargs)

        elapsed_ms = (datetime.now() - start).total_seconds() * 1000

        return {
            "output_path": str(output_path),
            "method": method,
            "size": output_size,
            "format": output_format,
            "processing_time_ms": round(elapsed_ms, 1),
            "file_size_bytes": output_path.stat().st_size,
        }

    def _make_tileable(
        self, img: Image.Image, size: Tuple[int, int],
        blend_width: int = 64, **kwargs
    ) -> Image.Image:
        """
        Make an image seamlessly tileable using edge blending.

        Algorithm:
        1. Resize to target size
        2. Mirror-blend edges (left↔right, top↔bottom)
        3. Result tiles seamlessly in all directions
        """
        img = img.resize(size, Image.LANCZOS)
        w, h = size

        # Create mirrored copies for blending
        flipped_h = ImageOps.mirror(img)
        flipped_v = ImageOps.flip(img)

        # Blend edges horizontally
        result = img.copy()
        bw = min(blend_width, w // 4)

        for x in range(bw):
            alpha = x / bw
            for y in range(h):
                # Left edge: blend with right side of flipped image
                r1, g1, b1 = img.getpixel((x, y))
                r2, g2, b2 = flipped_h.getpixel((x, y))
                r = int(r1 * alpha + r2 * (1 - alpha))
                g = int(g1 * alpha + g2 * (1 - alpha))
                b = int(b1 * alpha + b2 * (1 - alpha))
                result.putpixel((x, y), (r, g, b))

                # Right edge
                rx = w - 1 - x
                r1, g1, b1 = img.getpixel((rx, y))
                r2, g2, b2 = flipped_h.getpixel((rx, y))
                r = int(r1 * alpha + r2 * (1 - alpha))
                g = int(g1 * alpha + g2 * (1 - alpha))
                b = int(b1 * alpha + b2 * (1 - alpha))
                result.putpixel((rx, y), (r, g, b))

        # Blend edges vertically
        bh = min(blend_width, h // 4)
        for y in range(bh):
            alpha = y / bh
            for x in range(w):
                r1, g1, b1 = result.getpixel((x, y))
                r2, g2, b2 = flipped_v.getpixel((x, y))
                r = int(r1 * alpha + r2 * (1 - alpha))
                g = int(g1 * alpha + g2 * (1 - alpha))
                b = int(b1 * alpha + b2 * (1 - alpha))
                result.putpixel((x, y), (r, g, b))

                by = h - 1 - y
                r1, g1, b1 = result.getpixel((x, by))
                r2, g2, b2 = flipped_v.getpixel((x, by))
                r = int(r1 * alpha + r2 * (1 - alpha))
                g = int(g1 * alpha + g2 * (1 - alpha))
                b = int(b1 * alpha + b2 * (1 - alpha))
                result.putpixel((x, by), (r, g, b))

        return result

    def _uv_projection(
        self, img: Image.Image, size: Tuple[int, int], **kwargs
    ) -> Image.Image:
        """
        Simple UV projection — resize and center-crop to exact dimensions.
        Useful for directly applying an image as a texture.
        """
        # Smart crop to aspect ratio
        target_ratio = size[0] / size[1]
        img_ratio = img.width / img.height

        if img_ratio > target_ratio:
            # Image is wider — crop sides
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Image is taller — crop top/bottom
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        return img.resize(size, Image.LANCZOS)

    def _extract_colors(
        self, img: Image.Image, size: Tuple[int, int],
        num_colors: int = 5, pattern: str = "gradient", **kwargs
    ) -> Image.Image:
        """
        Extract dominant colors and generate a texture.

        Args:
            num_colors: Number of dominant colors to extract
            pattern: Output pattern (gradient, stripes, radial)
        """
        # Quantize to find dominant colors
        small = img.resize((64, 64), Image.LANCZOS)
        quantized = small.quantize(colors=num_colors, method=Image.Quantize.FASTOCTREE)
        palette = quantized.getpalette()

        colors = []
        for i in range(num_colors):
            r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
            colors.append((r, g, b))

        # Sort by luminance for pleasing gradients
        colors.sort(key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])

        # Generate pattern
        result = Image.new("RGB", size)
        draw = ImageDraw.Draw(result)
        w, h = size

        if pattern == "gradient":
            for y in range(h):
                # Map y position to color index
                t = y / h * (len(colors) - 1)
                idx = int(t)
                frac = t - idx
                if idx >= len(colors) - 1:
                    idx = len(colors) - 2
                    frac = 1.0

                c1 = colors[idx]
                c2 = colors[idx + 1]
                r = int(c1[0] * (1 - frac) + c2[0] * frac)
                g = int(c1[1] * (1 - frac) + c2[1] * frac)
                b = int(c1[2] * (1 - frac) + c2[2] * frac)
                draw.line([(0, y), (w, y)], fill=(r, g, b))

        elif pattern == "stripes":
            stripe_height = h // num_colors
            for i, color in enumerate(colors):
                y0 = i * stripe_height
                y1 = min((i + 1) * stripe_height, h)
                draw.rectangle([0, y0, w, y1], fill=color)

        elif pattern == "radial":
            cx, cy = w // 2, h // 2
            max_r = math.sqrt(cx**2 + cy**2)
            for y in range(h):
                for x in range(w):
                    d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                    t = min(d / max_r, 1.0) * (len(colors) - 1)
                    idx = int(t)
                    frac = t - idx
                    if idx >= len(colors) - 1:
                        idx = len(colors) - 2
                        frac = 1.0
                    c1, c2 = colors[idx], colors[idx + 1]
                    r = int(c1[0] * (1 - frac) + c2[0] * frac)
                    g = int(c1[1] * (1 - frac) + c2[1] * frac)
                    b = int(c1[2] * (1 - frac) + c2[2] * frac)
                    result.putpixel((x, y), (r, g, b))

        return result

    def _generate_normal_map(
        self, img: Image.Image, size: Tuple[int, int],
        strength: float = 2.0, **kwargs
    ) -> Image.Image:
        """
        Generate a normal map from an image for bump mapping.

        Uses Sobel-like gradient detection on the grayscale image.
        """
        # Convert to grayscale and resize
        gray = img.convert("L").resize(size, Image.LANCZOS)
        import numpy as np

        arr = np.array(gray, dtype=np.float64) / 255.0
        h, w = arr.shape

        # Compute gradients (Sobel-like)
        dx = np.zeros_like(arr)
        dy = np.zeros_like(arr)

        dx[:, 1:] = arr[:, 1:] - arr[:, :-1]
        dy[1:, :] = arr[1:, :] - arr[:-1, :]

        # Scale by strength
        dx *= strength
        dy *= strength

        # Normal map components (tangent space)
        # R = dx mapped to [0, 255]
        # G = dy mapped to [0, 255]
        # B = z component (always pointing up)
        nx = (-dx * 0.5 + 0.5) * 255.0
        ny = (-dy * 0.5 + 0.5) * 255.0
        nz = np.full_like(arr, 255.0)

        # Stack into RGB
        normal_map = np.stack([
            np.clip(nx, 0, 255),
            np.clip(ny, 0, 255),
            np.clip(nz, 0, 255),
        ], axis=-1).astype(np.uint8)

        return Image.fromarray(normal_map, "RGB")

    def get_methods(self) -> List[Dict[str, str]]:
        """List available texture generation methods."""
        return [
            {"id": "tiling", "name": "Seamless Tiling", "description": "Makes images tile seamlessly"},
            {"id": "projection", "name": "UV Projection", "description": "Smart crop for UV application"},
            {"id": "color_extraction", "name": "Color Extraction", "description": "Dominant color gradient/pattern"},
            {"id": "normal_map", "name": "Normal Map", "description": "Generate bump/normal map"},
        ]
