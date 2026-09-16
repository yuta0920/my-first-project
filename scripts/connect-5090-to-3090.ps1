# 5090 PC を 3090 判定ノードにつなぐ（2026-09-17）。5090 PC の PowerShell で実行する（管理者不要）。
# 役割: 3090 ノードの ollama に到達できるか確認し、必要な 4 モデルが揃っているか見て、
#       JINX_OLLAMA=http://<3090 の IP>:11434 をユーザー環境変数に設定する。最後に小さいモデルで 1 回推論して疎通を確かめる。
# 使い方:
#   .\connect-5090-to-3090.ps1 -NodeIp 192.168.1.23     # 3090 の IP が分かっているとき
#   .\connect-5090-to-3090.ps1                          # IP 省略時は同一サブネットを走査して 11434 が開いている PC を探す
#   .\connect-5090-to-3090.ps1 -NodeIp 192.168.1.23 -SkipTest   # 推論テストを飛ばす
param(
  [string]$NodeIp,
  [switch]$SkipTest
)
$ErrorActionPreference = 'Stop'
$Port = 11434
$Models = 'qwen3-vl:32b', 'qwen3:32b', 'qwen2.5vl:7b', 'deepseek-r1:32b'

function Find-OllamaNode {
  # 自分の /24 を全部 TCP 接続してみて 11434 が開いている PC を返す（200ms タイムアウト、全部並列なので数秒で終わる）
  $my = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' } | Select-Object -First 1
  if (-not $my) { throw "LAN の IPv4 アドレスが見つからない。-NodeIp で 3090 の IP を指定してください。" }
  $prefix = ($my.IPAddress -split '\.')[0..2] -join '.'
  Write-Host "3090 ノードを探索中: $prefix.0/24 のポート $Port ..."
  $clients = @{}
  foreach ($n in 1..254) {
    $ip = "$prefix.$n"
    if ($ip -eq $my.IPAddress) { continue }
    $c = New-Object System.Net.Sockets.TcpClient
    $clients[$ip] = @{ Client = $c; Task = $c.ConnectAsync($ip, $Port) }
  }
  Start-Sleep -Milliseconds 1500
  $found = @()
  foreach ($ip in $clients.Keys) {
    $e = $clients[$ip]
    if ($e.Task.IsCompleted -and -not $e.Task.IsFaulted -and $e.Client.Connected) { $found += $ip }
    $e.Client.Dispose()
  }
  return $found
}

if (-not $NodeIp) {
  $found = @(Find-OllamaNode)
  if ($found.Count -eq 0) { throw "ポート $Port が開いている PC が見つからない。3090 側で setup-3090-ollama-node.ps1 を実行済みか、同じ LAN にいるか確認してください。" }
  if ($found.Count -gt 1) { Write-Warning "複数見つかった: $($found -join ', ')。先頭を使う。別の PC にしたいときは -NodeIp で指定。" }
  $NodeIp = $found[0]
}
$Base = "http://${NodeIp}:$Port"

Write-Host "== 1/3 到達確認: $Base =="
try {
  $tags = Invoke-RestMethod "$Base/api/tags" -TimeoutSec 5
} catch {
  throw "$Base に接続できない: $($_.Exception.Message)`n3090 側で ollama が OLLAMA_HOST=0.0.0.0 で動いているか、ファイアウォールで $Port が開いているか確認してください。"
}
$have = @($tags.models | ForEach-Object { $_.name })
$missing = @($Models | Where-Object { $_ -notin $have })
Write-Host "ノード上のモデル: $($have -join ', ')"
if ($missing.Count -gt 0) {
  Write-Warning "3090 側にまだ無いモデル: $($missing -join ', ')（3090 側で 'ollama pull' が終わっていない可能性）"
}

Write-Host "== 2/3 JINX_OLLAMA を設定 =="
[Environment]::SetEnvironmentVariable('JINX_OLLAMA', $Base, 'User')
$env:JINX_OLLAMA = $Base
Write-Host "JINX_OLLAMA=$Base（ユーザー環境変数。既に開いている他のターミナルや autopilot は開き直すと反映される）"

if (-not $SkipTest) {
  Write-Host "== 3/3 疎通テスト（qwen2.5vl:7b で 1 回だけ生成、初回はモデル読み込みで 10〜30 秒）=="
  $testModel = if ('qwen2.5vl:7b' -in $have) { 'qwen2.5vl:7b' } elseif ($have.Count -gt 0) { $have[0] } else { $null }
  if ($testModel) {
    $body = @{ model = $testModel; prompt = 'Reply with the single word OK.'; stream = $false } | ConvertTo-Json
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-RestMethod "$Base/api/generate" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180
    $sw.Stop()
    Write-Host "応答 ($testModel, $([int]$sw.Elapsed.TotalSeconds) 秒): $($r.response.Trim())"
  } else {
    Write-Warning "モデルが 1 つも無いので推論テストは飛ばす"
  }
} else {
  Write-Host "== 3/3 疎通テストは -SkipTest により省略 =="
}

Write-Host ""
Write-Host "DONE. 5090 の autopilot は JINX_OLLAMA=$Base で 3090 ノードに判定を投げます。"
