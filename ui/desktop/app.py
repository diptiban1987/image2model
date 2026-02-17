"""
ImageTo3D Pro — Desktop Application
====================================
Full-featured desktop app mirroring all web app capabilities:
  - Device fingerprint security login (hardware-locked)
  - Image upload with preview
  - Local (TripoSR) and Cloud API processing
  - Live progress bar with heartbeat updates
  - Color-coded RAM display (green/amber/red)
  - Activity log with timestamps
  - Multi-angle processing
  - License/trial system
  - Auto-update checker
"""

import os
import sys
import asyncio
import json
import tempfile
import subprocess
import shutil
import urllib.request
import urllib.error
from urllib.parse import urlparse
from typing import List
import platform
import psutil
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QProgressBar,
    QPlainTextEdit,
    QGroupBox,
    QGridLayout,
    QSizePolicy,
    QRadioButton,
    QComboBox,
    QFormLayout,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QScrollArea,
    QCheckBox,
    QTabWidget,
    QStackedWidget,
    QSpacerItem,
)
from PySide6.QtGui import QPixmap, QFont, QColor, QPalette, QIcon
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QSize
from PySide6.QtGui import QDesktopServices

# Ensure project root is on sys.path when running this file directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.unified_pipeline import (
    run_pipeline,
    get_available_models,
    validate_api_token,
    resolve_hitem3d_credentials,
    save_hitem3d_credentials,
    get_hitem3d_balance,
)
from core.auth import is_password_configured, verify_password, set_password
from core.device_fingerprint import (
    get_device_fingerprint,
    get_device_fingerprint_short,
    get_device_info_display,
    verify_device_fingerprint,
    generate_device_fingerprint,
)
from ui.desktop.multiangle_widget import MultiAngleWidget
from core.multiangle_processor import run_multiangle_pipeline

# Try to import license dialog (optional — app works without it)
try:
    from ui.desktop.license_dialog import require_license_dialog
    from core.license_manager import get_license_manager

    HAS_LICENSE = True
except ImportError:
    HAS_LICENSE = False

APP_VERSION = "2.0.0"
UPDATE_URL = os.getenv("IMAGETO3D_UPDATE_URL", "").strip()
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
DEVICE_AUTH_FILE = CONFIG_DIR / "device_auth.json"


# ═══════════════════════════════════════════════════════════════════
#  DEVICE FINGERPRINT AUTH STORAGE
# ═══════════════════════════════════════════════════════════════════


def _load_device_auth() -> dict:
    """Load device auth config."""
    if DEVICE_AUTH_FILE.exists():
        try:
            with open(DEVICE_AUTH_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_device_auth(data: dict) -> None:
    """Save device auth config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(DEVICE_AUTH_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_device_registered() -> bool:
    """Check if this device has a registered password."""
    auth = _load_device_auth()
    fp = get_device_fingerprint()
    device_entry = auth.get(fp)
    return bool(device_entry and device_entry.get("password_hash"))


def register_device(password: str) -> None:
    """Register this device with a password."""
    try:
        import bcrypt

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
            "ascii"
        )
    except ImportError:
        import hashlib

        hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()

    fp = get_device_fingerprint()
    fp_data = generate_device_fingerprint()
    auth = _load_device_auth()
    auth[fp] = {
        "password_hash": hashed,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "machine_name": fp_data["components"].get("machine_name", "Unknown"),
        "platform": fp_data["platform"],
        "device_id_short": get_device_fingerprint_short(),
    }
    _save_device_auth(auth)


def verify_device_password(password: str) -> bool:
    """Verify password for this device."""
    auth = _load_device_auth()
    fp = get_device_fingerprint()
    device = auth.get(fp)
    if not device or not device.get("password_hash"):
        return False
    stored = device["password_hash"]

    try:
        import bcrypt

        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("ascii"))
    except ImportError:
        import hashlib

        return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored


# ═══════════════════════════════════════════════════════════════════
#  VERSION HELPERS
# ═══════════════════════════════════════════════════════════════════


def _normalize_version(value: str) -> tuple:
    if not value:
        return ()
    parts = []
    for raw in value.replace("-", ".").split("."):
        digits = "".join(ch for ch in raw if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _is_newer_version(current: str, latest: str) -> bool:
    cur = _normalize_version(current)
    lat = _normalize_version(latest)
    if not cur or not lat:
        return False
    max_len = max(len(cur), len(lat))
    cur += (0,) * (max_len - len(cur))
    lat += (0,) * (max_len - len(lat))
    return lat > cur


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _fetch_update_info(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ImageTo3DPro"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Update payload must be a JSON object")
    return data


def _safe_filename_from_url(url: str) -> str:
    name = os.path.basename(urlparse(url).path)
    return name or "ImageTo3DPro.exe"


def _launch_update_script(current_exe: str, new_exe: str) -> None:
    pid = os.getpid()
    script = "\n".join(
        [
            "@echo off",
            "setlocal",
            f'set "EXE_PATH={current_exe}"',
            f'set "NEW_EXE={new_exe}"',
            f'set "PID={pid}"',
            ":wait",
            'tasklist /FI "PID eq %PID%" | find "%PID%" >nul',
            "if %ERRORLEVEL%==0 (",
            "  timeout /t 1 /nobreak >nul",
            "  goto wait",
            ")",
            'move /Y "%NEW_EXE%" "%EXE_PATH%"',
            'start "" "%EXE_PATH%"',
            'del "%~f0"',
            "endlocal",
        ]
    )
    fd, path = tempfile.mkstemp(suffix=".cmd")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(script)
    subprocess.Popen(["cmd", "/c", path], close_fds=True)


# ═══════════════════════════════════════════════════════════════════
#  DEVICE LOGIN DIALOG (Fingerprint-locked)
# ═══════════════════════════════════════════════════════════════════


class DeviceLoginDialog(QDialog):
    """
    Device fingerprint-based login.
    Shows device ID, requires password, locked to hardware.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image → 3D Pro — Login")
        self.setFixedSize(420, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 24, 28, 24)

        # App title - compact
        title = QLabel("🔒 Image → 3D Pro")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: #60a5fa; margin-bottom: 4px;"
        )
        layout.addWidget(title)

        subtitle = QLabel("Device-Locked Security")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 12px; color: #64748b; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # Device info card - compact
        device_box = QGroupBox("Device Information")
        device_box.setStyleSheet("""
            QGroupBox {
                border: 1px solid #3b82f6;
                border-radius: 8px;
                margin-top: 8px;
                padding: 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                color: #60a5fa;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                font-size: 11px;
                text-transform: uppercase;
            }
        """)
        dev_layout = QFormLayout(device_box)
        dev_layout.setSpacing(6)

        fp_short = get_device_fingerprint_short()
        fp_data = generate_device_fingerprint()
        comp = fp_data["components"]

        # Device ID
        device_id = QLabel(fp_short)
        device_id.setStyleSheet(
            "color: #60a5fa; font-size: 13px; font-weight: 600; font-family: 'JetBrains Mono', monospace;"
        )
        device_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dev_layout.addRow("Device ID:", device_id)

        # Machine
        machine_lbl = QLabel(comp.get("machine_name", "Unknown"))
        machine_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        dev_layout.addRow("Machine:", machine_lbl)

        # Platform
        platform_lbl = QLabel(platform.system() + " " + platform.release())
        platform_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        dev_layout.addRow("Platform:", platform_lbl)

        # Status
        is_reg = is_device_registered()
        status_lbl = QLabel("✓ Registered" if is_reg else "New Device")
        status_lbl.setStyleSheet(
            f"color: {'#22c55e' if is_reg else '#f59e0b'}; font-size: 12px; font-weight: 600;"
        )
        dev_layout.addRow("Status:", status_lbl)

        layout.addWidget(device_box)

        # Password section - compact
        if is_device_registered():
            layout.addWidget(QLabel("Enter your password:"))
            self.password_edit = QLineEdit()
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.password_edit.setPlaceholderText("Password")
            self.password_edit.returnPressed.connect(self._login)
            layout.addWidget(self.password_edit)

            self.login_btn = QPushButton("🔓 Login")
            self.login_btn.setProperty("success", "true")
            self.login_btn.clicked.connect(self._login)
            layout.addWidget(self.login_btn)
        else:
            layout.addWidget(QLabel("Set up a password for this device:"))

            self.password_edit = QLineEdit()
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.password_edit.setPlaceholderText("New password (min 8 chars)")
            layout.addWidget(self.password_edit)

            self.confirm_edit = QLineEdit()
            self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_edit.setPlaceholderText("Confirm password")
            self.confirm_edit.returnPressed.connect(self._register)
            layout.addWidget(self.confirm_edit)

            self.login_btn = QPushButton("🔐 Register & Login")
            self.login_btn.setProperty("success", "true")
            self.login_btn.clicked.connect(self._register)
            layout.addWidget(self.login_btn)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setStyleSheet(
            "color: #ef4444; font-weight: 600; font-size: 12px;"
        )
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        layout.addStretch()

        # Footer
        footer = QLabel(f"v{APP_VERSION} • Hardware-locked license")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #475569; font-size: 10px;")
        layout.addWidget(footer)

    def _login(self):
        pwd = self.password_edit.text()
        if not pwd:
            self.error_label.setText("Please enter your password.")
            return
        if verify_device_password(pwd):
            self.accept()
        else:
            self.error_label.setText("❌ Incorrect password for this device.")
            self.password_edit.clear()
            self.password_edit.setFocus()

    def _register(self):
        pwd = self.password_edit.text()
        confirm = self.confirm_edit.text() if hasattr(self, "confirm_edit") else pwd
        if not pwd:
            self.error_label.setText("Please enter a password.")
            return
        if len(pwd) < 8:
            self.error_label.setText("Password must be at least 8 characters.")
            return
        if pwd != confirm:
            self.error_label.setText("Passwords do not match.")
            return
        try:
            register_device(pwd)
            QMessageBox.information(
                self,
                "Device Registered",
                f"✅ Device registered successfully!\n\n"
                f"Device ID: {get_device_fingerprint_short()}\n"
                f"Your password is locked to this hardware.\n\n"
                f"Remember this password — it cannot be recovered.",
            )
            self.accept()
        except Exception as e:
            self.error_label.setText(f"Registration failed: {e}")


# ═══════════════════════════════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════════════════════════════


class PipelineWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)
    progress = Signal(int, str)  # (percent, message)

    def __init__(
        self,
        image_path,
        use_api=False,
        api_token=None,
        api_model="hitem3dv1.5",
        api_resolution="1024",
        api_format="glb",
        quality="standard",
        parent=None,
    ):
        super().__init__(parent)
        self.image_path = image_path
        self.use_api = use_api
        self.api_token = api_token
        self.api_model = api_model
        self.api_resolution = api_resolution
        self.api_format = api_format
        self.quality = quality

    def run(self):
        try:

            def _progress_cb(stage, pct, msg):
                self.progress.emit(int(pct), msg)

            result = run_pipeline(
                self.image_path,
                use_api=self.use_api,
                api_token=self.api_token,
                api_model=self.api_model,
                api_resolution=self.api_resolution,
                api_format=self.api_format,
                quality=self.quality,
                progress_callback=_progress_cb,
            )
            self.progress.emit(100, "Complete!")
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class MultiAngleWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)
    progress = Signal(int, str)

    def __init__(
        self,
        image_paths,
        use_api=False,
        api_token=None,
        api_model="hitem3dv1.5",
        api_resolution="1024",
        api_format="glb",
        quality="standard",
        parent=None,
    ):
        super().__init__(parent)
        self.image_paths = image_paths
        self.use_api = use_api
        self.api_token = api_token
        self.api_model = api_model
        self.api_resolution = api_resolution
        self.api_format = api_format
        self.quality = quality

    def run(self):
        try:
            self.progress.emit(10, "Starting multi-angle processing...")
            result = run_multiangle_pipeline(
                self.image_paths,
                name="multiangle_model",
                use_api=self.use_api,
                api_token=self.api_token,
                api_model=self.api_model,
                api_resolution=self.api_resolution,
                api_format=self.api_format,
                quality=self.quality,
            )
            self.progress.emit(100, "Complete!")
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateCheckWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, url, current_version, parent=None):
        super().__init__(parent)
        self.url = url
        self.current_version = current_version

    def run(self):
        try:
            info = _fetch_update_info(self.url)
            latest = str(info.get("version") or "").strip()
            download_url = str(info.get("url") or "").strip()
            notes = str(info.get("notes") or "").strip()
            self.finished.emit(
                {
                    "update_available": bool(
                        latest
                        and download_url
                        and _is_newer_version(self.current_version, latest)
                    ),
                    "version": latest,
                    "url": download_url,
                    "notes": notes,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            temp_dir = tempfile.mkdtemp(prefix="imagetoad_update_")
            filename = _safe_filename_from_url(self.url)
            target = os.path.join(temp_dir, filename)
            req = urllib.request.Request(
                self.url, headers={"User-Agent": "ImageTo3DPro"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(target, "wb") as handle:
                    shutil.copyfileobj(resp, handle)
            self.finished.emit(target)
        except Exception as exc:
            self.failed.emit(str(exc))


# ═══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION WINDOW
# ═══════════════════════════════════════════════════════════════════


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Image → 3D Pro v{APP_VERSION}")
        self.setMinimumSize(900, 700)

        self.worker = None
        self.update_worker = None
        self.download_worker = None
        self.selected_path = None
        self.outputs = {}
        self._preview_pix = QPixmap()
        self.balance_available = None
        self.balance_error = None
        self._start_time = None
        self.multiangle_mode = False
        self.multiangle_paths = []

        self.balance_timer = QTimer(self)
        self.balance_timer.setSingleShot(True)
        self.balance_timer.timeout.connect(self._fetch_balance)

        self.credit_costs = {
            # Hitem3D models
            "hitem3dv1.5": {"512": 15, "1024": 20, "1536": 50, "1536pro": 70},
            "hitem3dv2.0": {"1536": 75, "1536pro": 90},
            "scene-portraitv1.5": {"1536": 70},
            "scene-portraitv2.0": {"1536pro": 70},
            "scene-portraitv2.1": {"1536pro": 70},
            # Tripo3D models (estimated credits based on resolution)
            "v2_5": {"512": 10, "1024": 20, "2048": 40},
            "v2_0": {"1024": 25, "2048": 50},
            "v1_4": {"512": 8, "1024": 15},
        }

        self._build_ui()
        self._update_model_description()
        self._update_run_enabled()
        self._refresh_system_info()

        # Load saved API credentials
        self._load_saved_credentials()

        self.system_timer = QTimer(self)
        self.system_timer.timeout.connect(self._refresh_system_info)
        self.system_timer.start(5000)

        QTimer.singleShot(800, self._check_for_updates)

    # ═══════════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── LEFT SIDEBAR ──
        sidebar = QWidget()
        sidebar.setObjectName("SidebarWidget")
        sidebar.setFixedWidth(260)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 20, 16, 20)
        sb_layout.setSpacing(16)

        # App logo area - compact
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(4)

        logo = QLabel("🎨 Image → 3D Pro")
        logo.setStyleSheet("font-size: 20px; font-weight: 700; color: #60a5fa;")
        logo.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(logo)

        ver_label = QLabel(f"v{APP_VERSION}")
        ver_label.setAlignment(Qt.AlignCenter)
        ver_label.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500;")
        logo_layout.addWidget(ver_label)

        sb_layout.addWidget(logo_container)

        # Device info - compact card
        device_box = self._build_device_info_box()
        sb_layout.addWidget(device_box)

        # System panel - compact
        system_box = self._build_system_panel()
        sb_layout.addWidget(system_box)

        sb_layout.addStretch()

        # Bottom buttons - compact
        logout_btn = QPushButton("🔒 Log Out")
        logout_btn.setProperty("secondary", "true")
        logout_btn.clicked.connect(self._logout)
        sb_layout.addWidget(logout_btn)

        quit_btn = QPushButton("✕ Quit")
        quit_btn.setProperty("danger", "true")
        quit_btn.clicked.connect(QApplication.instance().quit)
        sb_layout.addWidget(quit_btn)

        main_layout.addWidget(sidebar)

        # ── MAIN CONTENT ──
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)

        # Row 1: Input + Processing Options (compact side-by-side)
        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        top_row.addWidget(self._build_input_section(), stretch=1)
        top_row.addWidget(self._build_processing_options(), stretch=2)
        content_layout.addLayout(top_row)

        # Row 2: Preview + Progress (balanced)
        mid_row = QHBoxLayout()
        mid_row.setSpacing(16)
        mid_row.addWidget(self._build_preview_section(), stretch=1)
        mid_row.addWidget(self._build_progress_section(), stretch=1)
        content_layout.addLayout(mid_row, stretch=1)

        # Row 3: Outputs - horizontal layout
        content_layout.addWidget(self._build_output_section())

        # Row 4: Activity log - compact
        content_layout.addWidget(self._build_activity_log())

        # Row 5: Action buttons - centered
        content_layout.addLayout(self._build_action_buttons())

        main_layout.addWidget(content, stretch=1)

    def _build_device_info_box(self):
        box = QGroupBox("🔒 Device")
        box.setObjectName("deviceBox")
        layout = QFormLayout(box)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 16, 12, 12)

        fp_short = get_device_fingerprint_short()
        fp_data = generate_device_fingerprint()
        machine = fp_data["components"].get("machine_name", "Unknown")

        # Device ID with monospace font
        device_id = QLabel(fp_short)
        device_id.setStyleSheet(
            "color: #60a5fa; font-size: 12px; font-weight: 600; font-family: 'JetBrains Mono', monospace;"
        )
        device_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow("ID:", device_id)

        # Machine name
        machine_lbl = QLabel(machine[:20] + "..." if len(machine) > 20 else machine)
        machine_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addRow("Host:", machine_lbl)

        # Status badge
        status_lbl = QLabel("✓ Secured")
        status_lbl.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: 600;")
        layout.addRow("Status:", status_lbl)

        return box

    def _build_system_panel(self):
        box = QGroupBox("⚙️ System")
        box.setObjectName("systemBox")
        layout = QFormLayout(box)
        layout.setSpacing(5)
        layout.setContentsMargins(12, 16, 12, 12)

        # RAM display with color coding
        ram_container = QWidget()
        ram_layout = QHBoxLayout(ram_container)
        ram_layout.setContentsMargins(0, 0, 0, 0)
        ram_layout.setSpacing(4)

        self.sys_available_label = QLabel("--")
        self.sys_available_label.setStyleSheet("font-size: 12px; font-weight: 600;")

        ram_layout.addWidget(self.sys_available_label)
        ram_layout.addWidget(QLabel("/"))
        self.sys_total_label = QLabel("--")
        self.sys_total_label.setStyleSheet("color: #64748b; font-size: 11px;")
        ram_layout.addWidget(self.sys_total_label)
        ram_layout.addStretch()

        layout.addRow("RAM:", ram_container)

        # CPU & Platform in one row
        cpu_platform = QWidget()
        cpu_plat_layout = QHBoxLayout(cpu_platform)
        cpu_plat_layout.setContentsMargins(0, 0, 0, 0)
        cpu_plat_layout.setSpacing(8)

        self.sys_cpu_label = QLabel("--")
        self.sys_cpu_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        cpu_plat_layout.addWidget(QLabel("CPU:"))
        cpu_plat_layout.addWidget(self.sys_cpu_label)
        cpu_plat_layout.addStretch()

        self.sys_platform_label = QLabel("--")
        self.sys_platform_label.setStyleSheet("color: #64748b; font-size: 10px;")
        cpu_plat_layout.addWidget(self.sys_platform_label)

        layout.addRow(cpu_platform)

        # Mode badge
        self.sys_mode_label = QLabel("Local")
        self.sys_mode_label.setStyleSheet(
            "color: #22c55e; font-size: 11px; font-weight: 600;"
        )
        layout.addRow("Mode:", self.sys_mode_label)

        return box

    def _build_input_section(self):
        box = QGroupBox("📷 Source")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 16, 12, 12)

        # File path with browse button - compact
        file_row = QHBoxLayout()
        file_row.setSpacing(8)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Select image file...")

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.setProperty("secondary", "true")
        browse_btn.clicked.connect(self.pick_file)

        file_row.addWidget(self.path_edit)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        return box

    def _build_preview_section(self):
        box = QGroupBox("🖼️ Preview")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 16, 12, 12)

        self.preview_label = QLabel("No image selected")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(180)
        self.preview_label.setStyleSheet(
            "border: 2px dashed #334155; border-radius: 8px; color: #64748b; font-size: 12px;"
        )

        layout.addWidget(self.preview_label)
        return box

    def _build_progress_section(self):
        box = QGroupBox("📊 Progress")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 16, 12, 12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.progress_msg = QLabel("Idle")
        self.progress_msg.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.progress_msg.setWordWrap(True)
        layout.addWidget(self.progress_msg)

        # Time info row
        time_row = QHBoxLayout()
        self.elapsed_label = QLabel("Elapsed: --:--")
        self.elapsed_label.setStyleSheet(
            "color: #64748b; font-size: 11px; font-family: 'JetBrains Mono', monospace;"
        )
        self.eta_label = QLabel("ETA: --:--")
        self.eta_label.setStyleSheet(
            "color: #64748b; font-size: 11px; font-family: 'JetBrains Mono', monospace;"
        )
        time_row.addWidget(self.elapsed_label)
        time_row.addStretch()
        time_row.addWidget(self.eta_label)
        layout.addLayout(time_row)

        # Status message
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #60a5fa; font-size: 12px; font-weight: 600;"
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        return box

    def _build_output_section(self):
        box = QGroupBox("📦 Outputs")
        layout = QHBoxLayout(box)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 16, 12, 12)

        self.output_labels = {}
        self.output_btns = {}

        for key in ["obj", "stl", "glb"]:
            # Container for each format
            fmt_container = QWidget()
            fmt_container.setStyleSheet(
                "background-color: #0f172a; border-radius: 6px;"
            )
            fmt_layout = QVBoxLayout(fmt_container)
            fmt_layout.setSpacing(6)
            fmt_layout.setContentsMargins(10, 10, 10, 10)

            # Format header
            header = QLabel(key.upper())
            header.setStyleSheet("color: #60a5fa; font-size: 12px; font-weight: 700;")
            fmt_layout.addWidget(header)

            # Path label
            path_label = QLabel("—")
            path_label.setStyleSheet(
                "color: #64748b; font-size: 10px; font-family: 'JetBrains Mono', monospace;"
            )
            fmt_layout.addWidget(path_label)

            # Buttons row
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)

            open_btn = QPushButton("Open")
            open_btn.setFixedSize(55, 24)
            open_btn.setProperty("secondary", "true")
            open_btn.setStyleSheet(
                "QPushButton { font-size: 10px; padding: 2px 6px; min-width: 0; }"
            )
            open_btn.clicked.connect(lambda _, k=key: self.open_output(k))

            dl_btn = QPushButton("Save")
            dl_btn.setFixedSize(55, 24)
            dl_btn.setStyleSheet(
                "QPushButton { font-size: 10px; padding: 2px 6px; min-width: 0; }"
            )
            dl_btn.clicked.connect(lambda _, k=key: self._save_output_as(k))

            btn_row.addWidget(open_btn)
            btn_row.addWidget(dl_btn)
            btn_row.addStretch()
            fmt_layout.addLayout(btn_row)

            layout.addWidget(fmt_container)
            self.output_labels[key] = path_label
            self.output_btns[key] = (open_btn, dl_btn)

        return box

    def _build_activity_log(self):
        box = QGroupBox("📋 Log")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 16, 12, 12)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(80)
        self.log_text.setMaximumHeight(120)

        layout.addWidget(self.log_text)
        return box

    def _build_processing_options(self):
        box = QGroupBox("⚙️ Processing")
        main_layout = QVBoxLayout(box)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 16, 12, 12)

        # Top row: Method + Quality
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # Method selection
        method_container = QWidget()
        method_layout = QHBoxLayout(method_container)
        method_layout.setContentsMargins(0, 0, 0, 0)
        method_layout.setSpacing(8)
        method_layout.addWidget(QLabel("Method:"))

        self.local_radio = QRadioButton("Local")
        self.api_radio = QRadioButton("Cloud API")
        self.local_radio.setChecked(True)
        self.local_radio.toggled.connect(self._on_method_changed)
        self.api_radio.toggled.connect(self._on_method_changed)

        method_layout.addWidget(self.local_radio)
        method_layout.addWidget(self.api_radio)
        method_layout.addStretch()
        top_row.addWidget(method_container)

        # Quality preset
        qual_container = QWidget()
        qual_layout = QHBoxLayout(qual_container)
        qual_layout.setContentsMargins(0, 0, 0, 0)
        qual_layout.setSpacing(8)
        qual_layout.addWidget(QLabel("Quality:"))

        self.quality_combo = QComboBox()
        self.quality_combo.setFixedWidth(140)
        for key, label in [
            ("draft", "Draft"),
            ("standard", "Standard"),
            ("high", "High"),
            ("production", "Production"),
        ]:
            self.quality_combo.addItem(label, key)
        self.quality_combo.setCurrentIndex(3)
        qual_layout.addWidget(self.quality_combo)
        top_row.addWidget(qual_container)
        top_row.addStretch()

        main_layout.addLayout(top_row)

        # API options (compact form layout)
        self.api_group = QGroupBox("API Configuration")
        self.api_group.setVisible(False)
        self.api_group.setStyleSheet(
            "QGroupBox { margin-top: 6px; padding-top: 10px; font-size: 11px; }"
        )
        api_layout = QGridLayout(self.api_group)
        api_layout.setSpacing(8)
        api_layout.setContentsMargins(10, 12, 10, 10)

        # Row 0: Token + Save button
        self.api_token_edit = QLineEdit()
        self.api_token_edit.setPlaceholderText(
            "Enter API token (Tripo3D) or AccessKey:SecretKey..."
        )
        self.api_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_token_edit.textChanged.connect(self._update_run_enabled)
        self.api_token_edit.textChanged.connect(self._on_token_changed)

        save_token_btn = QPushButton("Save")
        save_token_btn.setFixedWidth(70)
        save_token_btn.setProperty("secondary", "true")
        save_token_btn.clicked.connect(self._save_server_token)

        api_layout.addWidget(QLabel("Token:"), 0, 0)
        api_layout.addWidget(self.api_token_edit, 0, 1)
        api_layout.addWidget(save_token_btn, 0, 2)

        # Row 1: Model + Resolution + Format
        self.api_model_combo = QComboBox()
        self.api_model_combo.setFixedWidth(140)
        model_info = get_available_models()
        hitem3d_models = model_info.get("hitem3d", {}).get("models", {})
        for model_key, model_data in hitem3d_models.items():
            self.api_model_combo.addItem(model_data["name"], model_key)
        self.api_model_combo.currentIndexChanged.connect(self._on_model_changed)

        self.api_resolution_combo = QComboBox()
        self.api_resolution_combo.setFixedWidth(90)
        self._update_resolution_options_for_platform()

        self.api_format_combo = QComboBox()
        self.api_format_combo.setFixedWidth(70)
        for key, label in [
            ("obj", "OBJ"),
            ("glb", "GLB"),
            ("stl", "STL"),
            ("fbx", "FBX"),
            ("usdz", "USDZ"),
        ]:
            self.api_format_combo.addItem(label, key)
        self.api_format_combo.setCurrentIndex(1)

        api_layout.addWidget(QLabel("Model:"), 1, 0)
        api_layout.addWidget(self.api_model_combo, 1, 1)
        api_layout.addWidget(self.api_resolution_combo, 1, 2)

        # Row 2: Balance display
        self.balance_label = QLabel("Enter token to check balance")
        self.balance_label.setStyleSheet("color: #64748b; font-size: 11px;")
        api_layout.addWidget(QLabel("Balance:"), 2, 0)
        api_layout.addWidget(self.balance_label, 2, 1, 1, 2)

        main_layout.addWidget(self.api_group)
        return box

    def _build_action_buttons(self):
        row = QHBoxLayout()
        row.setSpacing(12)

        self.run_btn = QPushButton("🚀 Generate 3D Model")
        self.run_btn.setProperty("success", "true")
        self.run_btn.setMinimumWidth(180)
        self.run_btn.setMinimumHeight(40)
        self.run_btn.clicked.connect(self.start_pipeline)

        reset_btn = QPushButton("🔄 Reset")
        reset_btn.setProperty("secondary", "true")
        reset_btn.setFixedWidth(100)
        reset_btn.clicked.connect(self.reset_ui)

        open_out_btn = QPushButton("📂 Open Folder")
        open_out_btn.setProperty("secondary", "true")
        open_out_btn.setFixedWidth(120)
        open_out_btn.clicked.connect(self.open_output_folder)

        row.addStretch()
        row.addWidget(reset_btn)
        row.addWidget(open_out_btn)
        row.addWidget(self.run_btn)
        row.addStretch()

        return row

    # ═══════════════════════════════════════════════════════════════
    #  ACTIONS
    # ═══════════════════════════════════════════════════════════════

    def pick_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not file:
            return
        self.selected_path = file
        self.path_edit.setText(file)
        self._load_preview(file)
        self._log(f"📷 Selected: {os.path.basename(file)}")
        self._update_run_enabled()

    def start_pipeline(self):
        if not self.selected_path:
            QMessageBox.information(
                self, "Select an image", "Please choose an image first."
            )
            return

        options = self._get_processing_options()

        # RAM check for local
        if not options["use_api"]:
            try:
                available_gb = psutil.virtual_memory().available / (1024**3)
                if available_gb < 4.0:
                    QMessageBox.warning(
                        self,
                        "Low RAM",
                        f"Only {available_gb:.1f}GB available. Local processing requires "
                        f"at least 4GB. Close other apps or use Cloud API.",
                    )
                    return
            except Exception:
                pass

        self._set_running(True)
        self._start_time = time.time()
        method_text = "Cloud API" if options["use_api"] else "Local Processing"
        self.status_label.setText(f"Running ({method_text})…")
        self.progress_bar.setValue(0)
        self.progress_msg.setText(f"Starting {method_text}...")
        self._log(f"🚀 Starting pipeline with {method_text}…")

        if options["use_api"]:
            self._log(
                f"   Model: {options['api_model']}, Res: {options['api_resolution']}"
            )

        # Start elapsed timer
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._update_elapsed)
        self.elapsed_timer.start(1000)

        self.worker = PipelineWorker(
            self.selected_path,
            use_api=options["use_api"],
            api_token=options["api_token"],
            api_model=options["api_model"],
            api_resolution=options["api_resolution"],
            api_format=options["api_format"],
            quality=options["quality"],
            parent=self,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_msg.setText(msg)

        # Update ETA
        if self._start_time and pct > 0:
            elapsed = time.time() - self._start_time
            if pct < 100:
                eta = (elapsed / pct) * (100 - pct)
                m, s = divmod(int(eta), 60)
                self.eta_label.setText(f"ETA: {m:02d}:{s:02d}")

    def _update_elapsed(self):
        if self._start_time:
            elapsed = time.time() - self._start_time
            m, s = divmod(int(elapsed), 60)
            self.elapsed_label.setText(f"Elapsed: {m:02d}:{s:02d}")

    def _on_finished(self, outputs: dict):
        if hasattr(self, "elapsed_timer"):
            self.elapsed_timer.stop()

        # Check for error in result dict
        if outputs.get("error"):
            self._on_failed(outputs["error"])
            return

        if outputs.get("warning"):
            self._log(f"⚠️ Warning: {outputs['warning']}")

        self.outputs = outputs
        for key, lbl in self.output_labels.items():
            path = outputs.get(key, "")
            if path:
                lbl.setText(os.path.basename(path))
                lbl.setStyleSheet(
                    "color: #22c55e; font-size: 10px; font-weight: 600; font-family: 'JetBrains Mono', monospace;"
                )
            else:
                lbl.setText("—")
                lbl.setStyleSheet(
                    "color: #64748b; font-size: 10px; font-family: 'JetBrains Mono', monospace;"
                )

        method = outputs.get("processing_method", "local")
        method_text = "Cloud API" if method == "hitem3d_api" else "Local Processing"
        self.status_label.setText(f"✅ Completed ({method_text})")
        self.status_label.setStyleSheet(
            "color: #28a745; font-size: 12px; font-weight: bold;"
        )
        self.progress_bar.setValue(100)
        self.progress_msg.setText("Done! 3D files generated successfully.")
        self.eta_label.setText("ETA: 00:00")

        stats = outputs.get("stats") or {}
        total = stats.get("total_seconds")
        stages = stats.get("stages") or {}
        if total:
            self._log(f"✅ Done! Total time: {total:.1f}s")
        if stages:
            for name, secs in stages.items():
                self._log(f"   {name}: {secs:.1f}s")

        files = {k: outputs.get(k) for k in ("obj", "stl", "glb") if outputs.get(k)}
        self._log(f"📦 Files: {', '.join(os.path.basename(v) for v in files.values())}")

        system_info = outputs.get("system_info") or {}
        if system_info:
            self._log(
                f"💻 RAM: {system_info.get('ram_available_gb', '?')}GB free / "
                f"{system_info.get('ram_total_gb', '?')}GB total"
            )

        self._set_running(False)

    def _on_failed(self, message: str):
        if hasattr(self, "elapsed_timer"):
            self.elapsed_timer.stop()

        self.status_label.setText("❌ Failed")
        self.status_label.setStyleSheet(
            "color: #e74c3c; font-size: 12px; font-weight: bold;"
        )
        self.progress_bar.setValue(0)
        self.progress_msg.setText("Processing failed.")
        self._log(f"❌ Error: {message}")
        QMessageBox.critical(self, "Processing Error", message)
        self._set_running(False)

    def reset_ui(self):
        self.selected_path = None
        self.outputs = {}
        self.path_edit.clear()
        self.preview_label.setText("No image selected")
        self.preview_label.setPixmap(QPixmap())
        self._preview_pix = QPixmap()
        for lbl in self.output_labels.values():
            lbl.setText("—")
            lbl.setStyleSheet(
                "color: #64748b; font-size: 10px; font-family: 'JetBrains Mono', monospace;"
            )
        self.status_label.setText("")
        self.progress_bar.setValue(0)
        self.progress_msg.setText("Idle")
        self.elapsed_label.setText("Elapsed: --:--")
        self.eta_label.setText("ETA: --:--")
        self.log_text.clear()
        self._log("🔄 Reset.")
        self._update_run_enabled()

    def open_output(self, key: str):
        path = self.outputs.get(key)
        if not path or not os.path.exists(path):
            QMessageBox.information(
                self, "Not available", f"No {key.upper()} file yet."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    def _save_output_as(self, key: str):
        path = self.outputs.get(key)
        if not path or not os.path.exists(path):
            QMessageBox.information(
                self, "Not available", f"No {key.upper()} file yet."
            )
            return
        ext = key.upper()
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {ext} File",
            os.path.basename(path),
            f"{ext} files (*.{key});;All Files (*)",
        )
        if save_path:
            shutil.copy2(path, save_path)
            self._log(f"💾 Saved {ext} to: {save_path}")

    def open_output_folder(self):
        out_dir = os.path.abspath("output")
        os.makedirs(out_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(out_dir))

    # ═══════════════════════════════════════════════════════════════
    #  HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _set_running(self, running: bool):
        self.run_btn.setEnabled(not running and bool(self.selected_path))
        self.path_edit.setEnabled(not running)

    def _update_run_enabled(self):
        has_image = bool(self.selected_path)
        if not has_image:
            self.run_btn.setEnabled(False)
            return
        if self.api_radio.isChecked():
            token = self.api_token_edit.text().strip()
            credentials = resolve_hitem3d_credentials(token)
            has_credentials = bool(
                credentials["access_token"]
                or (credentials["client_id"] and credentials["client_secret"])
            )
            self.run_btn.setEnabled(bool(token and len(token) >= 10) or has_credentials)
        else:
            self.run_btn.setEnabled(True)

    def _log(self, text: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{timestamp}] {text}")

    def _load_preview(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            self.preview_label.setText("Preview not available")
            return
        self._preview_pix = pix
        self._update_preview_pixmap()

    def _update_preview_pixmap(self):
        if self._preview_pix.isNull():
            return
        size = self.preview_label.size()
        if size.width() < 10 or size.height() < 10:
            return
        self.preview_label.setPixmap(
            self._preview_pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._preview_pix and not self._preview_pix.isNull():
            self._update_preview_pixmap()

    def _on_method_changed(self):
        use_api = self.api_radio.isChecked()
        self.api_group.setVisible(use_api)
        self.sys_mode_label.setText("Cloud API" if use_api else "Local")
        self.sys_mode_label.setStyleSheet(
            "color: #3b82f6; font-size: 11px; font-weight: 600;"
            if use_api
            else "color: #22c55e; font-size: 11px; font-weight: 600;"
        )
        self._update_run_enabled()
        if use_api:
            self._schedule_balance_fetch()

    def _update_model_description(self):
        # Model description removed for compact UI
        pass

    def _refresh_system_info(self):
        try:
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024**3)
            total_gb = mem.total / (1024**3)

            # Color-coded RAM display
            if available_gb >= 8:
                color = "#28a745"  # green
            elif available_gb >= 4:
                color = "#ffa500"  # amber
            else:
                color = "#e74c3c"  # red

            self.sys_available_label.setText(f"{available_gb:.2f} GB")
            self.sys_available_label.setStyleSheet(
                f"color: {color}; font-size: 11px; font-weight: bold;"
            )
            self.sys_total_label.setText(f"{total_gb:.2f} GB")
            self.sys_cpu_label.setText(str(os.cpu_count() or "--"))
            self.sys_platform_label.setText(f"{platform.system()} {platform.release()}")
        except Exception:
            self.sys_available_label.setText("--")

    def _get_processing_options(self):
        token = self.api_token_edit.text().strip()
        return {
            "use_api": self.api_radio.isChecked(),
            "api_token": token or None,
            "api_model": self.api_model_combo.currentData(),
            "api_resolution": self.api_resolution_combo.currentData(),
            "api_format": self.api_format_combo.currentData(),
            "quality": self.quality_combo.currentData() or "standard",
        }

    def _logout(self):
        self.hide()
        dlg = DeviceLoginDialog(self)
        if dlg.exec():
            self.reset_ui()
            self.show()
        else:
            QApplication.instance().quit()

    # ── Balance ──
    def _schedule_balance_fetch(self):
        if not self.api_radio.isChecked():
            return
        self.balance_error = None
        self.balance_timer.start(600)

    def _fetch_balance(self):
        if not self.api_radio.isChecked():
            return
        token = self.api_token_edit.text().strip()
        credentials = resolve_hitem3d_credentials(token)
        has_creds = bool(
            credentials["access_token"]
            or (credentials["client_id"] and credentials["client_secret"])
        )
        if not has_creds:
            self.balance_available = None
            self.balance_error = "Add a valid API token to check balance."
            self.balance_label.setText(self.balance_error)
            return

        # Detect platform and use appropriate balance checker
        platform_type = self._detect_platform_from_token(token)

        try:
            if platform_type == "tripo3d":
                # Use unified API for Tripo3D balance
                from core.unified_api import Unified3DAPI, APICredentials

                creds = APICredentials.from_string(token)
                api = Unified3DAPI(credentials=creds)

                async def get_tripo_balance():
                    balance = await api.get_balance()
                    await api.close()
                    return balance

                balance = asyncio.run(get_tripo_balance())

                self.balance_available = balance
                self.balance_error = None
                if balance is not None:
                    self.balance_label.setText(f"Balance: {balance:.0f} credits")
                else:
                    self.balance_label.setText("Balance unavailable")
            else:
                # Use Hitem3D balance check
                result = asyncio.run(get_hitem3d_balance(token or None))
                self.balance_available = result.get("available")
                self.balance_error = None
                available = self.balance_available
                self.balance_label.setText(
                    f"Balance: {available} credits"
                    if available
                    else "Balance unavailable"
                )
        except Exception as exc:
            self.balance_error = f"Balance check failed: {exc}"
            self.balance_label.setText(self.balance_error)

    def _save_server_token(self):
        token = self.api_token_edit.text().strip()
        if not token:
            QMessageBox.information(self, "Token", "Please enter the API token first.")
            return
        try:
            # Use unified save function that handles both Tripo3D and Hitem3D
            from core.unified_pipeline import save_api_credentials

            result = save_api_credentials(token)

            platform_name = (
                "Tripo3D" if result["platform"] == "tripo3d" else "Cloud API"
            )
            QMessageBox.information(
                self, "Token Saved", f"{platform_name} API token saved successfully!"
            )
            self._schedule_balance_fetch()
        except Exception as exc:
            QMessageBox.critical(self, "Token", f"Failed to save: {exc}")

    # ── Platform Detection & Dynamic UI ──
    def _load_saved_credentials(self):
        """Load saved API credentials from storage and populate the UI."""
        try:
            from core.unified_pipeline import load_saved_api_credentials

            saved = load_saved_api_credentials()

            if saved and saved.get("token"):
                token = saved["token"]
                platform = saved.get("platform", "unknown")

                # Set the token in the UI (it will be masked)
                self.api_token_edit.setText(token)

                # Update platform-specific UI
                self._update_platform_ui(token)

                # Log the loaded credentials
                platform_display = "Tripo3D" if platform == "tripo3d" else "Cloud API"
                print(f"[UI] Loaded saved {platform_display} credentials")
                self._log(f"Loaded saved {platform_display} credentials")

                # Schedule balance check
                self._schedule_balance_fetch()
        except Exception as e:
            print(f"[UI] Failed to load saved credentials: {e}")

    def _on_token_changed(self):
        """Handle API token text changes - update platform UI and schedule balance check."""
        token = self.api_token_edit.text().strip()

        # Update platform-specific UI (models, resolutions, etc.)
        if token:
            self._update_platform_ui(token)

        # Schedule balance fetch
        self._schedule_balance_fetch()

    def _detect_platform_from_token(self, token: str) -> str:
        """
        Detect platform type from API token.
        Returns: 'tripo3d', 'hitem3d', or 'unknown'
        """
        if not token:
            return "unknown"

        # Tripo3D keys start with 'tsk_' and don't contain colons
        if token.startswith("tsk_") and ":" not in token:
            return "tripo3d"

        # Hitem3D uses client_id:secret format
        if ":" in token:
            return "hitem3d"

        # Default assumption for long keys without colons (Tripo3D)
        if len(token) > 30 and ":" not in token:
            return "tripo3d"

        return "hitem3d"

    def _update_platform_ui(self, token: str):
        """
        Update UI elements based on detected platform.
        This changes model dropdown, available features, etc.
        """
        platform_type = self._detect_platform_from_token(token)

        # Update model combo box based on platform
        self.api_model_combo.clear()

        if platform_type == "tripo3d":
            # Tripo3D models
            models = {
                "v2_5": "v2.5 (Latest - Balanced)",
                "v2_0": "v2.0 (PBR Quality)",
                "v1_4": "v1.4 (Fast)",
            }
            for model_id, model_name in models.items():
                self.api_model_combo.addItem(model_name, model_id)
        else:
            # Hitem3D models (default fallback)
            models = {
                "hitem3dv1.5": "Standard v1.5",
                "hitem3dv2.0": "Standard v2.0",
                "scene-portraitv1.5": "Portrait v1.5",
                "scene-portraitv2.0": "Portrait v2.0",
                "scene-portraitv2.1": "Portrait v2.1",
            }
            for model_id, model_name in models.items():
                self.api_model_combo.addItem(model_name, model_id)

        # Update resolution options based on first model
        self._update_resolution_options_for_platform(platform_type)

        # Log platform detection
        platform_display = "Tripo3D" if platform_type == "tripo3d" else "Cloud API"
        print(f"[UI] Detected platform: {platform_display}")
        self._log(f"Detected {platform_display} API")

    def _update_resolution_options_for_platform(self, platform_type: str = None):
        """Update resolution dropdown based on platform and selected model."""
        if platform_type is None:
            token = self.api_token_edit.text().strip()
            platform_type = self._detect_platform_from_token(token)

        model_key = self.api_model_combo.currentData()
        if not model_key:
            return

        self.api_resolution_combo.clear()

        if platform_type == "tripo3d":
            # Tripo3D resolutions
            resolutions_map = {
                "v2_5": ["512", "1024", "2048"],
                "v2_0": ["1024", "2048"],
                "v1_4": ["512", "1024"],
            }
            resolutions = resolutions_map.get(model_key, ["1024"])
        else:
            # Hitem3D resolutions
            resolutions_map = {
                "hitem3dv1.5": ["512", "1024", "1536", "1536pro"],
                "hitem3dv2.0": ["1536", "1536pro"],
                "scene-portraitv1.5": ["1536"],
                "scene-portraitv2.0": ["1536pro"],
                "scene-portraitv2.1": ["1536pro"],
            }
            resolutions = resolutions_map.get(model_key, ["1024"])

        for res in resolutions:
            display = f"{res}³" if res != "1536pro" else "1536³ Pro"
            self.api_resolution_combo.addItem(display, res)

    def _on_model_changed(self):
        """Handle model selection change."""
        token = self.api_token_edit.text().strip()
        platform_type = self._detect_platform_from_token(token)
        self._update_resolution_options_for_platform(platform_type)
        self._update_model_description()

    # ── Updates ──
    def _check_for_updates(self):
        if not UPDATE_URL:
            return
        self.update_worker = UpdateCheckWorker(UPDATE_URL, APP_VERSION, parent=self)
        self.update_worker.finished.connect(self._on_update_check)
        self.update_worker.failed.connect(
            lambda m: self._log(f"Update check failed: {m}")
        )
        self.update_worker.start()

    def _on_update_check(self, info: dict):
        if not info.get("update_available"):
            return
        latest = info.get("version", "")
        notes = info.get("notes", "")
        message = f"A new version ({latest}) is available."
        if notes:
            message = f"{message}\n\n{notes}"
        reply = QMessageBox.question(
            self,
            "Update available",
            message + "\n\nDownload and restart now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_update(info.get("url"))

    def _download_update(self, url):
        if not url:
            return
        if not _is_frozen():
            QMessageBox.information(
                self, "Update", "Update is available for the packaged .exe build only."
            )
            return
        self.download_worker = UpdateDownloadWorker(url, parent=self)
        self.download_worker.finished.connect(self._on_update_downloaded)
        self.download_worker.failed.connect(
            lambda m: QMessageBox.warning(self, "Update failed", m)
        )
        self.download_worker.start()

    def _on_update_downloaded(self, new_exe):
        _launch_update_script(sys.executable, new_exe)
        QApplication.instance().quit()


# ═══════════════════════════════════════════════════════════════════
#  STARTUP FLOW
# ═══════════════════════════════════════════════════════════════════


def run_app():
    """
    Full app startup flow:
    1. License check (if license module available)
       - If valid license exists: skip to password login
       - If license expired: show license dialog to renew
       - If no license: show license dialog for trial/purchase
    2. Device fingerprint login
    3. Show main app
    """
    app = QApplication.instance() or QApplication(sys.argv)

    # Load professional dark theme
    style_file = os.path.join(os.path.dirname(__file__), "styles.qss")
    if os.path.exists(style_file):
        with open(style_file, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    # Step 1: License check (optional)
    if HAS_LICENSE:
        license_manager = get_license_manager()
        has_valid = license_manager.has_valid_license()
        has_trial = license_manager.has_trial_available()

        if has_valid:
            # Valid license exists - check if expiring soon and warn user
            license_info = license_manager.get_license_info()
            if license_info:
                days_remaining = license_info.get("days_remaining", 0)
                if days_remaining <= 7 and days_remaining > 0:
                    # Warn user that license is expiring soon
                    QMessageBox.warning(
                        None,
                        "License Expiring Soon",
                        f"Your license will expire in {days_remaining} days.\n\n"
                        f"Please renew your license to continue using ImageTo3D Pro without interruption.",
                    )
                elif days_remaining <= 0:
                    # License expired - show license dialog
                    if not require_license_dialog():
                        return 1
            # Valid license - skip to password login
            print("[Startup] Valid license found, skipping license dialog")
        elif has_trial:
            # Has trial available - show license dialog to let them start trial
            if not require_license_dialog():
                return 1
        else:
            # No valid license and no trial - show license dialog
            if not require_license_dialog():
                return 1

    # Step 2: Device fingerprint login
    login = DeviceLoginDialog()
    if not login.exec():
        return 0

    # Step 3: Show main app
    w = App()
    w.show()
    return app.exec()


def main():
    exit_code = run_app()
    sys.exit(exit_code if exit_code is not None else 0)


if __name__ == "__main__":
    main()
