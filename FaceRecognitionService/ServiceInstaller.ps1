# PowerShell Script to Install/Uninstall FaceRecognitionService
# Run as Administrator

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("install", "uninstall")]
    [string]$Action,
    
    [Parameter(Mandatory=$false)]
    [string]$ServicePath = "C:\Program Files\FaceLock\FaceRecognitionService.exe"
)

# Requires Administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run as Administrator!"
    exit 1
}

function Install-Service {
    param(
        [string]$ExePath
    )
    
    if (-NOT (Test-Path $ExePath)) {
        Write-Error "Service executable not found: $ExePath"
        exit 1
    }
    
    Write-Host "Installing FaceRecognitionService..." -ForegroundColor Cyan
    
    try {
        # Create Windows Service
        $serviceName = "FaceRecognitionService"
        $displayName = "FaceLock Recognition Service"
        $description = "Biometric authentication service for FaceLock"
        
        # Remove if already exists
        if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
            Write-Host "Service already exists. Removing..." -ForegroundColor Yellow
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            Remove-Item "HKLM:\SYSTEM\CurrentControlSet\Services\$serviceName" -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        }
        
        # Create new service
        New-Service -Name $serviceName `
                   -DisplayName $displayName `
                   -BinaryPathName $ExePath `
                   -StartupType Automatic `
                   -Description $description | Out-Null
        
        Write-Host "✓ Service created successfully" -ForegroundColor Green
        
        # Start the service
        Start-Service -Name $serviceName
        Start-Sleep -Seconds 2
        
        $serviceStatus = (Get-Service -Name $serviceName).Status
        if ($serviceStatus -eq "Running") {
            Write-Host "✓ Service is running" -ForegroundColor Green
        } else {
            Write-Host "✗ Service failed to start" -ForegroundColor Red
            exit 1
        }
    }
    catch {
        Write-Error "Failed to install service: $_"
        exit 1
    }
}

function Uninstall-Service {
    try {
        $serviceName = "FaceRecognitionService"
        
        Write-Host "Uninstalling FaceRecognitionService..." -ForegroundColor Cyan
        
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            Remove-Item "HKLM:\SYSTEM\CurrentControlSet\Services\$serviceName" -Force -ErrorAction SilentlyContinue
            Write-Host "✓ Service uninstalled successfully" -ForegroundColor Green
        } else {
            Write-Host "Service not found" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Error "Failed to uninstall service: $_"
        exit 1
    }
}

switch ($Action) {
    "install" {
        Install-Service -ExePath $ServicePath
    }
    "uninstall" {
        Uninstall-Service
    }
}

Write-Host "Done." -ForegroundColor Green
