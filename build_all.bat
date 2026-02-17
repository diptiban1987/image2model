@echo off
chcp 65001 >nul
title ImageTo3D Pro v2.1.0 - Complete Build System
cls

echo ============================================
echo  ImageTo3D Pro v2.1.0 - Complete Build
echo ============================================
echo.
echo This script will build BOTH the application
echo and the Windows installer in one step.
echo.
echo Steps:
echo   1. Build PyInstaller executable
echo   2. Build Windows installer
echo.
pause
cls

REM Check for Python
echo [PRE-CHECK] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10 or higher from python.org
    pause
    exit /b 1
)
python --version
echo.

REM Check for Inno Setup
echo [PRE-CHECK] Checking Inno Setup...
set "INNO_SETUP_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if not defined INNO_SETUP_PATH (
    echo [WARNING] Inno Setup not found!
    echo Please install from: https://jrsoftware.org/isdl.php
    echo.
    echo Do you want to continue without building the installer? (Y/N)
    choice /c YN /n
    if errorlevel 2 exit /b 1
    set "SKIP_INSTALLER=1"
) else (
    echo Inno Setup found: %INNO_SETUP_PATH%
    set "SKIP_INSTALLER=0"
)
echo.

REM ============================================================================
echo STEP 1: Building Application Executable
echo ============================================================================
echo.

if not exist "build_exe.bat" (
    echo [ERROR] build_exe.bat not found!
    echo Please ensure you are in the project root directory.
    pause
    exit /b 1
)

call build_exe.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Application build failed!
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Application executable built successfully!
echo.

REM Check if we should skip installer
if "%SKIP_INSTALLER%"=="1" (
    echo.
    echo [INFO] Skipping installer build (Inno Setup not found)
    echo.
    echo Build Summary:
    echo   Application: dist\ImageTo3DPro.exe
    echo   Version: 2.1.0
    echo.
    echo To build the installer later, run:
    echo   cd installer
    echo   build_installer.bat
    echo.
    pause
    exit /b 0
)

REM ============================================================================
echo STEP 2: Building Windows Installer
echo ============================================================================
echo.

if not exist "installer\build_installer.bat" (
    echo [ERROR] Installer build script not found!
    echo Please ensure the installer directory exists.
    pause
    exit /b 1
)

cd installer
call build_installer.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Installer build failed!
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo [SUCCESS] Installer built successfully!
echo.

REM ============================================================================
echo BUILD COMPLETE!
echo ============================================================================
echo.
echo All Files Created:
echo.
echo [1] Application Executable:
echo     Location: dist\ImageTo3DPro.exe
echo     Size: 
for %%I in ("dist\ImageTo3DPro.exe") do echo             %%~zI bytes
echo.
echo [2] Windows Installer:
echo     Location: installer\output\ImageTo3DPro_Setup_v2.1.0.exe
echo     Size: 
for %%I in ("installer\output\ImageTo3DPro_Setup_v2.1.0.exe") do echo             %%~zI bytes
echo.
echo Features:
echo   Application:
echo     - Self-contained executable (no Python needed)
echo     - Includes all dependencies (PyTorch, PySide6, etc.)
echo     - Version 2.1.0 with enhanced progress bar
echo     - Animated activity log with emoji icons
echo.
echo   Installer:
echo     - Professional Windows installer
echo     - Installs to C:\Program Files\ImageTo3D Pro\
echo     - Custom branding with your logo
echo     - Sample images included (temple.jpg, API_TEMPLE.png)
echo     - Documentation included (README, User Guide, etc.)
echo     - Auto-upgrade from v2.0.0
echo     - Desktop shortcut option (user choice)
echo     - Launch checkbox on finish page
echo     - Full uninstall support
echo.
echo Next Steps:
echo   1. Test the installer on a clean Windows VM
echo   2. Create distribution package:
echo      copy installer\output\ImageTo3DPro_Setup_v2.1.0.exe ^
echo           ImageTo3DPro_Setup_v2.1.0.exe
echo   3. Upload to your distribution server
echo   4. Update updates.json for auto-updater:
echo      {
echo        "version": "2.1.0",
echo        "url": "https://yourserver.com/ImageTo3DPro_Setup_v2.1.0.exe",
echo        "notes": "Enhanced UI, animated progress, web redesign"
echo      }
echo   5. Set environment variable on user machines:
echo      set IMAGETO3D_UPDATE_URL=https://yourserver.com/updates.json
echo.
pause
