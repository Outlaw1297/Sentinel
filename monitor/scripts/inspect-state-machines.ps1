$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

function Dump-MethodRefs($typeName) {
    $t = ([ConsumerLib.Managers.ConsumerManager].Assembly.GetType($typeName))
    if (-not $t) { Write-Output "Type not found: $typeName"; return }
    Write-Output "=== $typeName ==="
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static)) {
        if ($m.Name -notmatch 'MoveNext|SetStateMachine|get_|set_') { continue }
        if ($m.Name -ne 'MoveNext') { continue }
        $body = $m.GetMethodBody()
        if (-not $body) { continue }
        foreach ($tok in $body.LocalVariables) { }
        $il = $body.GetILAsByteArray()
        for ($i = 0; $i -lt $il.Length; $i++) {
            if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
                $token = [BitConverter]::ToInt32($il, $i + 1)
                try {
                    $s = $m.Module.ResolveString($token)
                    if ($s) { Write-Output "  str: $s" }
                } catch {}
            }
            if ($il[$i] -eq 0x28 -or $il[$i] -eq 0x6F) { # call / callvirt
                if (($i + 4) -lt $il.Length) {
                    $token = [BitConverter]::ToInt32($il, $i + 1)
                    try {
                        $called = $m.Module.ResolveMethod($token)
                        if ($called) {
                            $sig = "$($called.DeclaringType.Name).$($called.Name)"
                            if ($sig -match 'Query|Request|Route|Play|Stop|Pause|Read|Json|License|Command|Exec|RunCode|GetData|Send') {
                                Write-Output "  call: $sig"
                            }
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
    'ConsumerLib.Managers.ConsumerManager+<>c__DisplayClass15_0+<<CreateServerAsync>b__0>d'
)) {
    Dump-MethodRefs $name
}
