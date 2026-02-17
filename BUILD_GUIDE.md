# Building ImageTo3D Pro Executable

This guide explains how to build the standalone Windows executable (.exe) for ImageTo3D Pro v2.1.0.

## Prerequisites

### 1. Windows Environment
- Windows 10 or Windows 11 (64-bit)
- Python 3.10 or higher (64-bit)
- At least 8GB RAM (16GB recommended)
- At least 10GB free disk space

### 2. Install Python Dependencies

Open Command Prompt or PowerShell in the project directory and run:

```cmd
pip install -r requirements.txt
```

This will install all required packages including:
- PyTorch
- PySide6
- Open3D
- Trimesh
- Diffusers
- And all other dependencies

Note: This may take 10-30 minutes depending on your internet connection.

### 3. Install PyInstaller

```cmd
pip install pyinstaller>=6.0
```

## Build Process

### Option 1: Using the Batch File (Recommended)

Simply run the provided batch file:

```cmd
build_exe.bat
```

This will:
1. Install PyInstaller (if not already installed)
2. Clean previous build artifacts
3. Build the executable
4. Verify the output

### Option 2: Manual Build

If you prefer to build manually:

```cmd
# Clean previous builds
rmdir /s /q build
rmdir /s /q dist

# Build the executable
python -m PyInstaller --clean --noconfirm ImageTo3DPro.spec
```

## Build Output

After successful build, you'll find:

- **Executable**: `dist\ImageTo3DPro.exe`
- **Build files**: `build\` directory (can be deleted)
- **Spec file**: `ImageTo3DPro.spec`

The executable size will be approximately 500MB-1GB depending on included dependencies.

## Creating Distribution Package

### 1. Create ZIP File

```cmd
cd dist
zip -r ImageTo3DPro_v2.1.0.zip ImageTo3DPro.exe
```

Or using Windows:
- Right-click on `ImageTo3DPro.exe`
- Select "Send to" → "Compressed (zipped) folder"
- Rename to `ImageTo3DPro_v2.1.0.zip`

### 2. Upload to Update Server

Upload the ZIP file to your web server, for example:
- `https://yourdomain.com/downloads/ImageTo3DPro_v2.1.0.exe`

### 3. Update updates.json

Create or update your `updates.json` file:

```json
{
  "version": "2.1.0",
  "url": "https://yourdomain.com/downloads/ImageTo3DPro_v2.1.0.exe",
  "notes": "New features:\n- Enhanced progress bar with colorful gradient\n- Animated activity log with emoji icons\n- Improved task tracking\n- Web UI now matches desktop layout\n- Various bug fixes and performance improvements"
}
```

### 4. Set Environment Variable

Users need to set this environment variable to enable auto-updates:

```cmd
set IMAGETO3D_UPDATE_URL=https://yourdomain.com/updates.json
```

Or create a `.env` file in the same directory as the executable:
```
IMAGETO3D_UPDATE_URL=https://yourdomain.com/updates.json
```

## Testing the Build

1. Navigate to `dist\` folder
2. Double-click `ImageTo3DPro.exe`
3. Verify the app launches correctly
4. Check that the version shows "v2.1.0" in the title bar
5. Test basic functionality (file selection, processing options)

## Troubleshooting

### Build Fails with "Module Not Found"

Make sure all dependencies are installed:
```cmd
pip install -r requirements.txt --force-reinstall
```

### Build Takes Too Long

The first build includes all dependencies and may take 30-60 minutes. Subsequent builds will be faster.

### Executable Too Large

This is normal for Python applications with PyTorch. The executable includes:
- Python runtime
- PyTorch libraries (~300MB)
- All other dependencies

To reduce size, you can modify the spec file to exclude unnecessary modules.

### Missing Styles or Icons

If the app looks unstyled, ensure the `styles.qss` file is included in the spec file's data section.

### Antivirus False Positive

Some antivirus software may flag PyInstaller executables. This is a known issue. You can:
- Submit the executable to your antivirus vendor for whitelisting
- Code sign the executable with a certificate
- Inform users about the false positive

## Version History

### v2.1.0 (Current)
- Enhanced progress bar with colorful animated gradient
- Animated activity log with emoji icons for different stages
- Improved task tracking with icons
- Web UI redesigned to match desktop app layout
- Added sidebar with device info and system panel
- Various bug fixes and performance improvements

### v2.0.0 (Previous)
- Initial release with desktop and web interfaces
- Device fingerprint authentication
- Local and Cloud API processing
- License management system

## Support

For build issues or questions:
1. Check that all prerequisites are met
2. Ensure you have sufficient disk space
3. Try running the build on a clean Python environment
4. Review the PyInstaller output for specific errors
