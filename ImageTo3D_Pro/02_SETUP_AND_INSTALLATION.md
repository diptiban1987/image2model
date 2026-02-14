# ImageTo3D Pro — Setup & Installation Guide

> **Purpose**: Complete step-by-step guide to set up ImageTo3D Pro from scratch on Windows, Linux, or macOS. Every command, every file, every dependency.

---

## 1. Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **Python** | 3.10 | 3.11+ |
| **RAM** | 4GB (API only) | 16GB (local TripoSR) |
| **Disk** | 2GB | 10GB (with model cache) |
| **GPU** | Not required | NVIDIA CUDA (optional, for faster TripoSR) |
| **OS** | Windows 10, Ubuntu 20.04, macOS 12 | Latest |
| **Git** | Required | Latest |

---

## 2. Clone the Repository

```bash
git clone https://github.com/diptiban1987/image2model.git ImageTo3D_Pro_Full_Working
cd ImageTo3D_Pro_Full_Working
```

---

## 3. Create Virtual Environment

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 4. Install Dependencies

### File: `requirements.txt`

Create this file at project root:

```txt
# ImageTo3D Pro - pinned for reproducibility
bcrypt>=4.0,<5
torch>=2.0,<3.0
torchvision
numpy>=1.24,<2.0
pillow
opencv-python<4.10
open3d
trimesh
fastapi
uvicorn[standard]
pyside6>=6.5
tqdm
rembg
psutil
httpx
gunicorn
python-multipart
```

### Install command:

```bash
pip install -r requirements.txt
```

> **Note for Render/cloud deployments**: Consider using `torch` CPU-only build to save disk:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

---

## 5. Create Required Directories

```bash
# These are created automatically but you can pre-create:
mkdir -p config input output logs models
```

---

## 6. Initial Admin Setup (Web App)

### Option A: Using the setup script

```python
# File: setup_admin.py (already exists at project root)
"""Setup script for creating admin user."""

from core.user_db import create_user, admin_exists

if not admin_exists():
    print("Creating admin user...")
    create_user("admin", "your_secure_password_here", is_admin=True)
    print("Admin user created!")
else:
    print("Admin already exists.")
```

Run:
```bash
python setup_admin.py
```

### Option B: Set password via auth module (server-side bcrypt):

```bash
python -m core.auth set-password
# Prompts for password (min 8 chars)
# Stores bcrypt hash in config/auth.json
```

---

## 7. Configure Hitem3D API (Optional)

If you want cloud-based 3D generation, create:

### File: `config/hitem3d_credentials.json`

```json
{
  "access_token": "YOUR_HITEM3D_ACCESS_TOKEN",
  "client_id": null,
  "client_secret": null
}
```

Or set environment variables:
```bash
export HITEM3D_ACCESS_TOKEN="your_token_here"
```

---

## 8. Run the Application

### 8A. Web App (FastAPI)

**Development mode:**
```bash
# Windows
.venv\Scripts\uvicorn.exe ui.web.api:app --reload --host 0.0.0.0

# Linux/macOS
uvicorn ui.web.api:app --reload --host 0.0.0.0
```

**Production mode (Gunicorn):**
```bash
gunicorn ui.web.api:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Open: [http://localhost:8000](http://localhost:8000)

### 8B. Desktop App (PySide6)

```bash
# Windows
.venv\Scripts\python.exe -m ui.desktop.app

# Linux/macOS
python -m ui.desktop.app
```

---

## 9. Build Desktop Executable

```bash
python -m PyInstaller --noconfirm --onefile --windowed --name ImageTo3DPro ui/desktop/app.py
```

Output: `dist/ImageTo3DPro.exe`

---

## 10. Run Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific test suites
python tests/test_improvements.py
python tests/test_payment_system.py
```

---

## 11. First-Time Usage Checklist

- [ ] Clone repository
- [ ] Create virtual environment
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Create admin user (`python setup_admin.py`)
- [ ] (Optional) Configure Hitem3D API credentials
- [ ] Run web app (`uvicorn ui.web.api:app --reload --host 0.0.0.0`)
- [ ] Open http://localhost:8000
- [ ] Set application password on first visit
- [ ] Upload an image and generate your first 3D model
- [ ] Check `output/` folder for generated files

---

## 12. Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'core'` | Run from project root: `cd ImageTo3D_Pro_Full_Working` |
| `torch` install fails | Use CPU-only: `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| `PySide6` won't install | Desktop only — skip for web-only deployment |
| TripoSR runs out of memory | Use Hitem3D API instead (set `use_api=True`) |
| Port already in use | Change port: `uvicorn ui.web.api:app --port 8001` |
| `bcrypt` error on install | Windows: `pip install bcrypt --no-binary :all:` |
| `open3d` fails on ARM Mac | Use `pip install open3d --no-deps` and install deps manually |

---

*Next: See [03_CONFIGURATION_GUIDE.md](./03_CONFIGURATION_GUIDE.md) for all configuration options.*
