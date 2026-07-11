$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\EmbedIO.dll"
Add-Type -Path "$gn\Swan.Lite.dll"
Add-Type -Path "$gn\ConsumerLib.dll"

function Dump-AllCalls($typeName) {
    $t = ([ConsumerLib.Managers.ConsumerManager].Assembly.GetType($typeName))
    if (-not $t) { Write-Output "missing $typeName"; return }
    Write-Output "=== $typeName ==="
    $m = $t.GetMethods([Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance) |
        Where-Object { $_.Name -eq 'MoveNext' } | Select-Object -First 1
    $il = $m.GetMethodBody().GetILAsByteArray()
    for ($i = 0; $i -lt $il.Length; $i++) {
        if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
            $token = [BitConverter]::ToInt32($il, $i + 1)
            try { $s = $m.Module.ResolveString($token); if ($s) { Write-Output "  STR: $s" } } catch {}
        }
        if ($il[$i] -in 0x28, 0x6F, 0x73) {
            if (($i + 4) -lt $il.Length) {
                $token = [BitConverter]::ToInt32($il, $i + 1)
                try {
                    $called = $m.Module.ResolveMethod($token)
                    if ($called) { Write-Output ("  CALL: {0}" -f $called) }
                } catch {}
            }
        }
    }
}

Dump-AllCalls 'ConsumerLib.Managers.ConsumerManager+<PlayCommand>d__26'
Write-Output ""
Dump-AllCalls 'ConsumerLib.Managers.ConsumerManager+<StopCommand>d__27'
Write-Output ""
Dump-AllCalls 'ConsumerLib.Managers.SessionController+<PostRunCode>d__3'
