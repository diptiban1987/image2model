@echo off
chcp 65001 >nul
title ImageTo3D Pro v2.1.0 - Installer Builder
cls

echo ============================================
echo  ImageTo3D Pro v2.1.0 - Installer Builder
echo ============================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Not running as administrator.
    echo Some operations may fail. It is recommended to run as admin.
    echo.
    pause
)

REM Check for Inno Setup
set "INNO_SETUP_PATH="

REM Try common installation paths
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
) else if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "INNO_SETUP_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)

if not defined INNO_SETUP_PATH (
    echo [ERROR] Inno Setup 6 not found!
    echo.
    echo Please install Inno Setup 6 from:
    echo https://jrsoftware.org/isdl.php
    echo.
    echo Or download the portable version and place it in:
    echo C:\Program Files (x86)\Inno Setup 6\
    echo.
    pause
    exit /b 1
)

echo [1/5] Inno Setup found at:
echo      %INNO_SETUP_PATH%
echo.

REM Check if application executable exists
if not exist "..\dist\ImageTo3DPro.exe" (
    echo [ERROR] Application executable not found!
    echo.
    echo Please build the application first using:
    echo   build_exe.bat
echo.
    echo Or manually:
    echo   python -m PyInstaller --clean --noconfirm ImageTo3DPro.spec
    echo.
    pause
    exit /b 1
)

echo [2/5] Application executable found
echo      ..\dist\ImageTo3DPro.exe
echo.

REM Clean previous installer builds
echo [3/5] Cleaning previous installer builds...
if exist output rmdir /s /q output 2>nul
if exist output rmdir /s /q output
mkdir output 2>nul
echo      Done.
echo.

REM Build the installer
echo [4/5] Building installer...
echo      This may take 5-10 minutes depending on your system...
echo.

"%INNO_SETUP_PATH%" /Q "ImageTo3DPro.iss"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installer build failed!
    echo Please check the error messages above.
    echo.
    pause
    exit /b 1
)

echo.
echo [5/5] Verifying installer...
if exist "output\ImageTo3DPro_Setup_v2.1.0.exe" (
    echo      SUCCESS: Installer created successfully!
    echo.
    for %%I in ("output\ImageTo3DPro_Setup_v2.1.0.exe") do (
        echo      File: output\ImageTo3DPro_Setup_v2.1.0.exe
        echo      Size: %%~zI bytes (%%~zI / 1024 / 1024 MB)
    )
) else (
    echo      ERROR: Installer file not found!
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build Complete!
echo ============================================
echo.
echo Installer Details:
echo   File: output\ImageTo3DPro_Setup_v2.1.0.exe
echo   Version: 2.1.0
echo   Location: C:\Program Files\ImageTo3D Pro\
echo   Features:
echo     - Custom branding with logo
echo     - Sample images included
echo     - Documentation included
echo     - Auto-upgrade from v2.0.0
echo     - Desktop shortcut option
echo     - Launch checkbox on finish
echo.
echo Next Steps:
echo   1. Test the installer on a clean VM
echo   2. Upload to your distribution server
echo   3. Update updates.json for auto-updates
echo   4. Distribute to users
echo.
pause
