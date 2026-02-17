@echo off
chcp 65001 >nul
echo ==========================================
echo ImageTo3D Pro v2.1.0 Build Script
echo ==========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

echo [1/4] Installing PyInstaller...
pip install pyinstaller>=6.0 -q
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    exit /b 1
)

echo [2/4] Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo      Done.

echo [3/4] Building executable...
python -m PyInstaller --clean --noconfirm ImageTo3DPro.spec
if errorlevel 1 (
    echo ERROR: Build failed!
    exit /b 1
)

echo [4/4] Verifying build...
if exist "dist\ImageTo3DPro.exe" (
    echo      SUCCESS: dist\ImageTo3DPro.exe created
    for %%I in ("dist\ImageTo3DPro.exe") do echo      Size: %%~zI bytes
) else (
    echo ERROR: Executable not found
    exit /b 1
)

echo.
echo ==========================================
echo Build Complete! v2.1.0
echo ==========================================
echo Output: dist\ImageTo3DPro.exe
echo.
echo Next steps:
echo   1. Test the executable
echo   2. Create zip file for distribution
echo   3. Upload to your update server
echo   4. Update updates.json with new version
pause
