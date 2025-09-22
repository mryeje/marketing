<#
PowerShell test script for POST /process

Usage:
.\test-process.ps1
.\test-process.ps1 -ServerUrl "http://127.0.0.1:5000" -NgrokUrl "https://abcd1234.ngrok-free.app"
#>

param(
    [string]$ServerUrl = "http://127.0.0.1:5000",
    [string]$NgrokUrl = "",
    [string]$PayloadPath = ".\payload.json",
    [string]$Src = "https://example.com/somevideo.mp4",
    [string]$LocalResponseFile = ".\response_local.json",
    [string]$NgrokResponseFile = ".\response_ngrok.json"
)

function Build-Payload {
    param($src)
    return @{
        recipe = @{
            src = $src
            clips = @(
                @{ id = 'c1'; start = '0'; end = '3'; label = 'test' }
            )
        }
    }
}

function Save-Payload {
    param($payload, $path)
    $json = $payload | ConvertTo-Json -Depth 10
    # Save UTF-8 without BOM by writing bytes
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $fullPath = (Resolve-Path -LiteralPath $path -ErrorAction SilentlyContinue)
    if ($null -ne $fullPath) {
        $outPath = $fullPath.ProviderPath
    } else {
        $outPath = Join-Path (Get-Location) $path
    }
    [System.IO.File]::WriteAllBytes($outPath, $bytes)
    Write-Host "Saved payload to: $outPath"
    return $outPath
}

function Post-Json {
    param($url, $payloadPath, $outFile)
    Write-Host "POST -> $url"
    $status = "Unknown"
    $body = ""
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Post -ContentType 'application/json' -InFile $payloadPath -ErrorAction Stop
        $status = $resp.StatusCode
        $body = $resp.Content
    } catch {
        $ex = $_.Exception
        if ($ex.Response -ne $null) {
            try {
                $stream = $ex.Response.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream)
                $body = $reader.ReadToEnd()
                try { $status = $ex.Response.StatusCode } catch { $status = 'Error' }
            } catch {
                $body = $ex.Message
                $status = 'Error'
            }
        } else {
            $body = $ex.Message
            $status = 'Error'
        }
    }

    if ($null -eq $body) { $body = "" }

    try {
        $body | Out-File -FilePath $outFile -Encoding utf8 -Force
        Write-Host "Saved response to: $outFile"
    } catch {
        # Use format operator to avoid parsing issues with embedded colons
        Write-Host ("Failed to save response to: {0} - {1}" -f $outFile, $_.Exception.Message)
    }

    # Try to pretty-print JSON summary
    try {
        $parsed = $body | ConvertFrom-Json -ErrorAction Stop
        $summary = $parsed | ConvertTo-Json -Depth 6
        Write-Host "HTTP Status:" $status
        $out = $summary
        if ($out.Length -gt 4000) { $out = $out.Substring(0,4000) + "...(truncated)" }
        Write-Host "Response (pretty JSON, truncated to 4000 chars):"
        Write-Host $out
    } catch {
        Write-Host "HTTP Status:" $status
        $first = $body
        if ($first.Length -gt 800) { $first = $first.Substring(0,800) + "...(truncated)" }
        Write-Host "Response (text, truncated):"
        Write-Host $first
    }
}

# Main
try {
    $payload = Build-Payload -src $Src
    $savedPath = Save-Payload -payload $payload -path $PayloadPath
} catch {
    Write-Host "Failed to build/save payload: $($_.Exception.Message)"
    exit 1
}

# Post to local server — ensure concatenation is evaluated before passing to -url
$localUrl = "$($ServerUrl.TrimEnd('/'))/process"
Post-Json -url $localUrl -payloadPath $savedPath -outFile $LocalResponseFile

# Post to ngrok if provided
if ($NgrokUrl -and $NgrokUrl.Trim() -ne "") {
    $ngrokFull = "$($NgrokUrl.TrimEnd('/'))/process"
    Post-Json -url $ngrokFull -payloadPath $savedPath -outFile $NgrokResponseFile
} else {
    Write-Host "Ngrok URL not provided; skipping."
}

Write-Host "Done."