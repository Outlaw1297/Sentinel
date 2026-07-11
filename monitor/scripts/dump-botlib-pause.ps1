$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\BotLib.dll"
Add-Type -Path "$gn\WrapperLib.dll" -ErrorAction SilentlyContinue
$bot = [System.Reflection.Assembly]::LoadFrom("$gn\BotLib.dll")
Write-Output "=== BotLib Pause-related ==="
$bot.GetTypes() | ForEach-Object {
    $t = $_
    $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static) |
        Where-Object { $_.Name -match 'Pause|Resume' } |
        ForEach-Object {
            $params = ($_.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ", "
            "{0}.{1}({2})" -f $t.FullName, $_.Name, $params
        }
} | Sort-Object -Unique

$wrap = [System.Reflection.Assembly]::LoadFrom("$gn\WrapperLib.dll")
Write-Output "`n=== WrapperLib Pause-related ==="
$wrap.GetTypes() | ForEach-Object {
    $t = $_
    $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static) |
        Where-Object { $_.Name -match 'Pause|Resume' } |
        ForEach-Object {
            $params = ($_.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ", "
            "{0}.{1}({2})" -f $t.FullName, $_.Name, $params
        }
} | Sort-Object -Unique
