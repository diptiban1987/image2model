#!/usr/bin/env python3
"""
Build script for ImageTo3D Pro v2.1.0
Creates a standalone Windows executable using PyInstaller
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

# Configuration
APP_NAME = "ImageTo3DPro"
APP_VERSION = "2.1.0"
SPEC_FILE = "ImageTo3DPro.spec"
BUILD_DIR = "build"
DIST_DIR = "dist"


def clean_build():
    """Remove previous build artifacts."""
    print("🧹 Cleaning previous builds...")

    # Remove build directory
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
        print(f"   Removed {BUILD_DIR}/")

    # Remove dist directory
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
        print(f"   Removed {DIST_DIR}/")

    # Remove spec file if exists (we use our custom one)
    spec_path = Path(SPEC_FILE)
    if spec_path.exists():
        print(f"   Using existing {SPEC_FILE}")


def install_pyinstaller():
    """Ensure PyInstaller is installed."""
    print("📦 Checking PyInstaller...")
    try:
        import PyInstaller

        print(f"   PyInstaller {PyInstaller.__version__} is installed")
    except ImportError:
        print("   Installing PyInstaller...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"]
        )
        print("   PyInstaller installed successfully")


def create_version_file():
    """Create version info file for Windows executable."""
    print("📝 Creating version info...")

    version_info = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({APP_VERSION.replace(".", ", ")}, 0),
    prodvers=({APP_VERSION.replace(".", ", ")}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'ImageTo3D Pro'),
        StringStruct(u'FileDescription', u'Image to 3D Model Converter'),
        StringStruct(u'FileVersion', u'{APP_VERSION}'),
        StringStruct(u'InternalName', u'ImageTo3DPro'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2024'),
        StringStruct(u'OriginalFilename', u'ImageTo3DPro.exe'),
        StringStruct(u'ProductName', u'ImageTo3D Pro'),
        StringStruct(u'ProductVersion', u'{APP_VERSION}')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)"""

    with open("version.txt", "w") as f:
        f.write(version_info)
    print(f"   Created version.txt (v{APP_VERSION})")


def build_exe():
    """Build the executable using PyInstaller."""
    print(f"🔨 Building {APP_NAME} v{APP_VERSION}...")
    print("   This may take a few minutes...")

    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", SPEC_FILE]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print("❌ Build failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False

        print("✅ Build completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Build error: {e}")
        return False


def verify_build():
    """Verify the executable was created."""
    exe_path = Path(DIST_DIR) / f"{APP_NAME}.exe"

    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"✅ Executable created: {exe_path}")
        print(f"   Size: {size_mb:.1f} MB")
        return True
    else:
        print(f"❌ Executable not found at {exe_path}")
        return False


def create_distribution_package():
    """Create a zip file for distribution."""
    print("📦 Creating distribution package...")

    import zipfile

    zip_name = f"{APP_NAME}_v{APP_VERSION}.zip"
    exe_path = Path(DIST_DIR) / f"{APP_NAME}.exe"

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(exe_path, f"{APP_NAME}.exe")

    zip_size = Path(zip_name).stat().st_size / (1024 * 1024)
    print(f"   Created {zip_name} ({zip_size:.1f} MB)")
    return zip_name


def main():
    """Main build process."""
    print(f"🚀 ImageTo3D Pro Build Script v{APP_VERSION}")
    print("=" * 50)

    # Step 1: Clean previous builds
    clean_build()

    # Step 2: Install PyInstaller
    install_pyinstaller()

    # Step 3: Create version file
    create_version_file()

    # Step 4: Build executable
    if not build_exe():
        sys.exit(1)

    # Step 5: Verify build
    if not verify_build():
        sys.exit(1)

    # Step 6: Create distribution package
    zip_file = create_distribution_package()

    print("\n" + "=" * 50)
    print("✨ Build Complete!")
    print(f"📁 Output: dist/{APP_NAME}.exe")
    print(f"📦 Package: {zip_file}")
    print("\n📋 Next steps:")
    print("   1. Test the executable: dist/ImageTo3DPro.exe")
    print("   2. Upload the zip file to your update server")
    print("   3. Update your updates.json file with new version")
    print(f"   4. Set IMAGETO3D_UPDATE_URL environment variable")


if __name__ == "__main__":
    main()
