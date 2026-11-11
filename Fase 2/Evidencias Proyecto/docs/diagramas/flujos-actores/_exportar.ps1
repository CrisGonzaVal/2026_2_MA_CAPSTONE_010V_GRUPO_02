# Exporta los HTML de flujos-actores a PNG 2x con Edge headless.
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File .\_exportar.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$tmp = "C:\Users\ricar\AppData\Local\Temp\opencode\flujos-export"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$files = Get-ChildItem (Join-Path $root "*.html") | Sort-Object Name
foreach ($file in $files) {
    $slug = $file.BaseName
    $tmpHtml = Join-Path $tmp "$slug.html"
    $tmpPng = Join-Path $tmp "$slug.png"
    Copy-Item $file.FullName $tmpHtml -Force
    if (Test-Path $tmpPng) { Remove-Item $tmpPng -Force }

    $profile = Join-Path $tmp "profile-$slug"
    $uri = "file:///" + ($tmpHtml -replace '\\', '/')
    & $edge --headless=new --disable-gpu --hide-scrollbars --no-first-run `
        --disable-extensions --disable-background-networking `
        --user-data-dir="$profile" --force-device-scale-factor=2 `
        --window-size=1200,560 --virtual-time-budget=8000 `
        --screenshot="$tmpPng" $uri 2>$null

    # Edge devuelve el control antes de terminar de escribir el archivo.
    $ok = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Path $tmpPng) {
            $s1 = (Get-Item $tmpPng).Length
            Start-Sleep -Milliseconds 300
            $s2 = (Get-Item $tmpPng).Length
            if ($s1 -gt 0 -and $s1 -eq $s2) { $ok = $true; break }
        }
    }
    if (-not $ok) {
        Write-Output "FALLO $slug (sin PNG)"
        continue
    }
    Copy-Item $tmpPng (Join-Path $root "$slug.png") -Force
    Add-Type -AssemblyName System.Drawing
    $img = [System.Drawing.Image]::FromFile($tmpPng)
    Write-Output "OK $slug.png $($img.Width)x$($img.Height)"
    $img.Dispose()
}
