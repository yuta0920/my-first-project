# 3090 PC を「判定ノード」にする（2026-09-17）。この 1 本を 3090 PC の PowerShell（管理者）で実行する。
# 役割: ollama で qwen3-vl:32b（同一人物・肌の採点）/ qwen3:32b（演出指示・翻訳）/ qwen2.5vl:7b（絵コンテ適合）/ deepseek-r1:32b（予備）を
#       LAN に公開し、5090 PC の autopilot が JINX_OLLAMA=http://<この PC の IP>:11434 で使う。5090 の VRAM は H3 生成に専念できる。
# 3090（24GB）で 32B モデル（約 20GB）は 1 本ずつ載る。同時に 2 本は載らないので ollama が自動で入れ替える。
# 実行後、5090 PC で scripts/connect-5090-to-3090.ps1 を実行すると接続確認と JINX_OLLAMA の設定まで自動で行う。
$ErrorActionPreference = 'Stop'
$Models = 'qwen3-vl:32b', 'qwen3:32b', 'qwen2.5vl:7b', 'deepseek-r1:32b'

function Refresh-Path {
  # winget でインストールした直後は今のシェルの PATH に ollama が載っていないので、Machine + User の PATH を読み直す
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

Write-Host "== 1/5 ollama install =="
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Write-Host "ollama は既に入っているのでインストールを飛ばす"
} else {
  winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements --silent
  Refresh-Path
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "ollama が PATH に見つからない。管理者 PowerShell を開き直してからこのスクリプトを再実行してください。"
  }
}

Write-Host "== 2/5 LAN 公開設定（OLLAMA_HOST=0.0.0.0、常駐時間 30 分）=="
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '30m', 'User')
$env:OLLAMA_HOST = '0.0.0.0'; $env:OLLAMA_KEEP_ALIVE = '30m'

Write-Host "== 3/5 firewall 11434（同一サブネットからのみ許可、ネットワークが Public 扱いでも通る）=="
# 古い Private 限定ルールが残っていたら消して、LocalSubnet 限定・全プロファイルのルールに置き換える
Get-NetFirewallRule -DisplayName 'Ollama 11434' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'Ollama 11434' -Direction Inbound -Protocol TCP -LocalPort 11434 `
  -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null

Write-Host "== 4/5 ollama 再起動 =="
# インストーラが起動するトレイ常駐（ollama app.exe）は 127.0.0.1 でしか待ち受けないので、一度全部止めて serve を起動し直す
Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden
$ready = $false
foreach ($i in 1..30) {
  try { Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null; $ready = $true; break } catch { Start-Sleep 1 }
}
if (-not $ready) { throw "ollama serve が 30 秒以内に起動しなかった。手動で 'ollama serve' を実行してエラーを確認してください。" }

Write-Host "== 5/5 モデル取得（約 66GB、回線次第で 30〜90 分）=="
foreach ($m in $Models) { ollama pull $m }
$have = (Invoke-RestMethod 'http://127.0.0.1:11434/api/tags').models | ForEach-Object { $_.name }
$missing = $Models | Where-Object { $_ -notin $have }
if ($missing) { Write-Warning "取得できていないモデル: $($missing -join ', ')" }

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' } |
  Select-Object -First 1 -ExpandProperty IPAddress)
Write-Host ""
Write-Host "DONE. この PC の IP: $ip"
Write-Host "5090 PC 側で次を実行すると接続確認と JINX_OLLAMA の設定が自動で行われます:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\connect-5090-to-3090.ps1 -NodeIp $ip"
Write-Host "手動で設定する場合: JINX_OLLAMA=http://${ip}:11434"
