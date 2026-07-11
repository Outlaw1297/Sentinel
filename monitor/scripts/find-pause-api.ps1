# Find pause-related API surface in GnBots assemblies.
$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
foreach ($dll in @("ConsumerLib.dll", "BotLib.dll", "WrapperLib.dll", "AppsLib.dll")) {
    $path = Join-Path $gn $dll
    if (-not (Test-Path $path)) { continue }
    Add-Type -Path $path -ErrorAction SilentlyContinue | Out-Null
}

$asm = [System.Reflection.Assembly]::LoadFrom((Join-Path $gn "ConsumerLib.dll"))
Write-Output "=== ConsumerLib methods (Pause/Resume/Start/Toggle) ==="
$asm.GetTypes() | ForEach-Object {
    $t = $_
    $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static) |
        Where-Object { $_.Name -match 'Pause|Resume|Toggle|StartBot|StopBot|Play' -and $_.DeclaringType -eq $t } |
        ForEach-Object {
            $params = ($_.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ", "
            "{0}.{1}({2})" -f $t.FullName, $_.Name, $params
        }
} | Sort-Object -Unique

Write-Output ""
Write-Output "=== StopCommand / PlayCommand callee search ==="
function Get-CalledMethods($typeName) {
    $t = $asm.GetType($typeName)
    if (-not $t) { return }
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance)) {
        if ($m.Name -ne 'MoveNext') { continue }
        $body = $m.GetMethodBody()
        if (-not $body) { continue }
        $il = $body.GetILAsByteArray()
        for ($i = 0; $i -lt $il.Length; $i++) {
            if ($il[$i] -eq 0x28 -or $il[$i] -eq 0x6F) {
                if (($i + 4) -lt $il.Length) {
                    $token = [BitConverter]::ToInt32($il, $i + 1)
                    try {
                        $called = $m.Module.ResolveMethod($token)
                        if ($called) {
                            "{0}.{1}" -f $called.DeclaringType.FullName, $called.Name
                        }
                    } catch {}
                }
            }
        }
    }
}

Get-CalledMethods 'ConsumerLib.Managers.ConsumerManager+<PlayCommand>d__26' | Sort-Object -Unique
Write-Output "---"
Get-CalledMethods 'ConsumerLib.Managers.ConsumerManager+<StopCommand>d__27' | Sort-Object -Unique
