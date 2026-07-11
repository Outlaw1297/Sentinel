$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$asm = [ConsumerLib.Managers.ConsumerManager].Assembly
foreach ($t in $asm.GetTypes()) {
    if ($t.FullName -notmatch 'ConsumerManager\+<>c__DisplayClass15_0|CreateServerAsync') { continue }
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static)) {
        $body = $m.GetMethodBody()
        if (-not $body) { continue }
        $il = $body.GetILAsByteArray()
        for ($i = 0; $i -lt $il.Length; $i++) {
            if ($il[$i] -eq 0x28 -or $il[$i] -eq 0x6F) {
                if (($i + 4) -lt $il.Length) {
                    $token = [BitConverter]::ToInt32($il, $i + 1)
                    try {
                        $called = $m.Module.ResolveMethod($token)
                        if ($called -and ($called.Name -match 'WithAction|WithWebApi|WithModule|Map|Register|Handle')) {
                            Write-Output "$($t.Name).$($m.Name) -> $($called.DeclaringType.Name).$($called.Name)"
                        }
                    } catch {}
                }
            }
            if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
                $token = [BitConverter]::ToInt32($il, $i + 1)
                try {
                    $s = $m.Module.ResolveString($token)
                    if ($s -and ($s -match '^/|play|stop|pause|HttpVerbs|GET|POST')) {
                        Write-Output "$($t.Name).$($m.Name) str: $s"
                    }
                } catch {}
            }
        }
    }
}

$cm = [ConsumerLib.Managers.ConsumerManager]
foreach ($name in @('PlayCommand','StopCommand','StopAll','StopEmulators')) {
    $m = $cm.GetMethod($name)
    Write-Output "=== $name params ==="
    foreach ($p in $m.GetParameters()) { Write-Output "  $($p.ParameterType.Name) $($p.Name)" }
}
