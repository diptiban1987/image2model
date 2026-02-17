$ErrorActionPreference = "Stop"

Write-Host "Building ImageTo3D Pro..." -ForegroundColor Cyan

# 1. Clean previous build
if (Test-Path "dist") {
    Write-Host "Cleaning dist/..."
    Remove-Item "dist" -Recurse -Force
}
if (Test-Path "build") {
    Write-Host "Cleaning build/..."
    Remove-Item "build" -Recurse -Force
}

# 2. Run PyInstaller
Write-Host "Running PyInstaller..."
pyinstaller ImageTo3DPro.spec --noconfirm --clean

# 3. Post-build tasks
$distDir = "dist\ImageTo3DPro"
if (Test-Path $distDir) {
    Write-Host "Build successful!" -ForegroundColor Green
    
    # Copy updates.json to dist root for easy upload
    Copy-Item "updates.json" -Destination "dist\updates.json"
    
    Write-Host "Artifacts:"
    Write-Host "  - App: $distDir"
    Write-Host "  - Update File: dist\updates.json"
} else {
    Write-Host "Build failed: Output directory not found." -ForegroundColor Red
    exit 1
}
