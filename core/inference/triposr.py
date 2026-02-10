import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import open3d as o3d
import torch
import psutil


class TripoSR:
    """
    Thin wrapper around the official TripoSR repository.

    Instead of using ``torch.hub.load`` (which expects a ``hubconf.py`` that
    the upstream repo no longer provides), we shell out to its ``run.py``
    script and then load the generated mesh back into Python as an
    ``open3d.geometry.TriangleMesh``.
    """

    def __init__(self, device: str | None = None):
        # Force CPU by default for maximum compatibility and to avoid native
        # CUDA / driver crashes (e.g. Windows exit code 0xC0000005).
        # You can pass device="cuda:0" when creating ModelManager if you have
        # a stable GPU setup.
        self.device = device or "cpu"

        # Optimized settings for CPU processing with limited memory.
        # Higher resolution and chunk size improve surface fidelity but increase memory/time.
        self.mc_resolution = 256
        self.chunk_size = 8192

        # Location where we expect / manage the TripoSR repo
        self.repo_root = Path(os.path.expanduser("~")) / ".cache" / "torch" / "hub" / "VAST-AI-Research_TripoSR_main"
        if not self.repo_root.exists():
            self._ensure_repo()

    def _check_memory_availability(self) -> bool:
        """Check if there's enough memory available for TripoSR processing."""
        available_memory = psutil.virtual_memory().available / (1024**3)  # GB
        # TripoSR typically needs at least 6GB for model loading + processing
        min_required = 6.0
        return available_memory >= min_required

    def _ensure_repo(self) -> None:
        """
        Ensure the TripoSR repository is available locally.

        We try to `git clone` the official repo into the expected cache path.
        If this fails (no git, no network, etc.), the generate() call will
        gracefully fall back to the built‑in sphere mesh.
        """
        url = "https://github.com/VAST-AI-Research/TripoSR.git"
        self.repo_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(self.repo_root)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Unable to clone TripoSR repo into {self.repo_root}: {exc}"
            ) from exc

    def generate(self, image_path: str):
        """
        Run TripoSR on the given image and return an Open3D mesh.

        If TripoSR crashes or is not usable on this machine, we fall back to
        a lightweight built‑in mesh generator so that the rest of the app
        continues to function.
        """
        # Check memory availability first
        if not self._check_memory_availability():
            available_gb = psutil.virtual_memory().available / (1024**3)
            print(f"[TripoSR] Warning: Low memory detected ({available_gb:.1f}GB available).")
            print(f"[TripoSR] TripoSR requires at least 6GB RAM. Consider using Hitem3D API processing.")
            print(f"[TripoSR] Falling back to basic mesh.")
            mesh = self._fallback_mesh()
            return {
                "mesh": mesh,
                "fallback": True,
                "fallback_reason": "low_memory",
                "available_gb": round(available_gb, 2),
            }
        
        try:
            mesh = self._run_triposr(image_path)
            return {
                "mesh": mesh,
                "fallback": False,
            }
        except Exception as exc:  # pragma: no cover - surfaced via UI
            # Check if it's a memory-related error
            error_msg = str(exc)
            reason = "error"
            if "not enough memory" in error_msg.lower() or "allocate" in error_msg.lower():
                reason = "memory_error"
                print(f"[TripoSR] Memory allocation failed during processing.")
                print(f"[TripoSR] Available RAM may be insufficient for local processing.")
                print(f"[TripoSR] Consider using Hitem3D API processing instead.")
            else:
                print(f"[TripoSR] Falling back to basic mesh due to error: {exc}")
            # Fallback: still return a valid mesh so the pipeline never breaks.
            mesh = self._fallback_mesh()
            return {
                "mesh": mesh,
                "fallback": True,
                "fallback_reason": reason,
                "error": error_msg,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run_triposr(self, image_path: str) -> o3d.geometry.TriangleMesh:
        image_path = os.path.abspath(image_path)
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Input image not found: {image_path}")

        # Use a deterministic subfolder under output so repeated runs are
        # reusable and users can inspect intermediate artefacts.
        project_output = Path("output") / "triposr_direct"
        project_output.mkdir(parents=True, exist_ok=True)
        tmp_dir = project_output

        # TripoSR's run.py will create subdirs 0/, 1/, ... per input image
        out_format = "obj"
        cmd = [
            sys.executable,
            "run.py",
            image_path,
            "--device",
            self.device,
            "--output-dir",
            str(tmp_dir),
            "--model-save-format",
            out_format,
            "--chunk-size",
            str(self.chunk_size),
            "--mc-resolution",
            str(self.mc_resolution),
        ]

        # Memory and performance optimizations for CPU processing
        env = os.environ.copy()
        env.setdefault("CUDA_VISIBLE_DEVICES", "")  # Disable CUDA
        env.setdefault("OMP_NUM_THREADS", "2")    # Reduce threads for memory efficiency
        env.setdefault("MKL_NUM_THREADS", "2")    # Reduce threads for memory efficiency
        env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")  # Memory fragmentation control
        env.setdefault("PYTORCH_JIT", "0")        # Disable JIT to save memory

        # Execute from within the TripoSR repo
        try:
            subprocess.run(
                cmd,
                cwd=self.repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"TripoSR failed with code {exc.returncode}:\nSTDOUT:\n{exc.stdout}\n\nSTDERR:\n{exc.stderr}"
            ) from exc

        mesh_path = tmp_dir / "0" / f"mesh.{out_format}"
        if not mesh_path.exists():
            # If TripoSR ran but didn't emit a mesh, fall back gracefully.
            return self._fallback_mesh()

        mesh = o3d.io.read_triangle_mesh(str(mesh_path))
        if mesh.is_empty():
            return self._fallback_mesh()
        return mesh

    def _fallback_mesh(self) -> o3d.geometry.TriangleMesh:
        """
        Very lightweight built‑in mesh used when TripoSR cannot run.
        Generates a simple smooth sphere so export and visualization still work.
        """
        mesh = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=32)
        mesh.compute_vertex_normals()

        # Give the sphere a simple color gradient so users can see structure.
        vertices = np.asarray(mesh.vertices)
        colors = np.zeros_like(vertices)
        # Map Y coordinate to a blue‑white gradient
        y = (vertices[:, 1] - vertices[:, 1].min()) / (
            (vertices[:, 1].ptp() or 1.0)
        )
        colors[:, 2] = 0.5 + 0.5 * y  # blue channel
        colors[:, 1] = 0.2 + 0.3 * (1 - y)  # green channel
        mesh.vertex_colors = o3d.utility.Vector3dVector(colors)
        return mesh
