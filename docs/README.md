# ImageTo3D Pro

A full offline + SaaS-ready AI 2D → 3D system. Convert a single image into 3D mesh files (OBJ, STL, GLB) using local processing (TripoSR) or the Hitem3D cloud API.

## Features

- **Local processing**: Run TripoSR on your machine (GPU recommended, 8GB+ RAM).
- **Hitem3D API**: Optional cloud processing with multiple models and resolutions.
- **Mesh quality presets**: Draft (fast), Standard, High, Production—with advanced mesh repair, smoothing, and topology optimization for higher presets.
- **Export**: OBJ (with vertex colors), STL, and GLB with optional scale factor.
- **Interfaces**: Desktop app (PySide6) and web UI (FastAPI) with drag-and-drop and download links.

## Setup

1. **Create a virtual environment** (recommended):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # Linux/macOS
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Optional – Hitem3D API**:  
   Put `config/hitem3d_credentials.json` with `access_token` (or `client_id`/`client_secret`), or set env vars `HITEM3D_ACCESS_TOKEN` / `HITEM3D_CLIENT_ID` & `HITEM3D_CLIENT_SECRET`.

## Usage

### Desktop app

```bash
python -m ui.desktop.app
```

- Choose an image, pick **Local** or **Hitem3D API**, set **Mesh quality** for local (Draft/Standard/High/Production).
- Click **Generate 3D Model**. Outputs appear under `output/`; use **Open** next to each format or **Open Output Folder**.

### Web UI

```bash
uvicorn ui.web.api:app --reload --host 0.0.0.0
```

- Open http://localhost:8000, upload an image, set processing method and (for local) quality, then generate. Use the **Download OBJ/STL/GLB** links when done.

### Python API

```python
from core.unified_pipeline import run_pipeline

# Local with quality and output directory
result = run_pipeline(
    "path/to/image.png",
    name="my_model",
    output_dir="output",
    quality="high",      # draft | standard | high | production
    scale=1.0,
)
# result["obj"], result["stl"], result["glb"], result["stats"]

# Hitem3D API
result = run_pipeline(
    "path/to/image.png",
    use_api=True,
    api_token="your-token",
    api_model="hitem3dv1.5",
    api_resolution="1024",
)
```

## Pipeline options

| Option        | Description |
|---------------|-------------|
| `output_dir`  | Directory for OBJ/STL/GLB (default: `output`). |
| `quality`     | Local mesh quality: `draft` (fast cleanup only), `standard`, `high`, `production` (advanced repair, smoothing, subdivision). |
| `scale`       | Scale factor applied to the mesh at export (default: 1.0). |

## API endpoints (web)

| Method | Path                      | Description |
|--------|---------------------------|-------------|
| GET    | `/`                       | Web UI (upload, options, download links). |
| POST   | `/generate`               | Upload image + options; returns paths, stats, and `*_url` download links. |
| GET    | `/download?path=<filename>` | Download a generated file from `output/` (filename only). |
| GET    | `/models`                 | Available local/API models and resolutions. |
| GET    | `/credentials/availability` | Whether server-side Hitem3D credentials are set. |

## License

See project license file.
