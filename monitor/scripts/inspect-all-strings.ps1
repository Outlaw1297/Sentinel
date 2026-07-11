$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$asm = [ConsumerLib.Managers.ConsumerManager].Assembly

function All-Strings($method) {
    $body = $method.GetMethodBody()
    if (-not $body) { return @() }
    $out = @()
    $il = $body.GetILAsByteArray()
    for ($i = 0; $i -lt $il.Length; $i++) {
        if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
            $token = [BitConverter]::ToInt32($il, $i + 1)
            try {
                $s = $method.Module.ResolveString($token)
                if ($s) { $out += $s }
            } catch {}
        }
    }
    return $out
}

foreach ($t in $asm.GetTypes()) {
    if ($t.FullName -notmatch 'ConsumerManager') { continue }
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static)) {
        $strings = All-Strings $m
        if ($strings.Count -gt 0) {
            Write-Output "=== $($t.Name).$($m.Name) ==="
            $strings | Sort-Object -Unique
        }
    }
}
