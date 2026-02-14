# ImageTo3D Pro — User Guide

> **Purpose**: Complete end-user guide covering the trial → purchase → usage journey. Written for both web and desktop interfaces.

---

## 1. Getting Started

### Web App

1. Visit your ImageTo3D Pro instance URL
2. **First visit**: Set an admin password at `/setup`
3. **Register**: Create a user account at `/register`
4. **Login**: Enter your credentials

### Desktop App

1. Launch `ImageTo3DPro.exe` (or `python -m ui.desktop.app`)
2. The app automatically initializes with **1 free trial generation**
3. No login required for desktop (hardware-bound licensing)

---

## 2. Free Trial

Every new user gets **1 free 3D model generation** — no credit card required.

### How It Works

```
First launch → 1 free generation available
↓
Upload image → Generate 3D model → Download OBJ/STL/GLB
↓
Trial used → "Purchase License" prompt shown
```

### Trial Tracking

- **Web App**: Tracked per user account in SQLite database
- **Desktop App**: Tracked per machine via hardware fingerprint in `config/trial.json`

### Trial Limitations

- 1 generation only
- Same quality/features as paid users
- Cannot be reset (unless admin resets via `/admin/reset-trial`)

---

## 3. Generating a 3D Model

### Step 1: Upload Image

- Supported formats: PNG, JPG, JPEG, BMP, WebP
- Best results: Clear single object on neutral background
- Recommended: 1024×1024 resolution
- The app can remove backgrounds automatically

### Step 2: Choose Processing Options

| Option | Description | Default |
|--------|-------------|---------|
| **Quality** | `draft` (fast), `standard`, `high`, `production` (best) | `standard` |
| **Processing** | Local (TripoSR on your CPU) or Cloud (Hitem3D API) | Local |
| **API Model** | `hitem3dv1.5`, `hitem3dv2.0`, `scene-portraitv1.5` | `hitem3dv1.5` |
| **Resolution** | 512, 1024, 1536, 1536pro | 1024 |
| **Output Format** | OBJ, STL, GLB | All three |

### Step 3: Generate

Click **"Generate 3D Model"** and wait:

| Processing Type | Typical Time |
|----------------|-------------|
| Local (draft) | 30-60 seconds |
| Local (standard) | 1-3 minutes |
| Local (high) | 3-5 minutes |
| Local (production) | 5-10 minutes |
| Cloud API | 15-45 seconds |

### Step 4: Download

After generation completes, download your files:

- **OBJ** — Wavefront OBJ (for CAD, 3D printing)
- **STL** — Stereolithography (for 3D printing)
- **GLB** — glTF Binary (for web, AR, Unity, Unreal)

---

## 4. Multi-Angle Processing

Upload 3-5 images of the same object from different angles for **dramatically better quality** (up to 10x improvement).

### Requirements

| Plan | Max Images |
|------|-----------|
| Starter | 3 |
| Pro | 5 |
| Enterprise | Unlimited |

### Tips for Multi-Angle

1. Take photos from evenly spaced angles (e.g., front, 45°, side, back)
2. Keep consistent lighting across all images
3. Same object, same distance, same background
4. Higher quality when more angles are provided

---

## 5. Free Texture-from-Image Feature 🆓

Generate UV-mapped textures from any image — **completely free**, no license required.

### How to Use (Web)

1. Navigate to the texture generation page
2. Upload any image (photo, artwork, pattern)
3. Choose method: `tiling`, `projection`, `color_extraction`
4. Download the generated texture (PNG, 1024×1024)

### Use Cases

- Create tileable textures from photos
- Extract color palettes for 3D models
- Generate environment maps

See [08_FREE_TEXTURE_FROM_IMAGE.md](./08_FREE_TEXTURE_FROM_IMAGE.md) for full details.

---

## 6. Purchasing a License

### Step 1: Choose a Plan

| Plan | Price | Credits/Month | Best For |
|------|-------|--------------|----------|
| **Starter** | ₹499/mo ($5.99) | 100 | Hobbyists, students |
| **Pro** | ₹999/mo ($11.99) | 300 | Freelancers, professionals |
| **Enterprise** | ₹4999/mo ($59.99) | 2000 | Studios, businesses |

### Step 2: Purchase on Gumroad

1. Click the "Purchase License" button in the app
2. You'll be redirected to the Gumroad checkout page
3. Complete payment (credit card, debit card, PayPal)
4. Receive your license key via email

### Step 3: Activate License

**Web App**:
1. Go to `/dashboard`
2. Enter your license key in the activation form
3. Click "Activate"

**Desktop App**:
1. Click "Enter License Key" in the trial dialog
2. Enter your key
3. Click "Activate"

### Step 4: Start Using

Your credits are immediately available. Each operation costs:

| Operation | Credits |
|-----------|---------|
| Local processing | 1 |
| API (512px) | 15 |
| API (1024px) | 20 |
| API (1536px) | 50 |
| API (1536pro) | 70 |
| Texture generation | 0 (free!) |

---

## 7. Credit Packs (Pay-as-You-Go)

Don't want a subscription? Buy credits directly:

| Pack | Credits | Price |
|------|---------|-------|
| Small | 100 | ₹199 ($2.39) |
| Medium | 500 | ₹799 ($9.59) |
| Large | 2000 | ₹2499 ($29.99) |

Credits never expire while your account is active.

---

## 8. User Dashboard

### Web: `/dashboard`

Your dashboard shows:
- **Account Info**: Username, registration date
- **Trial Status**: Generations used / remaining
- **License**: Active plan, credits remaining, expiry date
- **Actions**: Activate license, change password

### Desktop

The status bar shows:
- Trial remaining / Credits remaining
- License status (active/expired)
- Processing mode (local/cloud)

---

## 9. Tips for Best Results

### Image Preparation

1. **Single object**: Works best with one object in frame
2. **Neutral background**: White or solid color backgrounds
3. **Good lighting**: Even, diffused lighting
4. **High resolution**: At least 512×512, ideally 1024×1024
5. **Clear details**: Sharp focus, no motion blur

### Quality Selection

| When to Use | Quality |
|-------------|---------|
| Quick preview | `draft` |
| General purpose | `standard` |
| Professional work | `high` |
| Animation/game assets | `production` |

### Local vs Cloud Processing

| Factor | Local (TripoSR) | Cloud (Hitem3D API) |
|--------|-----------------|-------------------|
| Speed | 1-10 min | 15-45 sec |
| Quality | Good | Excellent |
| Cost | 1 credit | 15-70 credits |
| RAM needed | 6GB+ | None |
| GPU needed | No (CPU works) | No |
| Internet needed | No | Yes |

---

## 10. Troubleshooting

| Issue | Solution |
|-------|----------|
| "Trial exhausted" | Purchase a license or ask admin to reset |
| "Low memory" warning | Use Cloud API processing instead of local |
| Model looks flat/bad | Use multi-angle or try cloud API |
| Slow generation | Switch from `production` to `standard` quality |
| "License expired" | Purchase renewal via Gumroad |
| Can't download files | Clear browser cache, try another browser |

---

*Next: See [07_DEVELOPER_GUIDE.md](./07_DEVELOPER_GUIDE.md) for developer documentation.*
