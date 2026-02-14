from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QGroupBox, QGridLayout,
    QMessageBox, QProgressBar, QCheckBox, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from pathlib import Path
from typing import List

class MultiAngleWidget(QGroupBox):
    files_selected = Signal(list)
    processing_requested = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__("Multi-Angle Input", parent)
        self.image_paths: List[str] = []
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Drag & Drop area
        self.drop_label = QLabel("Drop 3-5 images here\nor click 'Add Images'")
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setStyleSheet("border: 2px dashed #4A90E2; padding: 20px;")
        self.drop_label.setMinimumHeight(100)
        layout.addWidget(self.drop_label)
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(150)
        layout.addWidget(self.file_list)
        
        # Controls
        control_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add Images...")
        self.clear_btn = QPushButton("Clear All")
        self.optimize_btn = QPushButton("Auto-Order")
        
        self.add_btn.clicked.connect(self.add_images)
        self.clear_btn.clicked.connect(self.clear_all)
        self.optimize_btn.clicked.connect(self.auto_order)
        
        control_layout.addWidget(self.add_btn)
        control_layout.addWidget(self.optimize_btn)
        control_layout.addWidget(self.clear_btn)
        layout.addLayout(control_layout)
        
        # Options
        options_box = QGroupBox("Processing Options")
        options_layout = QVBoxLayout(options_box)
        
        self.confidence_weighting = QCheckBox("Use confidence-based weighting")
        self.confidence_weighting.setChecked(True)
        
        self.geometry_boost = QCheckBox("Enhanced geometry reconstruction")
        self.geometry_boost.setChecked(True)
        
        options_layout.addWidget(self.confidence_weighting)
        options_layout.addWidget(self.geometry_boost)
        layout.addWidget(options_box)
        
        # Status
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        image_files = [f for f in files if Path(f).suffix.lower() in ['.png', '.jpg', '.jpeg']]
        
        if len(image_files) + len(self.image_paths) > 5:
            QMessageBox.warning(self, "Too many images", "Maximum 5 images allowed")
            return
            
        self.add_image_paths(image_files)
        
    def add_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "", 
            "Images (*.png *.jpg *.jpeg);;All Files (*)"
        )
        if files:
            if len(files) + len(self.image_paths) > 5:
                QMessageBox.warning(self, "Too many images", "Maximum 5 images allowed")
                return
            self.add_image_paths(files)
            
    def add_image_paths(self, paths: List[str]):
        for path in paths:
            if path not in self.image_paths:
                self.image_paths.append(path)
                item = QListWidgetItem(Path(path).name)
                item.setToolTip(path)
                self.file_list.addItem(item)
                
        self.validate_and_emit()
        
    def clear_all(self):
        self.image_paths.clear()
        self.file_list.clear()
        self.validate_and_emit()
        
    def auto_order(self):
        if len(self.image_paths) < 3:
            QMessageBox.information(self, "Not enough images", "Need at least 3 images for auto-ordering")
            return
            
        QMessageBox.information(self, "Coming soon", "Auto-ordering will analyze images and suggest optimal sequence")
        
    def validate_and_emit(self):
        is_valid = 3 <= len(self.image_paths) <= 5
        if is_valid:
            self.files_selected.emit(self.image_paths)
        return is_valid
        
    def get_processing_options(self) -> dict:
        return {
            "use_confidence_weighting": self.confidence_weighting.isChecked(),
            "use_geometry_boost": self.geometry_boost.isChecked(),
            "image_paths": self.image_paths
        }
        
    def set_processing(self, is_processing: bool):
        self.add_btn.setEnabled(not is_processing)
        self.clear_btn.setEnabled(not is_processing)
        self.optimize_btn.setEnabled(not is_processing)
        self.progress.setVisible(is_processing)
        if is_processing:
            self.progress.setRange(0, 0)
            
    def show_status(self, msg: str):
        self.drop_label.setText(msg)
        QApplication.processEvents()
