$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"
Add-Type -Path "$gnbots\Newtonsoft.Json.dll"

$type = [ConsumerLib.Managers.ConsumerManager]
Write-Output "=== ConsumerManager all public methods ==="
foreach ($m in $type.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::DeclaredOnly)) {
    $params = ($m.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ", "
    Write-Output "$($m.Name)($params) -> $($m.ReturnType.Name)"
}

Write-Output "`n=== Searching CreateWebServer related types ==="
$asm = [ConsumerLib.Managers.ConsumerManager].Assembly
foreach ($t in $asm.GetTypes()) {
    if ($t.FullName -match 'Consumer|WebServer|WebApi') {
        Write-Output $t.FullName
    }
}
