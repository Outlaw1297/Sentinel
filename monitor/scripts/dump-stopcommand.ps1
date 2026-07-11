$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\EmbedIO.dll"
Add-Type -Path "$gn\Swan.Lite.dll"
Add-Type -Path "$gn\ConsumerLib.dll"

$stop = [ConsumerLib.Managers.ConsumerManager].GetMethod("StopCommand")
Write-Output "=== StopCommand signature ==="
Write-Output $stop
$il = $stop.GetMethodBody().GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
        $token = [BitConverter]::ToInt32($il, $i + 1)
        try { $s = $stop.Module.ResolveString($token); if ($s) { Write-Output "STR: $s" } } catch {}
    }
    if ($il[$i] -in 0x28, 0x6F) {
        if (($i + 4) -lt $il.Length) {
            $token = [BitConverter]::ToInt32($il, $i + 1)
            try {
                $called = $stop.Module.ResolveMethod($token)
                if ($called) { Write-Output "CALL: $called" }
            } catch {}
        }
    }
}

Write-Output "`n=== StopCommand state machine full ==="
$t = ([ConsumerLib.Managers.ConsumerManager].Assembly.GetType('ConsumerLib.Managers.ConsumerManager+<StopCommand>d__27'))
$m = $t.GetMethod('MoveNext')
$il = $m.GetMethodBody().GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
        $token = [BitConverter]::ToInt32($il, $i + 1)
        try { $s = $m.Module.ResolveString($token); if ($s) { Write-Output "STR: $s" } } catch {}
    }
    if ($il[$i] -in 0x28, 0x6F, 0x73) {
        if (($i + 4) -lt $il.Length) {
            $token = [BitConverter]::ToInt32($il, $i + 1)
            try {
                $called = $m.Module.ResolveMethod($token)
                if ($called) { Write-Output "CALL: $called" }
            } catch {}
        }
    }
}
