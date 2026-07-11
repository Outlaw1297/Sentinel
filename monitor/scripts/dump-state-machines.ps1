$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$out = "v:\Dropbox\Emulation\gnbot\monitor\scripts\state-machine-dump.txt"
Remove-Item $out -ErrorAction SilentlyContinue

function Dump-MethodRefs($typeName) {
    $t = ([ConsumerLib.Managers.ConsumerManager].Assembly.GetType($typeName))
    if (-not $t) { return }
    Add-Content $out "=== $typeName ==="
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static)) {
        if ($m.Name -ne 'MoveNext') { continue }
        $body = $m.GetMethodBody()
        if (-not $body) { continue }
        $il = $body.GetILAsByteArray()
        for ($i = 0; $i -lt $il.Length; $i++) {
            if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
                $token = [BitConverter]::ToInt32($il, $i + 1)
                try {
                    $s = $m.Module.ResolveString($token)
                    if ($s) { Add-Content $out "  str: $s" }
                } catch {}
            }
            if ($il[$i] -eq 0x28 -or $il[$i] -eq 0x6F) {
                if (($i + 4) -lt $il.Length) {
                    $token = [BitConverter]::ToInt32($il, $i + 1)
                    try {
                        $called = $m.Module.ResolveMethod($token)
                        if ($called) {
                            Add-Content $out ("  call: {0}.{1}" -f $called.DeclaringType.FullName, $called.Name)
                        }
                    } catch {}
                }
            }
        }
    }
}

foreach ($name in @(
    'ConsumerLib.Managers.ConsumerManager+<PlayCommand>d__26',
    'ConsumerLib.Managers.ConsumerManager+<StopCommand>d__27',
    'ConsumerLib.Managers.ConsumerManager+<StopAll>d__25',
    'ConsumerLib.Managers.ConsumerManager+<StopEmulators>d__28',
    'ConsumerLib.Managers.SessionController+<PostRunCode>d__3',
    'ConsumerLib.Managers.SessionController+<GetRunCode>d__4',
    'ConsumerLib.Managers.SettingsController+<UpdateSetting>d__2'
)) {
    Dump-MethodRefs $name
}

Write-Output "Wrote $out"
