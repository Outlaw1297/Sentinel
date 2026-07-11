$path = "v:\Dropbox\Emulation\gnbot\GnBots\ConsumerLib.dll"
$bytes = [System.IO.File]::ReadAllBytes($path)
$strings = New-Object System.Collections.Generic.HashSet[string]

function Add-AsciiStrings($data) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $data) {
        if ($b -ge 32 -and $b -le 126) {
            [void]$sb.Append([char]$b)
        } else {
            if ($sb.Length -ge 3) { [void]$strings.Add($sb.ToString()) }
            $sb.Clear() | Out-Null
        }
    }
    if ($sb.Length -ge 3) { [void]$strings.Add($sb.ToString()) }
}

Add-AsciiStrings $bytes

$strings | Where-Object {
    $_ -match '^/|play|stop|pause|restart|session|setting|exec|screenshot|emulator|command|WithWebApi|WebApi'
} | Sort-Object
