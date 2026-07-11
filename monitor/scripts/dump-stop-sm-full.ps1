$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\EmbedIO.dll"
Add-Type -Path "$gn\Swan.Lite.dll"
Add-Type -Path "$gn\ConsumerLib.dll"
$asm = [ConsumerLib.Managers.ConsumerManager].Assembly
$t = $asm.GetTypes() | Where-Object { $_.Name -eq '<StopCommand>d__27' } | Select-Object -First 1
$m = $t.GetMethod('MoveNext')
$il = $m.GetMethodBody().GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
        $tok = [BitConverter]::ToInt32($il, $i + 1)
        try { $s = $m.Module.ResolveString($tok); if ($s) { Write-Output "STR: $s" } } catch {}
    }
    if ($il[$i] -in 0x28, 0x6F, 0x73, 0x7B, 0x7E) {
        if (($i + 4) -lt $il.Length) {
            $tok = [BitConverter]::ToInt32($il, $i + 1)
            try {
                $c = $m.Module.ResolveMethod($tok)
                if ($c) { Write-Output "CALL: $c" }
            } catch {}
            try {
                $fld = $m.Module.ResolveField($tok)
                if ($fld) { Write-Output "FIELD: $fld" }
            } catch {}
        }
    }
}
