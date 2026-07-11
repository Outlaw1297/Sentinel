$base = "http://127.0.0.1:5508"
$id = "cba86a6aaeab496f"
$tests = @(
  @{ M = "GET"; P = "/play" },
  @{ M = "GET"; P = "/stop" },
  @{ M = "GET"; P = "/stopall" },
  @{ M = "POST"; P = "/play" },
  @{ M = "POST"; P = "/stop" },
  @{ M = "POST"; P = "/stopall" },
  @{ M = "GET"; P = "/pause" },
  @{ M = "POST"; P = "/pause" },
  @{ M = "GET"; P = "/restart" },
  @{ M = "POST"; P = "/restart" },
  @{ M = "GET"; P = "/stopemulators" },
  @{ M = "POST"; P = "/stopemulators" },
  @{ M = "GET"; P = "/stop/emulators" },
  @{ M = "POST"; P = "/stop/emulators" },
  @{ M = "GET"; P = "/sessions/$id" },
  @{ M = "GET"; P = "/sessions/$id/screenshot" },
  @{ M = "GET"; P = "/sessions/$id/exec" },
  @{ M = "POST"; P = "/sessions/$id/exec"; B = "{}" }
)

foreach ($t in $tests) {
  try {
    $params = @{
      Uri             = $base + $t.P
      Method          = $t.M
      UseBasicParsing = $true
      TimeoutSec      = 5
    }
    if ($t.B) {
      $params.Body = $t.B
      $params.ContentType = "application/json"
    }
    $r = Invoke-WebRequest @params
    $c = if ($r.Content.Length -gt 120) { $r.Content.Substring(0, 120) + "..." } else { $r.Content }
    Write-Output ("{0} {1} -> {2} {3}" -f $t.M, $t.P, $r.StatusCode, $c)
  } catch {
    $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { "ERR" }
    Write-Output ("{0} {1} -> {2}" -f $t.M, $t.P, $code)
  }
}
