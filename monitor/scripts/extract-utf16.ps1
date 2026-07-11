$ErrorActionPreference = "Stop"
$path = "v:\Dropbox\Emulation\gnbot\GnBots\ConsumerLib.dll"
$bytes = [IO.File]::ReadAllBytes($path)
$hits = New-Object System.Collections.Generic.HashSet[string]

# UTF-16LE strings
for ($i = 0; $i -lt ($bytes.Length - 3); $i += 2) {
    $sb = New-Object System.Text.StringBuilder
    $j = $i
    while ($j -lt ($bytes.Length - 1)) {
        $ch = [BitConverter]::ToUInt16($bytes, $j)
        if ($ch -ge 32 -and $ch -le 126) {
            [void]$sb.Append([char]$ch)
            $j += 2
        } else { break }
    }
    if ($sb.Length -ge 3) {
        $s = $sb.ToString()
        if ($s -match '^/|play|stop|pause|restart|exec|screenshot|emulator|command|WithAction|WebApi|sessions|settings|status') {
            [void]$hits.Add($s)
        }
    }
}

$hits | Sort-Object
