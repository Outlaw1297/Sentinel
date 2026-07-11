$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$asm = [ConsumerLib.Managers.ConsumerManager].Assembly
Write-Output "=== WebApi controllers ==="
foreach ($t in $asm.GetTypes()) {
    if ($t.Namespace -match 'ConsumerLib' -and $t.Name -match 'Controller|Api') {
        Write-Output "`n--- $($t.FullName) ---"
        foreach ($m in $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::DeclaredOnly)) {
            if ($m.IsSpecialName) { continue }
            $params = ($m.GetParameters() | ForEach-Object { "$($_.ParameterType.Name) $($_.Name)" }) -join ", "
            Write-Output "  $($m.Name)($params)"
        }
    }
}
