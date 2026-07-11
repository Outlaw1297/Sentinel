$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

function Dump-Strings($method) {
    Write-Output "=== $($method.DeclaringType.Name).$($method.Name) ==="
    $body = $method.GetMethodBody()
    if (-not $body) { return }
    $il = $body.GetILAsByteArray()
    for ($i = 0; $i -lt $il.Length; $i++) {
        if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
            $token = [BitConverter]::ToInt32($il, $i + 1)
            try {
                $s = $method.Module.ResolveString($token)
                if ($s) { Write-Output "  $s" }
            } catch {}
        }
    }
}

$asm = [ConsumerLib.Managers.ConsumerManager].Assembly
foreach ($t in $asm.GetTypes()) {
    if ($t.FullName -notmatch 'ConsumerManager') { continue }
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static)) {
        if ($m.Name -match 'CreateServer|b__0|WithWebApi|WithModule|PlayCommand|StopCommand|StopAll|StopEmulators') {
            Dump-Strings $m
        }
    }
}
