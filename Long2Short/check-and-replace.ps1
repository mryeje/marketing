<#
check-and-replace.ps1

Usage:
powershell -ExecutionPolicy Bypass -File .\check-and-replace.ps1
(or run in an existing PowerShell session)
.\check-and-replace.ps1 -ForceKill

What it does:
- Backups the requirements file
- Applies a safe regex replacement to relax gradio pin
- Writes to a temp file and tries to replace the original
- If the file is locked, it reports processes whose CommandLine contains the filename
- Optionally force-kills those processes and retries

Be careful with -ForceKill; it will terminate processes found to reference the filename.
#>

param(
    [string]$RequirementsFile = ".\requirements-gradio-4-range.txt",
    [switch]$ForceKill,
    [int]$MaxAttempts = 5,
    [int]$SleepSeconds = 2
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $RequirementsFile)) {
    Write-Error "Requirements file not found: $RequirementsFile"
    exit 1
}

$backup = "$RequirementsFile.bak"
Copy-Item -Path $RequirementsFile -Destination $backup -Force
Write-Host "Backup created: $backup"

# Read and apply replacement
try {
    $content = Get-Content $RequirementsFile -Raw
} catch {
    Write-Warning "Could not read file. Error: $_"
    exit 1
}

$newContent = $content -replace '(?m)^\s*gradio==\d+\.\d+\.\d+\s*$', 'gradio>=4.44.1,<5.0'
$tmp = "$RequirementsFile.tmp.$([guid]::NewGuid().ToString()).tmp"

Set-Content -Path $tmp -Value $newContent -Force
Write-Host "Wrote replacement to temporary file: $tmp"

$attempt = 0
$replaced = $false
while (($attempt -lt $MaxAttempts) -and (-not $replaced)) {
    $attempt++
    try {
        Move-Item -Path $tmp -Destination $RequirementsFile -Force -ErrorAction Stop
        Write-Host ("Successfully replaced {0} on attempt {1}." -f $RequirementsFile, $attempt)
        $replaced = $true
        break
    } catch {
        Write-Warning ("Attempt {0}: Could not move temp file over the target. File may be locked. Error: {1}" -f $attempt, $_.Exception.Message)
        # Find processes whose CommandLine mentions the filename (best-effort)
        $fullpath = (Get-Item $RequirementsFile).FullName
        $esc = [Regex]::Escape($fullpath)
        $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match $esc) } | Select-Object ProcessId, Name, CommandLine
        if ($procs) {
            Write-Host "Processes that mention the file in their CommandLine (possible lockers):"
            $procs | Format-Table -AutoSize
        } else {
            Write-Host "No processes found whose CommandLine contains the file path. You can also check editors (VSCode/Notepad), Resource Monitor, or Sysinternals Handle."
        }

        if ($ForceKill.IsPresent -and $procs) {
            Write-Warning "ForceKill requested. Stopping the found processes (this will terminate them)."
            foreach ($p in $procs) {
                try {
                    Write-Host ("Stopping process Id {0} ({1})" -f $p.ProcessId, $p.Name)
                    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                    Write-Host ("Stopped {0}." -f $p.ProcessId)
                } catch {
                    Write-Warning ("Failed to stop process {0}: {1}" -f $p.ProcessId, $_.Exception.Message)
                }
            }
        } elseif (-not $procs) {
            Write-Host "No lockers discovered; possibility: antivirus or OS-level lock. Try closing editors, waiting a moment, or reboot."
        } else {
            Write-Host "To proceed you can re-run the script with -ForceKill to terminate the listed processes, or close those programs manually and re-run."
        }

        Start-Sleep -Seconds $SleepSeconds
    }
}

if (-not $replaced) {
    Write-Error "Failed to replace the file after $MaxAttempts attempts. Temp file left at: $tmp. Restore original from $backup if needed."
    exit 2
}

# Show the changed lines for quick verification
Write-Host "`nChanged lines (gradio, fastapi, gradio_client, altair):"
Get-Content $RequirementsFile | Where-Object { $_ -match '^(gradio|fastapi|gradio_client|altair)' } | ForEach-Object { Write-Host "`t$_" }

Write-Host "`nDone."