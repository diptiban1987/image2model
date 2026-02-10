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
import platform
import psutil
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
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QDesktopServices

# Ensure project root is on sys.path when running this file directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.unified_pipeline import run_pipeline, get_available_models, validate_api_token, resolve_hitem3d_credentials, save_hitem3d_credentials
from core.auth import is_password_configured, verify_password, set_password

APP_VERSION = "1.0.0"
UPDATE_URL = os.getenv("IMAGETO3D_UPDATE_URL", "").strip()


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
    script = "\n".join([
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
    ])
    fd, path = tempfile.mkstemp(suffix=".cmd")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(script)
    subprocess.Popen(["cmd", "/c", path], close_fds=True)


class LoginDialog(QDialog):
    """Password dialog before opening the app. Validation is server-side (core.auth)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image → 3D Pro — Login")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter application password:"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.returnPressed.connect(self.accept_login)
        layout.addWidget(self.password_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept_login)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self._ok = btns.button(QDialogButtonBox.StandardButton.Ok)

    def accept_login(self):
        pwd = self.password_edit.text()
        if not pwd:
            QMessageBox.warning(self, "Login", "Please enter the password.")
            return
        if verify_password(pwd):
            self.accept()
        else:
            QMessageBox.warning(self, "Login", "Incorrect password.")
            self.password_edit.clear()
            self.password_edit.setFocus()

    def get_password(self):
        return self.password_edit.text()


class SetPasswordDialog(QDialog):
    """First-time setup: set the application password (stored as bcrypt hash server-side)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image → 3D Pro — Set Password")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Set an application password. It will be stored securely (hashed) on this machine."))
        layout.addWidget(QLabel("Password:"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("New password")
        layout.addWidget(self.password_edit)
        layout.addWidget(QLabel("Confirm:"))
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("Confirm password")
        layout.addWidget(self.confirm_edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_ok(self):
        pwd = self.password_edit.text()
        conf = self.confirm_edit.text()
        if not pwd:
            QMessageBox.warning(self, "Set Password", "Please enter a password.")
            return
        if pwd != conf:
            QMessageBox.warning(self, "Set Password", "Password and confirmation do not match.")
            return
        if len(pwd) < 8:
            QMessageBox.warning(self, "Set Password", "Use at least 8 characters.")
            return
        try:
            set_password(pwd)
            QMessageBox.information(self, "Set Password", "Password set. You will need it to open the application.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save password: {e}")


def require_login_then_show_app():
    """Show login or set-password dialog; on success show main app and run event loop."""
    app = QApplication.instance() or QApplication(sys.argv)
    if not is_password_configured():
        dlg = SetPasswordDialog()
        if not dlg.exec():
            return 1
    dlg = LoginDialog()
    if not dlg.exec():
        return 0
    w = App()
    w.show()
    return app.exec()


class PipelineWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)
    progress = Signal(int)

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
            self.progress.emit(5)
            result = run_pipeline(
                self.image_path,
                use_api=self.use_api,
                api_token=self.api_token,
                api_model=self.api_model,
                api_resolution=self.api_resolution,
                api_format=self.api_format,
                quality=self.quality,
            )
            self.progress.emit(100)
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - surfaced in UI
            self.failed.emit(str(exc))


class UpdateCheckWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, current_version: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.current_version = current_version

    def run(self):
        try:
            info = _fetch_update_info(self.url)
            latest = str(info.get("version") or "").strip()
            download_url = str(info.get("url") or "").strip()
            notes = str(info.get("notes") or "").strip()
            result = {
                "update_available": bool(latest and download_url and _is_newer_version(self.current_version, latest)),
                "version": latest,
                "url": download_url,
                "notes": notes,
            }
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            temp_dir = tempfile.mkdtemp(prefix="imagetoad_update_")
            filename = _safe_filename_from_url(self.url)
            target = os.path.join(temp_dir, filename)
            req = urllib.request.Request(self.url, headers={"User-Agent": "ImageTo3DPro"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(target, "wb") as handle:
                    shutil.copyfileobj(resp, handle)
            self.finished.emit(target)
        except Exception as exc:
            self.failed.emit(str(exc))


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image → 3D Pro")
        self.setMinimumSize(720, 560)

        self.worker: PipelineWorker | None = None
        self.update_worker: UpdateCheckWorker | None = None
        self.download_worker: UpdateDownloadWorker | None = None
        self.selected_path: str | None = None
        self.outputs = {}
        self._preview_pix = QPixmap()

        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        main.addWidget(self._build_input_group())
        main.addWidget(self._build_processing_options())
        main.addWidget(self._build_preview_group())
        main.addWidget(self._build_system_group())
        main.addWidget(self._build_status_bar())
        main.addWidget(self._build_output_group())
        main.addWidget(self._build_logs())
        main.addLayout(self._build_actions())

        self._update_model_description()
        self._update_run_enabled()
        self._refresh_system_info()
        self.system_timer = QTimer(self)
        self.system_timer.timeout.connect(self._refresh_system_info)
        self.system_timer.start(3000)
        QTimer.singleShot(800, self._check_for_updates)

    # ---- UI builders -------------------------------------------------
    def _build_input_group(self):
        box = QGroupBox("Source image")
        layout = QGridLayout(box)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.pick_file)

        layout.addWidget(QLabel("Path"), 0, 0)
        layout.addWidget(self.path_edit, 0, 1)
        layout.addWidget(browse, 0, 2)

        return box

    def _build_preview_group(self):
        box = QGroupBox("Preview")
        layout = QVBoxLayout(box)

        self.preview = QLabel("No image selected")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setStyleSheet("border: 1px solid #ccc;")
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.preview)
        return box

    def _build_system_group(self):
        box = QGroupBox("System & Requirements")
        layout = QGridLayout(box)

        self.sys_available_value = QLabel("--")
        self.sys_total_value = QLabel("--")
        self.sys_required_value = QLabel("--")
        self.sys_cpu_value = QLabel("--")
        self.sys_platform_value = QLabel("--")
        self.sys_mode_value = QLabel("Local")
        self.requirements_label = QLabel("")
        self.requirements_label.setWordWrap(True)

        layout.addWidget(QLabel("Available RAM"), 0, 0)
        layout.addWidget(self.sys_available_value, 0, 1)
        layout.addWidget(QLabel("Total RAM"), 1, 0)
        layout.addWidget(self.sys_total_value, 1, 1)
        layout.addWidget(QLabel("Required RAM"), 2, 0)
        layout.addWidget(self.sys_required_value, 2, 1)
        layout.addWidget(QLabel("CPU Cores"), 3, 0)
        layout.addWidget(self.sys_cpu_value, 3, 1)
        layout.addWidget(QLabel("Platform"), 4, 0)
        layout.addWidget(self.sys_platform_value, 4, 1)
        layout.addWidget(QLabel("Mode"), 5, 0)
        layout.addWidget(self.sys_mode_value, 5, 1)
        layout.addWidget(self.requirements_label, 6, 0, 1, 2)

        return box

    def _build_status_bar(self):
        box = QGroupBox("Status")
        layout = QVBoxLayout(box)

        self.status_label = QLabel("Idle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        return box

    def _build_output_group(self):
        box = QGroupBox("Outputs")
        layout = QGridLayout(box)

        self.output_labels = {}
        for row, key in enumerate(["obj", "stl", "glb", "fbx", "usdz"]):
            label = QLabel(f"{key.upper()}:")
            path_label = QLabel("—")
            path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            open_btn = QPushButton("Open")
            open_btn.clicked.connect(lambda _, k=key: self.open_output(k))

            layout.addWidget(label, row, 0)
            layout.addWidget(path_label, row, 1)
            layout.addWidget(open_btn, row, 2)
            self.output_labels[key] = path_label

        return box

    def _build_logs(self):
        box = QGroupBox("Logs")
        layout = QVBoxLayout(box)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(120)
        layout.addWidget(self.logs)
        return box

    def _build_processing_options(self):
        box = QGroupBox("Processing Options")
        layout = QVBoxLayout(box)
        
        # Processing method selection
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Method:"))
        
        self.local_radio = QRadioButton("Local Processing")
        self.api_radio = QRadioButton("Hitem3D API")
        self.local_radio.setChecked(True)
        
        self.local_radio.toggled.connect(self._on_method_changed)
        self.api_radio.toggled.connect(self._on_method_changed)

        method_layout.addWidget(self.local_radio)
        method_layout.addWidget(self.api_radio)
        method_layout.addStretch()
        layout.addLayout(method_layout)

        # Local quality preset (visible when local is selected)
        local_options = QHBoxLayout()
        local_options.addWidget(QLabel("Mesh quality:"))
        self.quality_combo = QComboBox()
        for key, label in [
            ("draft", "Draft (fast)"),
            ("standard", "Standard"),
            ("high", "High"),
            ("production", "Production"),
        ]:
            self.quality_combo.addItem(label, key)
        self.quality_combo.setCurrentIndex(1)  # Standard
        local_options.addWidget(self.quality_combo)
        local_options.addStretch()
        layout.addLayout(local_options)

        # API options (hidden by default)
        self.api_group = QGroupBox("API Options")
        self.api_group.setVisible(False)
        api_layout = QFormLayout(self.api_group)
        
        # API Token
        self.api_token_edit = QLineEdit()
        self.api_token_edit.setPlaceholderText("Enter your Hitem3D API token")
        self.api_token_edit.textChanged.connect(self._validate_token)
        self.api_token_edit.textChanged.connect(self._update_run_enabled)
        api_layout.addRow("API Token:", self.api_token_edit)

        save_token_btn = QPushButton("Save Server Token")
        save_token_btn.clicked.connect(self._save_server_token)
        api_layout.addRow("", save_token_btn)
        
        # Model selection
        self.api_model_combo = QComboBox()
        model_info = get_available_models()
        hitem3d_models = model_info.get("hitem3d", {}).get("models", {})
        for model_key, model_data in hitem3d_models.items():
            self.api_model_combo.addItem(model_data["name"], model_key)
        self.api_model_combo.currentIndexChanged.connect(self._on_model_changed)
        api_layout.addRow("Model:", self.api_model_combo)
        
        # Model description (create before _update_resolution_options so _update_model_description can set it)
        self.model_description_label = QLabel()
        self.model_description_label.setWordWrap(True)
        self.model_description_label.setStyleSheet("color: #666; font-size: 11px;")
        
        # Resolution selection
        self.api_resolution_combo = QComboBox()
        self._update_resolution_options()
        api_layout.addRow("Resolution:", self.api_resolution_combo)

        self.api_format_combo = QComboBox()
        for key, label in [
            ("obj", "OBJ"),
            ("glb", "GLB"),
            ("stl", "STL"),
            ("fbx", "FBX"),
            ("usdz", "USDZ"),
        ]:
            self.api_format_combo.addItem(label, key)
        self.api_format_combo.setCurrentIndex(1)
        api_layout.addRow("Output Format:", self.api_format_combo)
        api_layout.addRow(self.model_description_label)
        
        layout.addWidget(self.api_group)
        
        return box

    def _build_actions(self):
        row = QHBoxLayout()
        row.addStretch()

        self.run_btn = QPushButton("Generate 3D Model")
        self.run_btn.clicked.connect(self.start_pipeline)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_ui)

        open_out = QPushButton("Open Output Folder")
        open_out.clicked.connect(self.open_output_folder)

        logout_btn = QPushButton("Log out")
        logout_btn.clicked.connect(self._logout)

        quit_btn = QPushButton("Quit")
        quit_btn.clicked.connect(QApplication.instance().quit)

        row.addWidget(self.run_btn)
        row.addWidget(reset_btn)
        row.addWidget(open_out)
        row.addWidget(logout_btn)
        row.addWidget(quit_btn)

        return row

    # ---- Actions -----------------------------------------------------
    def pick_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"
        )
        if not file:
            return
        self.selected_path = file
        self.path_edit.setText(file)
        self._load_preview(file)
        self._log(f"Selected: {file}")
        self._update_run_enabled()

    def start_pipeline(self):
        if not self.selected_path:
            QMessageBox.information(self, "Select an image", "Please choose an image first.")
            return

        # Get processing options
        options = self._get_processing_options()
        
        # Validate API options if using API
        if options["use_api"]:
            credentials = resolve_hitem3d_credentials(options["api_token"])
            has_credentials = bool(credentials["access_token"] or (credentials["client_id"] and credentials["client_secret"]))
            if not has_credentials:
                QMessageBox.warning(self, "Credentials Required", "Please add Hitem3D credentials or API token.")
                return
            if options["api_token"]:
                is_valid = asyncio.run(validate_api_token(options["api_token"]))
                if not is_valid:
                    QMessageBox.warning(self, "Invalid Credentials", "Please enter valid Hitem3D credentials.")
                    return
        else:
            try:
                available_gb = psutil.virtual_memory().available / (1024 ** 3)
                if available_gb < 6:
                    QMessageBox.warning(
                        self,
                        "Low RAM",
                        "Local processing requires at least 6GB available RAM. "
                        "Please upgrade your PC RAM or use Hitem3D API."
                    )
                    return
            except Exception:
                pass

        self._set_running(True)
        method_text = "Hitem3D API" if options["use_api"] else "Local Processing"
        self.status_label.setText(f"Running ({method_text})…")
        self.progress.setValue(0)
        self._log(f"Starting pipeline with {method_text}…")
        if options["use_api"]:
            self._log(
                f"Model: {options['api_model']}, Resolution: {options['api_resolution']}, Format: {options['api_format']}"
            )

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
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_finished(self, outputs: dict):
        # Pipeline can return an error dict (e.g. local failure) instead of raising
        if outputs.get("error"):
            self._on_failed(outputs["error"])
            return
        if outputs.get("warning"):
            self._log(f"Warning: {outputs['warning']}")
            QMessageBox.warning(self, "Warning", outputs["warning"])

        self.outputs = outputs
        for key, lbl in self.output_labels.items():
            lbl.setText(outputs.get(key, "—"))

        method = outputs.get("processing_method", "local")
        method_text = "Hitem3D API" if method == "hitem3d_api" else "Local Processing"
        self.status_label.setText(f"Completed ({method_text})")

        self.progress.setValue(100)

        if method == "hitem3d_api":
            api_model = outputs.get("api_model", "unknown")
            api_resolution = outputs.get("api_resolution", "unknown")
            api_format = outputs.get("api_format", "unknown")
            self._log(f"API Model: {api_model}, Resolution: {api_resolution}, Format: {api_format}")

        stats = outputs.get("stats") or {}
        total = stats.get("total_seconds")
        stages = stats.get("stages") or {}
        if total is not None:
            self._log(f"Total time: {total:.3f}s")
        if stages:
            for name, secs in stages.items():
                self._log(f"  {name}: {secs:.3f}s")
        files = {k: outputs.get(k) for k in ("obj", "stl", "glb", "fbx", "usdz") if outputs.get(k)}
        self._log(f"Done. Files: {files}")
        system_info = outputs.get("system_info") or {}
        if system_info:
            self._log(
                "System: "
                f"{system_info.get('platform', 'unknown')} | "
                f"CPU: {system_info.get('cpu_count', 'unknown')} | "
                f"RAM Total: {system_info.get('ram_total_gb', 'unknown')}GB | "
                f"RAM Free: {system_info.get('ram_available_gb', 'unknown')}GB"
            )
        self._set_running(False)

    def _on_failed(self, message: str):
        self.status_label.setText("Failed")
        self.progress.setValue(0)
        self._log(f"Error: {message}")
        QMessageBox.critical(self, "Error", message)
        self._set_running(False)

    def reset_ui(self):
        self.selected_path = None
        self.outputs = {}
        self.path_edit.clear()
        self.preview.setText("No image selected")
        self.preview.setPixmap(QPixmap())
        if hasattr(self, "_preview_pix"):
            self._preview_pix = QPixmap()
        for lbl in self.output_labels.values():
            lbl.setText("—")
        self.status_label.setText("Idle")
        self.progress.setValue(0)
        self.logs.clear()
        self._log("Reset.")
        self._update_run_enabled()

    def open_output(self, key: str):
        path = self.outputs.get(key)
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Not available", f"No {key.upper()} file yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    def open_output_folder(self):
        out_dir = os.path.abspath("output")
        os.makedirs(out_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(out_dir))

    # ---- Helpers -----------------------------------------------------
    def _set_running(self, running: bool):
        self.run_btn.setEnabled(not running and bool(self.selected_path))
        self.path_edit.setEnabled(not running)
        self.logs.setEnabled(True)

    def _update_run_enabled(self):
        has_image = bool(self.selected_path)
        if not has_image:
            self.run_btn.setEnabled(False)
            return
            
        # If using API, check token
        if self.api_radio.isChecked():
            token = self.api_token_edit.text().strip()
            credentials = resolve_hitem3d_credentials(token)
            has_credentials = bool(credentials["access_token"] or (credentials["client_id"] and credentials["client_secret"]))
            has_valid_token = bool(token) and len(token) >= 10
            self.run_btn.setEnabled(has_valid_token or has_credentials)
        else:
            self.run_btn.setEnabled(True)

    def _log(self, text: str):
        self.logs.appendPlainText(text)

    def _load_preview(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            self.preview.setText("Preview not available")
            return
        self._preview_pix = pix
        self._update_preview_pixmap()

    def _update_preview_pixmap(self):
        """Scale and set preview pixmap to current label size."""
        if not hasattr(self, "_preview_pix") or self._preview_pix.isNull():
            return
        size = self.preview.size()
        if size.width() < 10 or size.height() < 10:
            return
        self.preview.setPixmap(
            self._preview_pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_preview_pix") and self._preview_pix and not self._preview_pix.isNull():
            self._update_preview_pixmap()

    def _on_method_changed(self):
        """Handle processing method change."""
        use_api = self.api_radio.isChecked()
        self.api_group.setVisible(use_api)
        self._refresh_token_placeholder()
        self._update_requirements_text()
        self._update_run_enabled()

    def _on_model_changed(self):
        """Handle model selection change."""
        self._update_resolution_options()
        self._update_model_description()

    def _update_resolution_options(self):
        """Update resolution dropdown based on selected model."""
        model_key = self.api_model_combo.currentData()
        if not model_key:
            return
            
        model_info = get_available_models()
        hitem3d_models = model_info.get("hitem3d", {}).get("models", {})
        model_data = hitem3d_models.get(model_key, {})
        resolutions = model_data.get("resolutions", ["1024"])
        
        self.api_resolution_combo.clear()
        for res in resolutions:
            display_text = f"{res}³" if res != "1536pro" else "1536³ Pro"
            self.api_resolution_combo.addItem(display_text, res)
        
        self._update_model_description()

    def _update_model_description(self):
        """Update model description label."""
        model_key = self.api_model_combo.currentData()
        if not model_key:
            return
            
        model_info = get_available_models()
        hitem3d_models = model_info.get("hitem3d", {}).get("models", {})
        model_data = hitem3d_models.get(model_key, {})
        description = model_data.get("description", "")
        
        self.model_description_label.setText(description)

    def _validate_token(self):
        """Validate API token (basic check)."""
        token = self.api_token_edit.text().strip()
        credentials = resolve_hitem3d_credentials(token)
        has_credentials = bool(credentials["access_token"] or (credentials["client_id"] and credentials["client_secret"]))
        if not token and has_credentials:
            self.api_token_edit.setStyleSheet("")
            return
        if token and len(token) < 10:
            self.api_token_edit.setStyleSheet("border: 1px solid #ff6b6b;")
        else:
            self.api_token_edit.setStyleSheet("")

    def _save_server_token(self):
        token = self.api_token_edit.text().strip()
        if not token:
            QMessageBox.information(self, "Server Token", "Please enter the API token first.")
            return
        is_valid = asyncio.run(validate_api_token(token))
        if not is_valid:
            QMessageBox.warning(self, "Invalid Credentials", "Please enter valid Hitem3D credentials.")
            return
        try:
            save_hitem3d_credentials(token)
            self._refresh_token_placeholder()
            QMessageBox.information(self, "Server Token", "Server API token saved.")
        except Exception as exc:
            QMessageBox.critical(self, "Server Token", f"Failed to save token: {exc}")

    def _get_processing_options(self):
        """Get current processing options."""
        token = self.api_token_edit.text().strip()
        return {
            "use_api": self.api_radio.isChecked(),
            "api_token": token or None,
            "api_model": self.api_model_combo.currentData(),
            "api_resolution": self.api_resolution_combo.currentData(),
            "api_format": self.api_format_combo.currentData(),
            "quality": self.quality_combo.currentData() or "standard",
        }

    def _update_requirements_text(self):
        use_api = self.api_radio.isChecked()
        self.sys_mode_value.setText("Hitem3D API" if use_api else "Local")
        self.requirements_label.setText(
            "Cloud processing uses the Hitem3D API. Network stability improves completion time."
            if use_api
            else "Local processing runs TripoSR on CPU. Keep at least 6GB RAM available for stable results."
        )

    def _refresh_system_info(self):
        required = 6.0
        try:
            mem = psutil.virtual_memory()
            self.sys_available_value.setText(f"{round(mem.available / (1024 ** 3), 2)} GB")
            self.sys_total_value.setText(f"{round(mem.total / (1024 ** 3), 2)} GB")
            self.sys_required_value.setText(f"{required} GB")
            self.sys_cpu_value.setText(str(os.cpu_count() or "--"))
            self.sys_platform_value.setText(platform.platform())
        except Exception:
            self.sys_available_value.setText("--")
            self.sys_total_value.setText("--")
            self.sys_required_value.setText(f"{required} GB")
            self.sys_cpu_value.setText("--")
            self.sys_platform_value.setText("--")
        self._update_requirements_text()

    def _logout(self):
        if not is_password_configured():
            self.reset_ui()
            return
        self.hide()
        dlg = LoginDialog(self)
        if dlg.exec():
            self.reset_ui()
            self.show()
        else:
            QApplication.instance().quit()

    def _refresh_token_placeholder(self):
        token = self.api_token_edit.text().strip()
        credentials = resolve_hitem3d_credentials(token)
        has_credentials = bool(credentials["access_token"] or (credentials["client_id"] and credentials["client_secret"]))
        if has_credentials and not token:
            self.api_token_edit.setPlaceholderText("Using server credentials (optional)")
        else:
            self.api_token_edit.setPlaceholderText("Enter your Hitem3D API token")

    def _check_for_updates(self):
        if not UPDATE_URL:
            return
        self.update_worker = UpdateCheckWorker(UPDATE_URL, APP_VERSION, parent=self)
        self.update_worker.finished.connect(self._on_update_check)
        self.update_worker.failed.connect(self._on_update_check_failed)
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

    def _on_update_check_failed(self, message: str):
        self._log(f"Update check failed: {message}")

    def _download_update(self, url: str | None):
        if not url:
            return
        if not _is_frozen():
            QMessageBox.information(self, "Update", "Update is available for the packaged .exe build only.")
            return
        self.status_label.setText("Downloading update…")
        self.download_worker = UpdateDownloadWorker(url, parent=self)
        self.download_worker.finished.connect(self._on_update_downloaded)
        self.download_worker.failed.connect(self._on_update_download_failed)
        self.download_worker.start()

    def _on_update_downloaded(self, new_exe: str):
        current_exe = sys.executable
        self._log(f"Downloaded update: {new_exe}")
        self.status_label.setText("Applying update…")
        _launch_update_script(current_exe, new_exe)
        QApplication.instance().quit()

    def _on_update_download_failed(self, message: str):
        self.status_label.setText("Idle")
        QMessageBox.warning(self, "Update failed", message)


def main():
    exit_code = require_login_then_show_app()
    sys.exit(exit_code if exit_code is not None else 0)


if __name__ == "__main__":
    main()
