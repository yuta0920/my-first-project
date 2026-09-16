# 3090 PC を「判定ノード」にする（2026-09-17）。この 1 本を 3090 PC の PowerShell（管理者）で実行する。
# 役割: ollama で qwen3-vl:32b（同一人物・肌の採点）/ qwen3:32b（演出指示・翻訳）/ qwen2.5vl:7b（絵コンテ適合）/ deepseek-r1:32b（予備）を
#       LAN に公開し、5090 PC の autopilot が JINX_OLLAMA=http://<この PC の IP>:11434 で使う。5090 の VRAM は H3 生成に専念できる。
# 3090（24GB）で 32B モデル（約 20GB）は 1 本ずつ載る。同時に 2 本は載らないので ollama が自動で入れ替える。
$ErrorActionPreference = 'Stop'
Write-Host "== 1/5 ollama install =="
winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements --silent
# winget が追加した PATH はこのセッションにまだ反映されていないので読み直す（ollama コマンドを見つけるため）
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
Write-Host "== 2/5 LAN 公開設定（OLLAMA_HOST=0.0.0.0、常駐時間 30 分）=="
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '30m', 'User')
$env:OLLAMA_HOST = '0.0.0.0'; $env:OLLAMA_KEEP_ALIVE = '30m'
Write-Host "== 3/5 firewall 11434 =="
if (-not (Get-NetFirewallRule -DisplayName 'Ollama 11434' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName 'Ollama 11434' -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow -Profile Private | Out-Null
}
Write-Host "== 4/5 ollama 再起動 =="
Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden
Start-Sleep 5
Write-Host "== 5/5 モデル取得（約 66GB、回線次第で 30〜90 分）=="
foreach ($m in 'qwen3-vl:32b', 'qwen3:32b', 'qwen2.5vl:7b', 'deepseek-r1:32b') { ollama pull $m }
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' } | Select-Object -First 1 -ExpandProperty IPAddress)
Write-Host ""
Write-Host "DONE. この PC の IP: $ip"
Write-Host "5090 PC 側で JINX_OLLAMA=http://${ip}:11434 を設定すれば判定がこの PC で走ります。"
