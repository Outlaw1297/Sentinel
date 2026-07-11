$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\EmbedIO.dll"
Add-Type -Path "$gn\Swan.Lite.dll"
Add-Type -Path "$gn\ConsumerLib.dll"

$asm = [ConsumerLib.Managers.ConsumerManager].Assembly
Write-Output "=== Types with Pause/Start/Stop/Run in ConsumerLib ==="
$asm.GetTypes() | ForEach-Object {
    $t = $_
    $methods = $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static) |
        Where-Object { $_.DeclaringType -eq $t -and $_.Name -match 'Pause|Resume|Start|Stop|Run' -and $_.Name -notmatch 'get_|set_|add_|remove_' }
    if ($methods) {
        Write-Output "`n$($t.FullName)"
        foreach ($m in $methods) {
            $params = ($m.GetParameters() | ForEach-Object { "$($_.ParameterType.Name) $($_.Name)" }) -join ", "
            Write-Output "  $($m.Name)($params)"
        }
    }
}
