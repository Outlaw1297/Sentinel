$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\EmbedIO.dll"
Add-Type -Path "$gn\Swan.Lite.dll"
Add-Type -Path "$gn\ConsumerLib.dll"
$asm = [ConsumerLib.Managers.ConsumerManager].Assembly

Write-Output "=== Methods named exactly Pause or Resume (any type) ==="
foreach ($t in $asm.GetTypes()) {
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static)) {
        if ($m.Name -in @('Pause', 'Resume', 'PauseAsync', 'ResumeAsync', 'TogglePause', 'PauseBot')) {
            $params = ($m.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ", "
            Write-Output "$($t.FullName).$($m.Name)($params)"
        }
    }
}

Write-Output "`n=== PlayCommand state machine ==="
$t = $asm.GetTypes() | Where-Object { $_.Name -eq '<PlayCommand>d__26' } | Select-Object -First 1
$m = $t.GetMethod('MoveNext', [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance)
$il = $m.GetMethodBody().GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -in 0x28, 0x6F) {
        if (($i + 4) -lt $il.Length) {
            $tok = [BitConverter]::ToInt32($il, $i + 1)
            try { $c = $m.Module.ResolveMethod($tok); if ($c) { Write-Output "CALL: $c" } } catch {}
        }
    }
}
