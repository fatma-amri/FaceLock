# PowerShell Uninstallation Script for FaceLock
# Run as Administrator
# Usage: powershell -ExecutionPolicy Bypass -File uninstall.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$InstallPath = "C:\Program Files\FaceLock"
)

# Requires Administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run as Administrator!"
    exit 1
}

Write-Host "================================================" -ForegroundColor Red
Write-Host "FaceLock Windows Integration Uninstaller" -ForegroundColor Red
Write-Host "================================================" -ForegroundColor Red
Write-Host ""

$confirm = Read-Host "Are you sure you want to uninstall FaceLock? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""

# Step 1: Stop and remove Windows Service
Write-Host "[1/4] Removing Windows Service..." -ForegroundColor Yellow
try {
    $svc = Get-Service -Name "FaceRecognitionService" -ErrorAction SilentlyContinue
    if ($svc) {
        Stop-Service -Name "FaceRecognitionService" -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Remove-Item "HKLM:\SYSTEM\CurrentControlSet\Services\FaceRecognitionService" -Force -ErrorAction SilentlyContinue
        Write-Host "✓ Service removed" -ForegroundColor Green
    } else {
        Write-Host "✓ Service not found" -ForegroundColor Green
    }
} catch {
    Write-Error "Failed to remove service: $_"
}

# Step 2: Unregister COM DLL
Write-Host "[2/4] Unregistering Credential Provider..." -ForegroundColor Yellow
try {
    $dllPath = Join-Path $InstallPath "CredentialProvider.dll"
    if (Test-Path $dllPath) {
        & regsvr32 /u /s $dllPath
        Write-Host "✓ Credential Provider unregistered" -ForegroundColor Green
    } else {
        Write-Host "✓ DLL not found" -ForegroundColor Green
    }
} catch {
    Write-Error "Failed to unregister DLL: $_"
}

# Step 3: Remove registry entries
Write-Host "[3/4] Removing registry entries..." -ForegroundColor Yellow
try {
    Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{A1B2C3D4-E5F6-47A8-9B0C-1D2E3F4A5B6C}" -Force -ErrorAction SilentlyContinue
    Remove-Item "HKEY_CLASSES_ROOT\CLSID\{A1B2C3D4-E5F6-47A8-9B0C-1D2E3F4A5B6C}" -Force -ErrorAction SilentlyContinue
    Write-Host "✓ Registry cleaned" -ForegroundColor Green
} catch {
    Write-Error "Failed to clean registry: $_"
}

# Step 4: Remove installation directory
Write-Host "[4/4] Removing installation directory..." -ForegroundColor Yellow
try {
    if (Test-Path $InstallPath) {
        Remove-Item -Path $InstallPath -Recurse -Force
        Write-Host "✓ Installation directory removed" -ForegroundColor Green
    } else {
        Write-Host "✓ Directory not found" -ForegroundColor Green
    }
} catch {
    Write-Error "Failed to remove directory: $_"
}

# Step 5: Remove shortcuts
Write-Host "[5/5] Removing shortcuts..." -ForegroundColor Yellow
try {
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $enrollmentLnk = Join-Path $desktopPath "FaceLock Enrollment.lnk"
    if (Test-Path $enrollmentLnk) {
        Remove-Item $enrollmentLnk -Force
        Write-Host "✓ Shortcuts removed" -ForegroundColor Green
    }
} catch {
    Write-Error "Failed to remove shortcuts: $_"
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Red
Write-Host "Uninstallation Complete!" -ForegroundColor Red
Write-Host "================================================" -ForegroundColor Red
