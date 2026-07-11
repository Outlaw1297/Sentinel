$base = "http://127.0.0.1:5508"
$id = "94ff75b9760b441c"

Write-Output "=== Status before ==="
(Invoke-WebRequest -Uri "$base/status" -UseBasicParsing).Content

$tests = @(
  @{ M = "GET"; P = "/sessions/$id" },
  @{ M = "GET"; P = "/sessions/$id/screenshot" },
  @{ M = "GET"; P = "/sessions/$id/exec" },
  @{ M = "POST"; P = "/sessions/$id/exec"; B = "{}" },
  @{ M = "POST"; P = "/sessions/$id/exec"; B = '{"code":"pause"}' },
  @{ M = "GET"; P = "/play?accountId=$id" },
  @{ M = "GET"; P = "/stop?accountId=$id" },
  @{ M = "GET"; P = "/play?id=$id" },
  @{ M = "GET"; P = "/stop?id=$id" }
)

foreach ($t in $tests) {
  try {
    $params = @{
      Uri             = $base + $t.P
      Method          = $t.M
      UseBasicParsing = $true
      TimeoutSec      = 10
    }
    if ($t.B) {
      $params.Body = $t.B
      $params.ContentType = "application/json"
    }
    $r = Invoke-WebRequest @params
    $c = if ($r.Content.Length -gt 200) { $r.Content.Substring(0, 200) + "..." } else { $r.Content }
    Write-Output ("{0} {1} -> {2} len={3} {4}" -f $t.M, $t.P, $r.StatusCode, $r.Content.Length, $c)
  } catch {
    $resp = $_.Exception.Response
    $code = if ($resp) { [int]$resp.StatusCode } else { "ERR" }
    $body = ""
    if ($resp) {
      $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
      $body = $reader.ReadToEnd()
      if ($body.Length -gt 200) { $body = $body.Substring(0, 200) + "..." }
    }
    Write-Output ("{0} {1} -> {2} {3}" -f $t.M, $t.P, $code, $body)
  }
}
