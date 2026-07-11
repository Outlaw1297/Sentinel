$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

function Dump-MethodIL($typeName, $methodName) {
    $t = [ConsumerLib.Managers.ConsumerManager].Assembly.GetType($typeName)
    if (-not $t) { Write-Output "Type not found: $typeName"; return }
    $m = $t.GetMethod($methodName, [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::DeclaredOnly)
    if (-not $m) {
        $m = $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance) |
            Where-Object { $_.Name -eq $methodName } | Select-Object -First 1
    }
    if (-not $m) { Write-Output "Method not found: $typeName.$methodName"; return }
    Write-Output "=== $($t.FullName).$($m.Name) ==="
    $body = $m.GetMethodBody()
    if (-not $body) { return }
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
                    if ($called -and $called.Name -match 'Pause|Resume|Start|Stop|RunCode|code|Toggle|Play') {
                        Write-Output ("  call: {0}.{1}" -f $called.DeclaringType.Name, $called.Name)
                    }
                } catch {}
            }
        }
    }
}

foreach ($pair in @(
        @('ConsumerLib.Managers.SessionController', 'PostRunCode'),
        @('ConsumerLib.Managers.SessionController', 'GetRunCode'),
        @('ConsumerLib.Managers.ConsumerManager', 'StartCommand'),
        @('ConsumerLib.Managers.ConsumerManager', 'StopCommand'),
        @('ConsumerLib.Managers.ConsumerManager', 'PlayCommand'),
        @('ConsumerLib.Managers.ConsumerManager', 'PauseCommand')
    )) {
    Dump-MethodIL $pair[0] $pair[1]
    Write-Output ""
}
