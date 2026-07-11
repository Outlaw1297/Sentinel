$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$method = [ConsumerLib.Managers.ConsumerManager].GetMethod(
    "CreateServerAsync",
    [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance
)

Write-Output "=== CreateServerAsync disassembly (ldstr only) ==="
$body = $method.GetMethodBody()
$il = $body.GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    $op = $il[$i]
    if ($op -eq 0x72 -and ($i + 4) -lt $il.Length) {
        $token = [BitConverter]::ToInt32($il, $i + 1)
        try {
            $s = $method.Module.ResolveString($token)
            if ($s) { Write-Output "  ldstr: $s" }
        } catch {}
    }
}

Write-Output "`n=== PlayCommand disassembly ==="
$play = [ConsumerLib.Managers.ConsumerManager].GetMethod("PlayCommand")
$il = $play.GetMethodBody().GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
        $token = [BitConverter]::ToInt32($il, $i + 1)
        try {
            $s = $play.Module.ResolveString($token)
            if ($s) { Write-Output "  ldstr: $s" }
        } catch {}
    }
}

Write-Output "`n=== StopCommand disassembly ==="
$stop = [ConsumerLib.Managers.ConsumerManager].GetMethod("StopCommand")
$il = $stop.GetMethodBody().GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
        $token = [BitConverter]::ToInt32($il, $i + 1)
        try {
            $s = $stop.Module.ResolveString($token)
            if ($s) { Write-Output "  ldstr: $s" }
        } catch {}
    }
}

Write-Output "`n=== PostRunCode disassembly ==="
$post = [ConsumerLib.Managers.SessionController].GetMethod("PostRunCode")
$il = $post.GetMethodBody().GetILAsByteArray()
for ($i = 0; $i -lt $il.Length; $i++) {
    if ($il[$i] -eq 0x72 -and ($i + 4) -lt $il.Length) {
        $token = [BitConverter]::ToInt32($il, $i + 1)
        try {
            $s = $post.Module.ResolveString($token)
            if ($s) { Write-Output "  ldstr: $s" }
        } catch {}
    }
}
