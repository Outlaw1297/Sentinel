$ErrorActionPreference = "Stop"
$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gnbots\EmbedIO.dll"
Add-Type -Path "$gnbots\Swan.Lite.dll"
Add-Type -Path "$gnbots\ConsumerLib.dll"

$types = @(
    [ConsumerLib.Managers.ConsumerManager],
    [ConsumerLib.Managers.SessionController],
    [ConsumerLib.Managers.SettingsController]
)

foreach ($t in $types) {
    Write-Output "=== $($t.Name) ==="
    $methods = $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::DeclaredOnly)
    foreach ($m in $methods) {
        $routeAttrs = $m.GetCustomAttributes([EmbedIO.Routing.RouteAttribute], $false)
        if ($routeAttrs.Count -gt 0) {
            foreach ($a in $routeAttrs) {
                Write-Output ("  {0} {1} Verb={2} Route={3}" -f $m.Name, $m.ReturnType.Name, $a.Verb, $a.Route)
            }
        } else {
            Write-Output ("  {0} (no route)" -f $m.Name)
        }
    }
}
