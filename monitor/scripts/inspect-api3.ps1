$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$method = [ConsumerLib.Managers.ConsumerManager].GetMethod("CreateServerAsync", [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance)
if (-not $method) {
    $method = [ConsumerLib.Managers.ConsumerManager].GetMethods([Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance) | Where-Object { $_.Name -eq "CreateServerAsync" }
}
Write-Output "Method: $($method.Name)"

# Dump IL and look for ldstr (string literals)
$body = $method.GetMethodBody()
$il = $body.GetILAsByteArray()
$strings = @()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -eq 0x72) { # ldstr token follows as int32
        $token = [BitConverter]::ToInt32($il, $i + 1)
        try {
            $s = $method.Module.ResolveString($token)
            if ($s) { $strings += $s }
        } catch {}
        $i += 4
    }
}
Write-Output "=== String literals in CreateServerAsync ==="
$strings | Sort-Object -Unique

# Also check PlayCommand, StopCommand bodies
foreach ($name in @("PlayCommand", "StopCommand", "StopAll", "StopEmulators", "RestartServerAsync")) {
    $m = [ConsumerLib.Managers.ConsumerManager].GetMethod($name, [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance)
    if (-not $m) { continue }
    Write-Output "`n=== $name strings ==="
    $body = $m.GetMethodBody()
    if (-not $body) { continue }
    $il = $body.GetILAsByteArray()
    $localStrings = @()
    for ($i = 0; $i -lt $il.Length; $i++) {
        if ($il[$i] -eq 0x72) {
            $token = [BitConverter]::ToInt32($il, $i + 1)
            try {
                $s = $m.Module.ResolveString($token)
                if ($s) { $localStrings += $s }
            } catch {}
            $i += 4
        }
    }
    $localStrings | Sort-Object -Unique
}
