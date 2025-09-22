<#
check-resolve-nogit.ps1
- Backup requirements
- Relax gradio_client and fastapi pins (and altair)
- Create a test requirements file excluding any git+ lines and diffusers @ lines
- Run pip install -vvv using .venv python, capture full log, and print tail

Usage:
powershell -ExecutionPolicy Bypass -File .\check-resolve-nogit.ps1
#>

param(
    [string]$RequirementsFile = ".\requirements-gradio-4-range.txt",
    [string]$VenvPython = ".\.venv\Scripts\python.exe",
    [string]$TestRequirements = ".\requirements-test-nogit.txt",
    [string]$VerboseOutput = ".\pip-install-output-verbose-nogit.txt",
    [int]$TailLines = 500
)

$ErrorActionPreference = "Stop"

Write-Host "Starting check-resolve-nogit.ps1"
Write-Host "Requirements file: $RequirementsFile"
Write-Host "Venv python: $VenvPython"

if (-not (Test-Path $RequirementsFile)) {
    Write-Error "Requirements file not found: $RequirementsFile"
    exit 1
}

# Backup original
$backup = "$RequirementsFile.bak"
Copy-Item -Path $RequirementsFile -Destination $backup -Force
Write-Host "Backup created: $backup"

# Read as raw text and relax strict pins (idempotent)
$content = Get-Content $RequirementsFile -Raw -ErrorAction Stop
$content = $content -replace '(?m)^\s*gradio_client==1\.13\.1\s*$', 'gradio_client>=1.13.1,<2.0'
$content = $content -replace '(?m)^\s*fastapi==0\.116\.2\s*$', 'fastapi>=0.116.2,<1.0'
$content = $content -replace '(?m)^\s*altair==4\.2\.2\s*$', 'altair>=4.2.2,<5.0'
Set-Content -Path $RequirementsFile -Value $content -Force
Write-Host "Relaxed pins written to $RequirementsFile"

Write-Host "`nShowing lines for gradio_client, fastapi, altair:"
Get-Content $RequirementsFile | Where-Object { $_ -match '^(gradio_client|fastapi|altair)' } | ForEach-Object { Write-Host "`t$_" }

# Create a test requirements file that removes any git+ lines and diffusers @ lines
Get-Content $RequirementsFile | Where-Object { $_ -notmatch '(^diffusers\s*@)|git\+|^\s*-\s*e\s*git\+|^\s*git\+|kohya-ss|sd-scripts' } | Set-Content $TestRequirements
Write-Host "`nTest requirements written to: $TestRequirements (git-based lines removed)"

# Verify venv python
if (-not (Test-Path $VenvPython)) {
    Write-Warning "Venv python not found at $VenvPython. Falling back to 'python' from PATH."
    $VenvPython = "python"
}

# Run pip install -vvv against the test requirements, capture output
Write-Host "`nRunning pip install -vvv against $TestRequirements ..."
& "$VenvPython" -m pip install -r "$TestRequirements" -vvv 2>&1 | Tee-Object -FilePath $VerboseOutput

# Print the tail for easy copy/paste
$lastLines = Get-Content $VerboseOutput -ErrorAction SilentlyContinue | Select-Object -Last $TailLines
Write-Host "`n--- Last $TailLines lines of $VerboseOutput ---`n"
$lastLines | ForEach-Object { Write-Host $_ }

if ($LASTEXITCODE -ne $null) {
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nPip install finished successfully."
        exit 0
    } else {
        Write-Warning "`nPip install exited with code $LASTEXITCODE."
        exit $LASTEXITCODE
    }
} else {
    Write-Host "`nCould not determine pip exit code; inspect $VerboseOutput."
}