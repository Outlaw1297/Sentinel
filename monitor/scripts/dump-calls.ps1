$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

function Dump-Calls($typeName) {
    $t = ([ConsumerLib.Managers.ConsumerManager].Assembly.GetType($typeName))
    if (-not $t) { return }
    Write-Output "=== $typeName ==="
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance)) {
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
            if ($il[$i] -eq 0x28 -or $il[$i] -eq 0x6F) {
                if (($i + 4) -lt $il.Length) {
                    $token = [BitConverter]::ToInt32($il, $i + 1)
                    try {
                        $called = $m.Module.ResolveMethod($token)
                        if ($called) {
                            Write-Output ("  call: {0}.{1}" -f $called.DeclaringType.Name, $called.Name)
                        }
                    } catch {}
                }
            }
        }
    }
}

Dump-Calls 'ConsumerLib.Managers.ConsumerManager+<PlayCommand>d__26'
Dump-Calls 'ConsumerLib.Managers.ConsumerManager+<StopCommand>d__27'
Dump-Calls 'ConsumerLib.Managers.ConsumerManager+<StopAll>d__25'
Dump-Calls 'ConsumerLib.Managers.ConsumerManager+<>c__DisplayClass15_0+<<CreateServerAsync>b__0>d'
Dump-Calls 'ConsumerLib.Managers.ConsumerManager+<CreateServerAsync>d__15'
