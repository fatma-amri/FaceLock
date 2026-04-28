# PowerShell Installation Script for FaceLock Windows Integration
# Run as Administrator
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$InstallPath = "C:\Program Files\FaceLock",
    
    [Parameter(Mandatory=$false)]
    [string]$PythonVenvPath = "$InstallPath\.venv"
)

# Requires Administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run as Administrator!"
    exit 1
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "FaceLock Windows Integration Installer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Create installation directory
Write-Host "[1/7] Creating installation directory..." -ForegroundColor Yellow
try {
    if (-NOT (Test-Path $InstallPath)) {
        New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
        Write-Host "✓ Created $InstallPath" -ForegroundColor Green
    } else {
        Write-Host "✓ Directory already exists" -ForegroundColor Green
    }
} catch {
    Write-Error "Failed to create directory: $_"
    exit 1
}

# Step 2: Copy Python project files
Write-Host "[2/7] Copying Python project files..." -ForegroundColor Yellow
try {
    $sourceDir = Split-Path -Parent $PSCommandPath
    $sourceDir = Split-Path -Parent $sourceDir  # Go up from Installer/
    
    $pythonFiles = @(
        "main.py",
        "enrollment_ui.py", 
        "face_authenticator_pipe.py",
        "requirements.txt",
        "modules"
    )
    
    foreach ($file in $pythonFiles) {
        $src = Join-Path $sourceDir $file
        $dst = Join-Path $InstallPath $file
        
        if (Test-Path $src) {
            if ((Get-Item $src).PSIsContainer) {
                Copy-Item -Path $src -Destination $dst -Recurse -Force
            } else {
                Copy-Item -Path $src -Destination $dst -Force
            }
            Write-Host "✓ Copied $file" -ForegroundColor Green
        }
    }
    
    # Copy model file
    $modelSrc = Join-Path $sourceDir "models"
    if (Test-Path $modelSrc) {
        $modelDst = Join-Path $InstallPath "models"
        Copy-Item -Path $modelSrc -Destination $modelDst -Recurse -Force
        Write-Host "✓ Copied models/" -ForegroundColor Green
    }
} catch {
    Write-Error "Failed to copy files: $_"
    exit 1
}

# Step 3: Create/update Python virtual environment
Write-Host "[3/7] Setting up Python virtual environment..." -ForegroundColor Yellow
try {
    if (-NOT (Test-Path $PythonVenvPath)) {
        & python -m venv $PythonVenvPath
        Write-Host "✓ Created virtual environment" -ForegroundColor Green
    } else {
        Write-Host "✓ Virtual environment already exists" -ForegroundColor Green
    }
    
    # Upgrade pip
    $pythonExe = Join-Path $PythonVenvPath "Scripts\python.exe"
    & $pythonExe -m pip install --upgrade pip setuptools wheel 2>&1 | Out-Null
    Write-Host "✓ Upgraded pip" -ForegroundColor Green
} catch {
    Write-Error "Failed to create virtual environment: $_"
    exit 1
}

# Step 4: Install Python dependencies
Write-Host "[4/7] Installing Python dependencies..." -ForegroundColor Yellow
try {
    $reqFile = Join-Path $InstallPath "requirements.txt"
    & $pythonExe -m pip install -r $reqFile 2>&1 | Out-Null
    Write-Host "✓ Installed dependencies" -ForegroundColor Green
} catch {
    Write-Error "Failed to install dependencies: $_"
    exit 1
}

# Step 5: Copy and register C++ Credential Provider
Write-Host "[5/7] Setting up Credential Provider..." -ForegroundColor Yellow
try {
    # Check multiple possible locations for compiled DLL
    $dllPaths = @(
        "$sourceDir\CredentialProvider\bin\Release\x64\CredentialProvider.dll",
        "$sourceDir\CredentialProvider\bin\Release\CredentialProvider.dll",
        "$sourceDir\CredentialProvider\x64\Release\CredentialProvider.dll"
    )
    
    $dllFound = $false
    foreach ($dllPath in $dllPaths) {
        if (Test-Path $dllPath) {
            Copy-Item -Path $dllPath -Destination $InstallPath -Force
            Write-Host "✓ Copied CredentialProvider.dll from $dllPath" -ForegroundColor Green
            $dllFound = $true
            break
        }
    }
    
    if ($dllFound) {
        # Register DLL as COM component
        $dllFullPath = Join-Path $InstallPath "CredentialProvider.dll"
        & regsvr32.exe /s "$dllFullPath"
        Write-Host "✓ Registered COM DLL (regsvr32)" -ForegroundColor Green
    } else {
        Write-Host "⚠ CredentialProvider.dll not found in expected locations" -ForegroundColor Yellow
        Write-Host "  Make sure to compile the C++ project first in Visual Studio 2022" -ForegroundColor Yellow
    }
    
    # Import registry settings
    $regSrc = "$sourceDir\CredentialProvider\register.reg"
    if (Test-Path $regSrc) {
        & reg import "$regSrc" 2>&1 | Out-Null
        Write-Host "✓ Imported registry settings" -ForegroundColor Green
    } else {
        Write-Host "⚠ register.reg not found" -ForegroundColor Yellow
    }
} catch {
    Write-Error "Failed to install Credential Provider: $_"
    # Don't exit - this is not critical
}

# Step 6: Copy and install Windows Service
Write-Host "[6/7] Installing Windows Service..." -ForegroundColor Yellow
try {
    $svcSrc = "$sourceDir\FaceRecognitionService\bin\Release\FaceRecognitionService.exe"
    
    if (Test-Path $svcSrc) {
        Copy-Item -Path $svcSrc -Destination $InstallPath -Force
        Write-Host "✓ Copied FaceRecognitionService.exe" -ForegroundColor Green
        
        # Install service using PowerShell
        $svcExe = Join-Path $InstallPath "FaceRecognitionService.exe"
        
        # Remove if already exists
        $svc = Get-Service -Name "FaceRecognitionService" -ErrorAction SilentlyContinue
        if ($svc) {
            Stop-Service -Name "FaceRecognitionService" -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        
        # Create service
        New-Service -Name "FaceRecognitionService" `
                   -DisplayName "FaceLock Recognition Service" `
                   -BinaryPathName $svcExe `
                   -StartupType Automatic `
                   -Description "Biometric authentication service for FaceLock" `
                   -ErrorAction SilentlyContinue | Out-Null
        
        Write-Host "✓ Created Windows Service" -ForegroundColor Green
        
        # Start service
        Start-Service -Name "FaceRecognitionService" -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        
        $svcStatus = (Get-Service -Name "FaceRecognitionService").Status
        if ($svcStatus -eq "Running") {
            Write-Host "✓ Service is running" -ForegroundColor Green
        } else {
            Write-Host "⚠ Service not running (may not be compiled yet)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "⚠ FaceRecognitionService.exe not found (may not be compiled yet)" -ForegroundColor Yellow
    }
} catch {
    Write-Error "Failed to install service: $_"
    # Don't exit - this is not critical
}

# Step 7: Create shortcuts and config
Write-Host "[7/7] Creating shortcuts..." -ForegroundColor Yellow
try {
    $enrollmentScript = Join-Path $InstallPath "enrollment_ui.py"
    $mainScript = Join-Path $InstallPath "main.py"
    $pythonExe = Join-Path $PythonVenvPath "Scripts\python.exe"
    
    # Desktop shortcuts
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    
    # Enrollment shortcut
    $enrollmentLnk = Join-Path $desktopPath "FaceLock Enrollment.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($enrollmentLnk)
    $shortcut.TargetPath = $pythonExe
    $shortcut.Arguments = "`"$enrollmentScript`""
    $shortcut.WorkingDirectory = $InstallPath
    $shortcut.IconLocation = "$InstallPath\icon.ico"
    $shortcut.Save()
    
    Write-Host "✓ Created enrollment shortcut" -ForegroundColor Green
} catch {
    Write-Host "⚠ Failed to create shortcuts: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "1. Enroll your face: Run 'FaceLock Enrollment' shortcut on desktop"
Write-Host "2. Start daemon: Run 'python main.py' from $InstallPath"
Write-Host "3. The service will auto-start and listen for login attempts"
Write-Host ""
Write-Host "Service status: $svcStatus"
Write-Host "Installation path: $InstallPath"
Write-Host ""
