"""
License Dialog for ImageTo3D Pro

This dialog shows at startup:
- If trial available: Show "Start Free Trial" button
- If trial used: Require license key
- Always show "Purchase License" option
"""

import os
import sys
import asyncio
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QSpacerItem, QSizePolicy,
    QFrame, QProgressDialog
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QDesktopServices

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.license_manager import get_license_manager, LicenseRequiredError
from core.payment_factory import PaymentProcessor, get_payment_processor
from config.payment_config import pricing_config, PAYMENT_PROVIDER
from core.logger import get_logger

logger = get_logger(__name__)


class LicenseDialog(QDialog):
    """
    License/Trial dialog - Shows trial option or license entry.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ImageTo3D Pro - Get Started")
        self.setMinimumWidth(500)
        self.setMinimumHeight(450)
        self.setModal(True)
        
        self.license_manager = get_license_manager()
        self.payment = get_payment_processor()
        
        self._setup_ui()
        self._check_existing_access()
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QLabel("🚀 Welcome to ImageTo3D Pro")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Check trial status and show appropriate UI
        if self.license_manager.has_trial_available():
            self._setup_trial_ui(layout)
        else:
            self._setup_license_ui(layout)
        
        # Spacer
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        # Pricing info
        pricing_label = QLabel(self._get_pricing_text())
        pricing_label.setAlignment(Qt.AlignCenter)
        pricing_label.setStyleSheet("color: #666; font-size: 11px;")
        pricing_label.setWordWrap(True)
        layout.addWidget(pricing_label)
    
    def _setup_trial_ui(self, layout):
        """Setup UI for trial mode."""
        # Trial info
        trial_info = QLabel(
            f"🎉 You have {self.license_manager.get_trial_remaining()} FREE generation remaining!\n\n"
            "Try ImageTo3D Pro with no commitment. Generate your first 3D model for FREE."
        )
        trial_info.setAlignment(Qt.AlignCenter)
        trial_info.setWordWrap(True)
        trial_info.setStyleSheet("color: #28a745; font-size: 14px; font-weight: bold;")
        layout.addWidget(trial_info)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #ccc;")
        layout.addWidget(line)
        
        # Buttons
        button_layout = QVBoxLayout()
        
        # Start Trial button
        self.trial_btn = QPushButton("🚀 Start Free Trial")
        self.trial_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 15px 30px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.trial_btn.clicked.connect(self._start_trial)
        button_layout.addWidget(self.trial_btn)
        
        # OR label
        or_label = QLabel("- OR -")
        or_label.setAlignment(Qt.AlignCenter)
        or_label.setStyleSheet("color: #666; padding: 10px;")
        button_layout.addWidget(or_label)
        
        # Purchase button
        self.purchase_btn = QPushButton("🛒 Purchase License Now")
        self.purchase_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.purchase_btn.clicked.connect(self._show_purchase_options)
        button_layout.addWidget(self.purchase_btn)
        
        layout.addLayout(button_layout)
        
        # Footer note
        footer = QLabel(
            "💡 After your free generation, you'll need a license to continue.\n"
            "Your trial is tied to this computer."
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999; font-size: 10px;")
        footer.setWordWrap(True)
        layout.addWidget(footer)
    
    def _setup_license_ui(self, layout):
        """Setup UI for license entry (trial used)."""
        # Trial expired message
        expired_msg = QLabel(
            "✅ You've used your free trial!\n\n"
            "Ready for more? Enter your license key or purchase one below."
        )
        expired_msg.setAlignment(Qt.AlignCenter)
        expired_msg.setWordWrap(True)
        expired_msg.setStyleSheet("color: #007bff; font-size: 13px;")
        layout.addWidget(expired_msg)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #ccc;")
        layout.addWidget(line)
        
        # License Key Input
        key_layout = QVBoxLayout()
        key_label = QLabel("Enter License Key:")
        key_label.setFont(QFont("", 10, QFont.Bold))
        key_layout.addWidget(key_label)
        
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("I3D-XXXX-XXXX-XXXX-XXXX")
        self.key_input.setMaxLength(24)
        self.key_input.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                font-size: 14px;
                border: 2px solid #ccc;
                border-radius: 5px;
            }
            QLineEdit:focus {
                border-color: #007bff;
            }
        """)
        key_layout.addWidget(self.key_input)
        
        example = QLabel("Example: I3D-ADB1-9890-4517-8E0F")
        example.setStyleSheet("color: #666; font-size: 11px;")
        key_layout.addWidget(example)
        
        layout.addLayout(key_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.validate_btn = QPushButton("✓ Validate License")
        self.validate_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.validate_btn.clicked.connect(self._validate_license)
        button_layout.addWidget(self.validate_btn)
        
        button_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Expanding))
        
        self.purchase_btn = QPushButton("🛒 Purchase License")
        self.purchase_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.purchase_btn.clicked.connect(self._show_purchase_options)
        button_layout.addWidget(self.purchase_btn)
        
        layout.addLayout(button_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # Footer
        footer = QLabel(
            "💡 Your license is tied to this computer. "
            "Contact support to transfer to a new machine."
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999; font-size: 10px;")
        footer.setWordWrap(True)
        layout.addWidget(footer)
    
    def _get_pricing_text(self) -> str:
        """Get pricing information text."""
        plans = pricing_config.plans
        text = "Available Plans:  "
        for plan_id, plan in plans.items():
            text += f"• {plan['name']}: ₹{plan['price']}/mo  "
        return text
    
    def _check_existing_access(self):
        """Check if user already has access (trial or license)."""
        if self.license_manager.can_use_app():
            logger.info("User has access (trial or license), auto-accepting")
            self.accept()
    
    def _start_trial(self):
        """Start the free trial."""
        if self.license_manager.use_trial_generation():
            logger.info("Trial started successfully")
            QMessageBox.information(
                self,
                "Trial Started!",
                "🎉 Your free trial has started!\n\n"
                "You can now generate ONE 3D model for FREE.\n\n"
                "After this, you'll need a license for more generations.\n\n"
                "Click OK to start using ImageTo3D Pro!"
            )
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Trial Error",
                "Could not start trial. Please try again or purchase a license."
            )
    
    def _validate_license(self):
        """Validate the entered license key."""
        license_key = self.key_input.text().strip().upper()
        
        if not license_key:
            self._show_error("Please enter a license key")
            return
        
        if not license_key.startswith("I3D-"):
            self._show_error("Invalid license key format. Should start with 'I3D-'")
            return
        
        # Show progress
        progress = QProgressDialog("Validating license...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._validate_online(license_key))
            loop.close()
            
            progress.close()
            
            if result["valid"]:
                self.license_manager.activate_license(license_key, result["license"])
                
                QMessageBox.information(
                    self,
                    "License Valid",
                    f"✅ License validated successfully!\n\n"
                    f"Plan: {result['license'].plan_id}\n"
                    f"Credits: {result['license'].credits}\n\n"
                    f"Click OK to start using ImageTo3D Pro."
                )
                self.accept()
            else:
                self._show_error(result.get("message", "Invalid license key"))
                
        except Exception as e:
            progress.close()
            logger.error(f"License validation error: {e}")
            self._show_error(f"Validation failed: {str(e)}")
    
    async def _validate_online(self, license_key: str) -> dict:
        """Validate license online."""
        try:
            return await self.license_manager.validate_license_online(license_key)
        except Exception as e:
            logger.error(f"Online validation failed: {e}")
            return {
                "valid": False,
                "message": "Could not validate license. Please check your internet connection."
            }
    
    def _show_purchase_options(self):
        """Show purchase options dialog."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Purchase License")
        msg.setText("Choose how to purchase ImageTo3D Pro:")
        msg.setInformativeText(
            "You'll be redirected to our secure payment partner.\n\n"
            "After payment, you'll receive a license key via email."
        )
        
        gumroad_btn = msg.addButton("Purchase via Gumroad", QMessageBox.ActionRole)
        cancel_btn = msg.addButton("Cancel", QMessageBox.RejectRole)
        
        msg.exec()
        
        if msg.clickedButton() == gumroad_btn:
            self._open_gumroad_store()
    
    def _open_gumroad_store(self):
        """Open Gumroad store."""
        store_url = "https://gumroad.com/imageto3d"  # Update this
        QDesktopServices.openUrl(QUrl(store_url))
        
        QMessageBox.information(
            self,
            "Purchase Initiated",
            "Gumroad has been opened in your browser.\n\n"
            "After completing your purchase:\n"
            "1. Check your email for the license key\n"
            "2. Return to this window\n"
            "3. Enter your license key\n\n"
            "Your license key will look like: I3D-XXXX-XXXX-XXXX-XXXX"
        )
    
    def _show_error(self, message: str):
        """Show error message."""
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"❌ {message}")
            self.status_label.setStyleSheet("color: #dc3545; font-weight: bold;")
        else:
            QMessageBox.warning(self, "Error", message)


def require_license_dialog() -> bool:
    """
    Show license/trial dialog.
    
    Returns True if user has access, False otherwise.
    """
    dialog = LicenseDialog()
    result = dialog.exec()
    
    if result == QDialog.Accepted:
        return True
    else:
        QMessageBox.critical(
            None,
            "Access Required",
            "You need a license or free trial to use ImageTo3D Pro.\n\n"
            "The application will now close."
        )
        return False


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    if require_license_dialog():
        print("Access granted - would start app")
    else:
        print("No access - app would close")
    
    sys.exit(0)
