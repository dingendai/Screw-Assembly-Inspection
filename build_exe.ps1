param(
    [switch]$IncludeCurrentData
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
$SpecPath = Join-Path $ProjectRoot "screw_inspection.spec"
$DistAppDir = Join-Path $ProjectRoot "dist\screw_inspection"
$DistModelsDir = Join-Path $DistAppDir "models"
$DistDataDir = Join-Path $DistAppDir "inspection_data"

if (-not (Test-Path $SpecPath)) {
    throw "Missing spec file: $SpecPath"
}

if (Test-Path $VenvPyInstaller) {
    $PyInstaller = $VenvPyInstaller
} else {
    $PyInstaller = "pyinstaller"
}

Get-Process screw_inspection -ErrorAction SilentlyContinue | Stop-Process -Force

Push-Location $ProjectRoot
try {
    & $PyInstaller --noconfirm --clean $SpecPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    New-Item -ItemType Directory -Force -Path $DistModelsDir | Out-Null
    New-Item -ItemType Directory -Force -Path $DistDataDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $DistDataDir "operator_photos") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $DistDataDir "user_records") | Out-Null

    $SourceModelsDir = Join-Path $ProjectRoot "models"
    if (Test-Path $SourceModelsDir) {
        Copy-Item -Path (Join-Path $SourceModelsDir "*") -Destination $DistModelsDir -Recurse -Force
    }

    if ($IncludeCurrentData) {
        $SourceDataDir = Join-Path $ProjectRoot "app\src\inspection_data"
        if (Test-Path $SourceDataDir) {
            Copy-Item -Path (Join-Path $SourceDataDir "*") -Destination $DistDataDir -Recurse -Force
        }
    }

    Write-Host ""
    Write-Host "Build complete:"
    Write-Host "  $DistAppDir"
    Write-Host ""
    Write-Host "Run:"
    Write-Host "  $DistAppDir\screw_inspection.exe"
} finally {
    Pop-Location
}
