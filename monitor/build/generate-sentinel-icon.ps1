# Generate a simple multi-size sentinel.ico for EXEs and the Inno installer.

$ErrorActionPreference = "Stop"
$BuildDir = $PSScriptRoot
$IconPath = Join-Path $BuildDir "sentinel.ico"

Add-Type -AssemblyName System.Drawing

function New-SentinelBitmap([int]$Size) {
    $bmp = New-Object System.Drawing.Bitmap $Size, $Size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::FromArgb(15, 23, 42))
    $margin = [Math]::Max(1, [int]($Size * 0.12))
    $rect = New-Object System.Drawing.Rectangle $margin, $margin, ($Size - 2 * $margin), ($Size - 2 * $margin)
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(56, 189, 248))
    $g.FillEllipse($brush, $rect)
    $inner = New-Object System.Drawing.Rectangle ($margin * 2), ($margin * 2), ($Size - 4 * $margin), ($Size - 4 * $margin)
    $innerBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(15, 23, 42))
    $g.FillEllipse($innerBrush, $inner)
    $fontSize = [Math]::Max(6, [int]($Size * 0.42))
    $font = New-Object System.Drawing.Font("Segoe UI", [single]$fontSize, [System.Drawing.FontStyle]::Bold)
    $textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(56, 189, 248))
    $format = New-Object System.Drawing.StringFormat
    $format.Alignment = [System.Drawing.StringAlignment]::Center
    $format.LineAlignment = [System.Drawing.StringAlignment]::Center
    $g.DrawString("S", $font, $textBrush, (New-Object System.Drawing.RectangleF 0, 0, $Size, $Size), $format)
    $g.Dispose()
    return $bmp
}

$sizes = @(16, 32, 48, 256)
$bitmaps = $sizes | ForEach-Object { New-SentinelBitmap $_ }

try {
    $stream = [System.IO.File]::Create($IconPath)
    try {
        $icon = [System.Drawing.Icon]::FromHandle($bitmaps[-1].GetHicon())
        $icon.Save($stream)
    } finally {
        $stream.Close()
        $icon.Dispose()
    }
} finally {
    foreach ($bmp in $bitmaps) { $bmp.Dispose() }
}

Write-Host "Wrote $IconPath"
