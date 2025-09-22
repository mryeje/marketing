<#
PowerShell helper script to:
- back up the requirements file
- relax pins for gradio_client and fastapi (and altair optionally)
- create a test requirements file without a "diffusers @ git+..." line
- run pip install -vvv using the .venv python, capture verbose output to a file, and print the tail

Usage:
powershell -ExecutionPolicy Bypass -File .\check-resolve.ps1

You can also pass custom paths:
.\check-resolve.ps1 -RequirementsFile ".\requirements.txt" -VenvPython ".\myenv\Scripts\python.exe"

#>

param(
    [string]$RequirementsFile = ".\requirements-gradio-4-range.txt",
    [string]$VenvPython = ".\.venv\Scripts\python.exe",
    [string]$TestRequirements = ".\requirements-test.txt",
    [string]$VerboseOutput = ".\pip-install-output-verbose-test.txt",
    [int]$TailLines = 500
)

# Fail early on errors
$ErrorActionPreference = "Stop"

Write-Host "Starting check-resolve.ps1"
Write-Host "Requirements file: $RequirementsFile"
Write-Host "Venv python: $VenvPython"

# Ensure requirements file exists
if (-not (Test-Path $RequirementsFile)) {
    Write-Error "Requirements file not found: $RequirementsFile"
    exit 1
}

# Backup the original requirements file (overwrites previous backup)
$backup = "$RequirementsFile.bak"
Copy-Item -Path $RequirementsFile -Destination $backup -Force
Write-Host "Backup created: $backup"

# Read, perform safe replacements to relax strict pins
$content = Get-Content $RequirementsFile -Raw -ErrorAction Stop

# Replace strict pins with ranges (won't duplicate if already relaxed)
$content = $content -replace '(?m)^\s*gradio_client==1\.13\.1\s*$', 'gradio_client>=1.13.1,<2.0'
$content = $content -replace '(?m)^\s*fastapi==0\.116\.2\s*$', 'fastapi>=0.116.2,<1.0'
# Optional: relax altair exact pin -> range
$content = $content -replace '(?m)^\s*altair==4\.2\.2\s*$', 'altair>=4.2.2,<5.0'

# Write changes back
Set-Content -Path $RequirementsFile -Value $content -Force
Write-Host "Relaxed pins written to $RequirementsFile"

# Show the changed lines for quick verification
Write-Host "`nShowing lines for gradio_client, fastapi, altair:"
Get-Content $RequirementsFile | Where-Object { $_ -match '^(gradio_client|fastapi|altair)' } | ForEach-Object { Write-Host "`t$_" }

# Create test requirements file without diffusers git line
Get-Content $RequirementsFile | Where-Object { $_ -notmatch '^diffusers\s*@' } | Set-Content $TestRequirements
Write-Host "`nTest requirements written to: $TestRequirements (diffusers lines removed)"

# Ensure venv python exists
if (-not (Test-Path $VenvPython)) {
    Write-Warning "Venv python not found at $VenvPython. Attempting to use 'python' from PATH."
    $VenvPython = "python"
}

# Run pip install -vvv against the test requirements, capture full output
Write-Host "`nRunning pip install -vvv (this may take a while)..."
& "$VenvPython" -m pip install -r "$TestRequirements" -vvv 2>&1 | Tee-Object -FilePath $VerboseOutput

$lastLines = Get-Content $VerboseOutput -ErrorAction SilentlyContinue | Select-Object -Last $TailLines
Write-Host "`n--- Last $TailLines lines of $VerboseOutput ---`n"
$lastLines | ForEach-Object { Write-Host $_ }

# Exit with pip's success/failure code if possible - note: call operator returns exit code in $LASTEXITCODE
if ($LASTEXITCODE -ne $null) {
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nPip install finished successfully."
        exit 0
    } else {
        Write-Warning "`nPip install exited with code $LASTEXITCODE (Resolution errors may be in the output above)."
        exit $LASTEXITCODE
    }
} else {
    Write-Host "`nNote: could not determine pip exit code (running python from PATH may not set $LASTEXITCODE). Inspect $VerboseOutput."
}