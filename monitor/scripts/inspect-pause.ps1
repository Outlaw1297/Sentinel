$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\BotLib.dll"
Add-Type -Path "$gn\ConsumerLib.dll"

$botAsm = [System.Reflection.Assembly]::LoadFrom("$gn\BotLib.dll")
$consumerAsm = [System.Reflection.Assembly]::LoadFrom("$gn\ConsumerLib.dll")

Write-Output "=== BotLib types with Pause/Resume ==="
$botAsm.GetTypes() |
    Where-Object { $_.Name -match 'Pause|Resume' } |
    ForEach-Object { $_.FullName }

Write-Output "`n=== BotLib methods named PauseAsync/ResumeAsync/PauseBot ==="
$botAsm.GetTypes() |
    ForEach-Object {
        $t = $_
        $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static) |
            Where-Object { $_.Name -match 'PauseAsync|ResumeAsync|PauseBot|Unpause|Pausing' } |
            ForEach-Object {
                "{0}.{1}({2})" -f $t.FullName, $_.Name, (($_.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ", ")
            }
    }

Write-Output "`n=== ConsumerLib public methods with Pause/Resume ==="
$consumerAsm.GetTypes() |
    ForEach-Object {
        $t = $_
        $t.GetMethods([Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static) |
            Where-Object { $_.Name -match 'Pause|Resume' } |
            ForEach-Object {
                "{0}.{1}({2})" -f $t.Name, $_.Name, (($_.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ", ")
            }
    }
