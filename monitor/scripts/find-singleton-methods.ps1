$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\EmbedIO.dll"
Add-Type -Path "$gn\Swan.Lite.dll"
Add-Type -Path "$gn\ConsumerLib.dll"
$asm = [ConsumerLib.Managers.ConsumerManager].Assembly

Write-Output "=== Singleton types with parameterless void methods ==="
foreach ($t in $asm.GetTypes()) {
    $inst = $t.GetMethod('get_Instance', [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Static)
    if (-not $inst) { continue }
    $voids = $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance) |
        Where-Object { $_.ReturnType -eq [void] -and $_.GetParameters().Count -eq 0 -and -not $_.IsSpecialName }
    if ($voids) {
        Write-Output "`n$($t.FullName)"
        foreach ($v in $voids) { Write-Output "  $($v.Name)()" }
    }
}

Write-Output "`n=== Singleton types with Void(Boolean) methods ==="
foreach ($t in $asm.GetTypes()) {
    $inst = $t.GetMethod('get_Instance', [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Static)
    if (-not $inst) { continue }
    $methods = $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance) |
        Where-Object { $_.ReturnType -eq [void] -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType -eq [bool] }
    if ($methods) {
        Write-Output "`n$($t.FullName)"
        foreach ($v in $methods) { Write-Output "  $($v.Name)(Boolean)" }
    }
}
