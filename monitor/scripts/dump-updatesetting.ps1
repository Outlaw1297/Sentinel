$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$t = [ConsumerLib.Managers.SettingsController]
foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::DeclaredOnly)) {
    Write-Output "=== $($m.Name) ==="
    foreach ($p in $m.GetParameters()) {
        Write-Output ("  param {0} : {1}" -f $p.Name, $p.ParameterType.FullName)
    }
    foreach ($a in $m.GetCustomAttributes($false)) {
        Write-Output ("  attr {0}" -f $a)
    }
    $body = $m.GetMethodBody()
    if (-not $body) { continue }
    $il = $body.GetILAsByteArray()
    for ($i = 0; $i -lt $il.Length; $i++) {
        if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
            $token = [BitConverter]::ToInt32($il, $i + 1)
            try {
                $s = $m.Module.ResolveString($token)
                if ($s) { Write-Output "  str: $s" }
            } catch {}
        }
        if ($il[$i] -eq 0x28 -or $il[$i] -eq 0x6F) {
            if (($i + 4) -lt $il.Length) {
                $token = [BitConverter]::ToInt32($il, $i + 1)
                try {
                    $called = $m.Module.ResolveMethod($token)
                    if ($called) {
                        Write-Output ("  call: {0}.{1}" -f $called.DeclaringType.FullName, $called.Name)
                    }
                } catch {}
            }
        }
    }
}

$typeName = 'ConsumerLib.Managers.SettingsController+<UpdateSetting>d__2'
$asyncType = ([ConsumerLib.Managers.ConsumerManager].Assembly.GetType($typeName))
if ($asyncType) {
    Write-Output "=== $typeName ==="
    foreach ($m in $asyncType.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance)) {
        if ($m.Name -ne 'MoveNext') { continue }
        $body = $m.GetMethodBody()
        if (-not $body) { continue }
        $il = $body.GetILAsByteArray()
        for ($i = 0; $i -lt $il.Length; $i++) {
            if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
                $token = [BitConverter]::ToInt32($il, $i + 1)
                try {
                    $s = $m.Module.ResolveString($token)
                    if ($s) { Write-Output "  str: $s" }
                } catch {}
            }
            if (($il[$i] -eq 0x28 -or $il[$i] -eq 0x6F) -and ($i + 4) -lt $il.Length) {
                $token = [BitConverter]::ToInt32($il, $i + 1)
                try {
                    $called = $m.Module.ResolveMethod($token)
                    if ($called) {
                        Write-Output ("  call: {0}.{1}" -f $called.DeclaringType.FullName, $called.Name)
                    }
                } catch {}
            }
        }
    }
}
