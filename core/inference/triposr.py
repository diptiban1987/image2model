import os
import subprocess
import sys
from pathlib import Path

import open3d as o3d
import psutil


class TripoSRError(RuntimeError):
    """Raised when TripoSR cannot generate a valid mesh."""

    def __init__(
        self, message: str, reason: str = "error", details: dict | None = None
    ):
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


class TripoSR:
    """
    Thin wrapper around the official TripoSR repository.

    Instead of using ``torch.hub.load`` (which expects a ``hubconf.py`` that
    the upstream repo no longer provides), we shell out to its ``run.py``
    script and then load the generated mesh back into Python as an
    ``open3d.geometry.TriangleMesh``.

    Settings are *adaptive*: mc_resolution, chunk_size, and thread counts
    scale automatically based on available system RAM so we get the best
    possible quality without crashing.
    """

    # RAM tier thresholds (in GB of *available* memory at init time)
    # mc_resolution controls marching cubes grid: 256³ = 16.7M points.
    # Memory budget ≈ TripoSR model (~3GB) + volume grid + MC extraction.
    # Tiers calibrated against real-world crash data on Windows 10 / 16GB.
    _TIERS = [
        # (min_available_gb, mc_resolution, chunk_size, bake_texture, texture_res, threads)
        (16, 256, 8192, True, 1024, "4"),  # 16GB+ → full quality
        (12, 192, 8192, True, 512, "4"),  # 12GB+ → high quality
        (8, 160, 8192, False, 512, "2"),  # 8GB+  → good quality (no texture bake)
        (4, 128, 4096, False, 512, "2"),  # 4GB+  → moderate quality
        (2, 96, 2048, False, 256, "1"),  # 2GB+  → minimal quality
    ]
    _MIN_RAM_GB = 2.0  # absolute minimum to even attempt

    def __init__(self, device: str | None = None):
        # Force CPU by default for maximum compatibility and to avoid native
        # CUDA / driver crashes (e.g. Windows exit code 0xC0000005).
        self.device = device or "cpu"

        # Adapt settings immediately on construction
        self._adapt_settings()

        # Location where we expect / manage the TripoSR repo
        self.repo_root = (
            Path(os.path.expanduser("~"))
            / ".cache"
            / "torch"
            / "hub"
            / "VAST-AI-Research_TripoSR_main"
        )
        if not self.repo_root.exists():
            self._ensure_repo()

    def _adapt_settings(self) -> None:
        """Dynamically choose processing parameters based on available RAM."""
        available_gb = psutil.virtual_memory().available / (1024**3)
        self.available_gb = round(available_gb, 2)

        for min_gb, mc_res, chunk, bake, tex_res, threads in self._TIERS:
            if available_gb >= min_gb:
                self.mc_resolution = mc_res
                self.chunk_size = chunk
                self.bake_texture = bake
                self.texture_resolution = tex_res
                self._thread_count = threads
                self._tier_label = f"{min_gb}GB+"
                print(
                    f"[TripoSR] RAM tier: {self._tier_label} "
                    f"(available {available_gb:.1f}GB) => "
                    f"mc_res={mc_res}, chunk={chunk}, threads={threads}, "
                    f"texture={'ON' if bake else 'OFF'}"
                )
                return

        # Below minimum — will be caught in generate()
        self.mc_resolution = 64
        self.chunk_size = 2048
        self.bake_texture = False
        self.texture_resolution = 256
        self._thread_count = "1"
        self._tier_label = "below_minimum"

    def _check_memory_availability(self) -> tuple[bool, float]:
        """Return (ok, available_gb)."""
        available = psutil.virtual_memory().available / (1024**3)
        return available >= self._MIN_RAM_GB, round(available, 2)

    def _ensure_repo(self) -> None:
        """
        Ensure the TripoSR repository is available locally.

        We try to `git clone` the official repo into the expected cache path.
        If this fails (no git, no network, etc.), the generate() call will
        raise a clear error to the user.
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
            raise TripoSRError(
                f"Unable to clone TripoSR repo into {self.repo_root}: {exc}",
                reason="repo_unavailable",
                details={"path": str(self.repo_root)},
            ) from exc

    def generate(self, image_path: str):
        """
        Run TripoSR on the given image and return an Open3D mesh.

        Unlike previous versions, this method will **raise TripoSRError**
        instead of silently returning a fallback sphere mesh.  The caller
        (pipeline / UI) is responsible for showing the error to the user.
        """
        # ---- Memory gate ----
        mem_ok, available_gb = self._check_memory_availability()
        if not mem_ok:
            raise TripoSRError(
                f"Insufficient RAM for local 3D generation. "
                f"Only {available_gb:.1f}GB available, but TripoSR needs at "
                f"least {self._MIN_RAM_GB}GB free RAM. "
                f"Close other applications or use the Cloud API instead.",
                reason="low_memory",
                details={"available_gb": available_gb, "required_gb": self._MIN_RAM_GB},
            )

        # ---- Re-adapt settings (RAM may have changed since __init__) ----
        self._adapt_settings()

        # ---- Attempt inference ----
        try:
            result = self._run_triposr(image_path)
            if isinstance(result, dict) and "mesh" in result:
                payload = dict(result)
                payload.setdefault("fallback", False)
                return payload
            return {
                "mesh": result,
                "fallback": False,
            }
        except TripoSRError:
            raise  # Already a TripoSRError, re-raise as-is
        except Exception as exc:
            error_msg = str(exc)
            # Detect memory-related crashes
            if any(
                kw in error_msg.lower()
                for kw in (
                    "not enough memory",
                    "allocate",
                    "out of memory",
                    "memoryerror",
                )
            ):
                raise TripoSRError(
                    f"TripoSR ran out of memory during processing. "
                    f"Available RAM: {available_gb:.1f}GB. "
                    f"Try closing other applications, or use the Cloud API "
                    f"for cloud-based processing.",
                    reason="memory_error",
                    details={"available_gb": available_gb, "original_error": error_msg},
                ) from exc
            else:
                import traceback

                tb = traceback.format_exc()
                print(f"[TripoSR] ERROR: {exc}")
                print(f"[TripoSR] Traceback: {tb}")
                raise TripoSRError(
                    f"TripoSR failed during 3D generation: {error_msg}. "
                    f"Use the Cloud API for reliable processing.",
                    reason="processing_error",
                    details={"original_error": error_msg},
                ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run_triposr(self, image_path: str):
        image_path = os.path.abspath(image_path)
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Input image not found: {image_path}")

        # Use a deterministic subfolder under output so repeated runs are
        # reusable and users can inspect intermediate artefacts.
        # CRITICAL: must be absolute so subprocess (cwd=repo_root) and our
        # file-existence check both resolve to the same location.
        project_output = Path("output").resolve() / "triposr_direct"
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
        if self.bake_texture:
            cmd.extend(
                ["--bake-texture", "--texture-resolution", str(self.texture_resolution)]
            )

        # Memory and performance optimizations — thread counts are adaptive
        env = os.environ.copy()
        env.setdefault("CUDA_VISIBLE_DEVICES", "")  # Disable CUDA
        env.setdefault("OMP_NUM_THREADS", self._thread_count)
        env.setdefault("MKL_NUM_THREADS", self._thread_count)
        env.setdefault("OPENBLAS_NUM_THREADS", self._thread_count)
        env.setdefault("VECLIB_MAXIMUM_THREADS", self._thread_count)
        env.setdefault("NUMEXPR_NUM_THREADS", self._thread_count)
        env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:64")
        env.setdefault("PYTORCH_JIT", "0")
        env.setdefault("PYTORCH_NO_CUDA_MEMORY_CACHING", "1")

        # Add repo to PYTHONPATH so run.py can import tsr module
        python_path = env.get("PYTHONPATH", "")
        repo_path = str(self.repo_root)
        if python_path:
            env["PYTHONPATH"] = f"{repo_path}{os.pathsep}{python_path}"
        else:
            env["PYTHONPATH"] = repo_path

        print(f"[TripoSR] Running: {' '.join(cmd[:6])}...")
        print(f"[TripoSR] Output dir (absolute): {tmp_dir}")

        # Execute from within the TripoSR repo — use Popen so we can stream
        # progress output in real time instead of blocking silently.
        print(f"[TripoSR] Subprocess starting...")
        proc = subprocess.Popen(
            cmd,
            cwd=self.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        # Read stderr line-by-line (TripoSR logs to stderr via Python logging)
        stderr_lines = []
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    stderr_lines.append(line)
                    print(f"[TripoSR] {line}")
        except Exception:
            pass

        # Read any remaining stdout
        stdout_text = ""
        try:
            stdout_text = proc.stdout.read() or ""
        except Exception:
            pass

        returncode = proc.wait()
        stderr_text = "\n".join(stderr_lines)

        if stdout_text.strip():
            for line in stdout_text.strip().splitlines()[-5:]:
                print(f"[TripoSR stdout] {line}")

        if returncode != 0:
            raise TripoSRError(
                f"TripoSR subprocess failed with exit code {returncode}. "
                f"This typically means the model ran out of memory or a "
                f"dependency is missing. Use the Cloud API for reliable results.\n"
                f"Details: {stderr_text[-800:]}",
                reason="subprocess_crash",
                details={
                    "returncode": returncode,
                    "stderr": stderr_text[-2000:],
                    "stdout": stdout_text[-500:],
                },
            )

        mesh_path = tmp_dir / "0" / f"mesh.{out_format}"
        print(f"[TripoSR] Looking for mesh at: {mesh_path}")
        print(f"[TripoSR] Path exists: {mesh_path.exists()}")
        if not mesh_path.exists():
            # List what's actually in the output dir for diagnosis
            found_files = []
            if tmp_dir.exists():
                for f in tmp_dir.rglob("*"):
                    if f.is_file():
                        found_files.append(str(f))
            print(f"[TripoSR] Files in output dir: {found_files[:20]}")
            raise TripoSRError(
                "TripoSR ran successfully but did not produce an output mesh file. "
                "This usually indicates the model could not extract 3D geometry "
                "from your image. Try a different image with a clear single object, "
                "or use the Cloud API.",
                reason="no_output",
                details={
                    "expected_path": str(mesh_path),
                    "found_files": found_files[:10],
                },
            )

        mesh = o3d.io.read_triangle_mesh(str(mesh_path))
        if mesh.is_empty():
            raise TripoSRError(
                "TripoSR produced an empty mesh. The 3D reconstruction could not "
                "extract meaningful geometry from your image. Try a different image "
                "with a clear single object, or use the Cloud API.",
                reason="empty_mesh",
                details={"mesh_path": str(mesh_path)},
            )

        if self.bake_texture:
            mtl_candidates = list((tmp_dir / "0").glob("*.mtl"))
            tex_candidates = []
            tex_candidates.extend((tmp_dir / "0").glob("*.png"))
            tex_candidates.extend((tmp_dir / "0").glob("*.jpg"))
            tex_candidates.extend((tmp_dir / "0").glob("*.jpeg"))
            textured = {
                "mesh": mesh,
                "textured_assets": {
                    "obj": str(mesh_path),
                    "mtl": str(mtl_candidates[0]) if mtl_candidates else None,
                    "texture": str(tex_candidates[0]) if tex_candidates else None,
                },
            }
            return textured
        return mesh
