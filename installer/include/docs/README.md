# 🎨 ImageTo3D Pro

**Convert any image to a production-ready 3D model** — locally on your CPU or via cloud GPU API.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🖼️ **Image → 3D** | Upload a photo, get OBJ + STL + GLB files |
| 🔄 **Multi-Angle** | 3-5 images from different angles for 10x quality |
| ☁️ **Cloud + Local** | Run locally (TripoSR, CPU-first) or via Hitem3D API |
| 🎨 **Free Textures** | Generate UV-ready textures from images — free forever |
| 💳 **Monetized** | Trial → Subscription/Credits via Gumroad, Razorpay, Stripe |
| 🖥️ **Dual Interface** | Web app (FastAPI) + Desktop app (PySide6) |
| 🔒 **Licensing** | Hardware-bound license keys with offline grace period |
| 🚀 **Render Deploy** | One-click deploy to Render.com free tier |

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/imageto3d-pro.git
cd imageto3d-pro
python -m venv venv
venv\Scripts\activate          # Windows
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

### 2. Run Web App

```bash
uvicorn ui.web.api:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` → Set admin password → Start generating!

### 3. Run Desktop App

```bash
python -m ui.desktop.app
```

---

## 📁 Project Structure

```
ImageTo3D_Pro_Full_Working/
├── config/                    # Configuration
│   ├── settings.py            # Central config manager
│   └── payment_config.py      # Payment provider selection & pricing
├── core/                      # Business logic
│   ├── pipeline.py            # Local processing pipeline
│   ├── unified_pipeline.py    # Routes local vs cloud
│   ├── hitem3d_api.py         # Cloud API client
│   ├── auth.py                # Bcrypt authentication
│   ├── user_db.py             # SQLite user database
│   ├── license_manager.py     # License & trial management
│   ├── exporter.py            # OBJ/STL/GLB export via trimesh
│   ├── texture/               # 🆕 Free texture generator
│   │   └── texture_from_image.py
│   ├── inference/             # AI model wrappers
│   │   ├── triposr.py         # TripoSR (CPU-first)
│   │   └── model_manager.py   # Model factory
│   ├── postprocess/           # Mesh cleaning
│   │   └── cleanup.py
│   └── providers/             # Payment providers
│       ├── base.py            # Abstract interface
│       └── gumroad.py         # Gumroad implementation
├── ui/
│   ├── web/api.py             # FastAPI web app (single file)
│   └── desktop/app.py         # PySide6 desktop app
├── tests/                     # Test suite
├── render.yaml                # Render.com deployment
├── requirements.txt           # Python dependencies
└── ImageTo3D_Pro/             # 📖 Complete documentation
    ├── 01_PROJECT_OVERVIEW.md
    ├── 02_SETUP_AND_INSTALLATION.md
    ├── 03_CONFIGURATION_GUIDE.md
    ├── 04_API_REFERENCE.md
    ├── 05_DEPLOYMENT_GUIDE.md
    ├── 06_USER_GUIDE.md
    ├── 07_DEVELOPER_GUIDE.md
    ├── 08_FREE_TEXTURE_FROM_IMAGE.md
    └── 09_MONETIZATION_STRATEGY.md
```

---

## 💰 Pricing

| Plan | Price | Credits/Month |
|------|:-----:|:------------:|
| **Free Trial** | ₹0 | 1 generation |
| **Starter** | ₹499/mo | 100 |
| **Pro** | ₹999/mo | 300 |
| **Enterprise** | ₹4999/mo | 2000 |

> 🎨 **Free texture generation** is unlimited and always free!

---

## 🔧 Environment Variables

| Variable | Description |
|----------|-------------|
| `HITEM3D_ACCESS_TOKEN` | Cloud API token |
| `IMAGETO3D_SECRET_KEY` | Session signing secret |
| `GUMROAD_ACCESS_TOKEN` | Payment provider token |
| `PORT` | Server port (default: 8000) |

---

## 📖 Documentation

All documentation is in the [`ImageTo3D_Pro/`](./ImageTo3D_Pro/) folder:

1. **[Project Overview](./ImageTo3D_Pro/01_PROJECT_OVERVIEW.md)** — Architecture, tech stack, design decisions
2. **[Setup Guide](./ImageTo3D_Pro/02_SETUP_AND_INSTALLATION.md)** — From clone to running
3. **[Configuration](./ImageTo3D_Pro/03_CONFIGURATION_GUIDE.md)** — All settings with full source code
4. **[API Reference](./ImageTo3D_Pro/04_API_REFERENCE.md)** — Every endpoint documented
5. **[Deployment](./ImageTo3D_Pro/05_DEPLOYMENT_GUIDE.md)** — Render.com setup
6. **[User Guide](./ImageTo3D_Pro/06_USER_GUIDE.md)** — End-user workflow
7. **[Developer Guide](./ImageTo3D_Pro/07_DEVELOPER_GUIDE.md)** — Complete module source code
8. **[Free Textures](./ImageTo3D_Pro/08_FREE_TEXTURE_FROM_IMAGE.md)** — Texture generator feature
9. **[Monetization](./ImageTo3D_Pro/09_MONETIZATION_STRATEGY.md)** — Revenue strategy

---

## 🧪 Testing

```bash
python tests/test_improvements.py
python tests/test_payment_system.py
```

---

## 📜 License

Proprietary. All rights reserved.
