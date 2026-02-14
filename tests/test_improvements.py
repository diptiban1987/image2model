"""
Tests for the code improvements made to ImageTo3D Pro

Run with: python -m pytest tests/test_improvements.py -v
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from config.settings import config, ConfigManager
from core.logger import get_logger, Logger


class TestConfiguration:
    """Tests for the centralized configuration module."""
    
    def test_config_singleton(self):
        """Test that config is a singleton."""
        assert isinstance(config, ConfigManager)
    
    def test_processing_config(self):
        """Test processing configuration values."""
        assert config.processing.min_images == 3
        assert config.processing.max_images == 5
        assert config.processing.local_min_ram_gb == 6.0
        assert config.processing.default_quality == "standard"
        assert "standard" in config.processing.available_qualities
    
    def test_api_config(self):
        """Test API configuration values."""
        assert config.api.timeout_seconds > 0
        assert config.api.max_retries >= 0
        assert "hitem3dv1.5" in config.api.credit_costs
    
    def test_ui_config(self):
        """Test UI configuration values."""
        assert config.ui.app_name == "Image → 3D Pro"
        assert ".png" in config.ui.supported_image_formats
        assert "glb" in config.ui.output_formats
    
    def test_quality_validation(self):
        """Test quality level validation."""
        assert config.is_valid_quality("standard") is True
        assert config.is_valid_quality("invalid") is False
    
    def test_image_format_validation(self):
        """Test image format validation."""
        assert config.is_supported_image_format("test.png") is True
        assert config.is_supported_image_format("test.jpg") is True
        assert config.is_supported_image_format("test.txt") is False
    
    def test_credit_cost_lookup(self):
        """Test credit cost retrieval."""
        cost = config.get_required_credits("hitem3dv1.5", "1024")
        assert cost == 20
        
        invalid = config.get_required_credits("invalid", "1024")
        assert invalid is None


class TestLogging:
    """Tests for the structured logging module."""
    
    def test_logger_creation(self):
        """Test logger creation."""
        logger = get_logger("test_module")
        assert isinstance(logger, Logger)
    
    def test_logger_singleton(self):
        """Test that loggers are cached."""
        logger1 = get_logger("test_singleton")
        logger2 = get_logger("test_singleton")
        assert logger1 is logger2
    
    def test_logger_methods(self):
        """Test logger methods don't raise exceptions."""
        logger = get_logger("test_methods")
        
        # These should not raise
        logger.debug("Debug message", context={"key": "value"})
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        
        # Test with context
        logger.info("Test", context={"test": True}, pipeline_stage="test_stage")


class TestBugFixes:
    """Tests to verify bug fixes."""
    
    def test_list_import_in_app(self):
        """Verify List is imported in app.py"""
        app_path = ROOT / "ui" / "desktop" / "app.py"
        assert app_path.exists()
        
        content = app_path.read_text()
        assert "from typing import List" in content
    
    def test_typo_fixed_in_multiangle(self):
        """Verify typo is fixed in multiangle_processor.py"""
        proc_path = ROOT / "core" / "multiangle_processor.py"
        assert proc_path.exists()
        
        content = proc_path.read_text()
        # Should have correct key name
        assert "confidence_scores" in content
        # Should NOT have the typo
        assert "conf is_multimodal_scores" not in content


class TestImports:
    """Test that all modules can be imported without errors."""
    
    def test_import_config(self):
        """Test config module imports."""
        from config.settings import ProcessingConfig, APIConfig, UIConfig, SecurityConfig
        assert ProcessingConfig is not None
        assert APIConfig is not None
    
    def test_import_logger(self):
        """Test logger module imports."""
        from core.logger import (
            get_logger, Logger, log_exception, 
            PipelineStageLogger, TimedContext
        )
        assert get_logger is not None
        assert Logger is not None


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running basic import tests...")
    
    # Test config
    print(f"✓ Config loaded: {config.ui.app_name}")
    print(f"✓ Min RAM required: {config.processing.local_min_ram_gb}GB")
    print(f"✓ API timeout: {config.api.timeout_seconds}s")
    
    # Test logger
    logger = get_logger("test")
    logger.info("Test logging works!")
    print("✓ Logger works")
    
    # Test bug fixes
    app_path = ROOT / "ui" / "desktop" / "app.py"
    content = app_path.read_text()
    assert "from typing import List" in content
    print("✓ List import fixed in app.py")
    
    proc_path = ROOT / "core" / "multiangle_processor.py"
    content = proc_path.read_text()
    assert "conf is_multimodal_scores" not in content
    print("✓ Typo fixed in multiangle_processor.py")
    
    print("\n✅ All basic tests passed!")
