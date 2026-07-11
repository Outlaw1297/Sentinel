$gnbots = "v:\Dropbox\Emulation\gnbot\GnBots"
$files = Get-ChildItem "$gnbots\*.dll", "$gnbots\GnBots.exe"
$patterns = @("^/play$", "^/stop$", "^/stopall$", "^/pause$", "^/restart$", "stopall", "PlayCommand", "WithAction", "WithModule")

foreach ($file in $files) {
  $bytes = [IO.File]::ReadAllBytes($file.FullName)
  $sb = New-Object Text.StringBuilder
  $hits = New-Object System.Collections.Generic.HashSet[string]
  foreach ($b in $bytes) {
    if ($b -ge 32 -and $b -le 126) {
      [void]$sb.Append([char]$b)
    } else {
      if ($sb.Length -ge 3) {
        $s = $sb.ToString()
        foreach ($p in $patterns) {
          if ($s -match $p) { [void]$hits.Add($s) }
        }
      }
      $sb.Clear() | Out-Null
    }
  }
  if ($hits.Count -gt 0) {
    Write-Output "=== $($file.Name) ==="
    $hits | Sort-Object
  }
}
