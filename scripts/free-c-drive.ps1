# C ドライブの空き容量を作る（2026-09-17）。3090 PC の PowerShell（管理者）で実行する。
# やること:
#   1. ollama のモデル置き場（約 40GB、C:\Users\<user>\.ollama\models）を F:\ollama\models に移し、OLLAMA_MODELS で以後も F に保存させる
#   2. 途中で失敗した .partial ブロブ、winget のインストーラキャッシュ、TEMP を消す
#   3. ollama を再起動し、取れていなかったモデル（qwen2.5vl:7b, deepseek-r1:32b）を F 側に取得する
#   4. C の空き容量の前後と、ユーザーフォルダの大きい順一覧を表示する（次に何を F に移すか決める材料）
# 使い方: powershell -ExecutionPolicy Bypass -File .\free-c-drive.ps1 [-SkipPull]
param(
  [string]$Dest = 'F:\ollama\models',
  [switch]$SkipPull
)
$ErrorActionPreference = 'Stop'
$Models = 'qwen3-vl:32b', 'qwen3:32b', 'qwen2.5vl:7b', 'deepseek-r1:32b'

function Free-GB([string]$drive) {
  [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
}
function Dir-GB([string]$path) {
  if (-not (Test-Path $path)) { return 0 }
  $sum = (Get-ChildItem $path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  [math]::Round(($sum / 1GB), 2)
}

$destDrive = $Dest.Substring(0, 1)
if (-not (Get-PSDrive $destDrive -ErrorAction SilentlyContinue)) {
  throw "$destDrive ドライブが見つからない。-Dest で別の場所を指定してください（例: -Dest D:\ollama\models）。"
}
$before = Free-GB 'C'
Write-Host "== 開始時 C: 空き $before GB / ${destDrive}: 空き $(Free-GB $destDrive) GB =="

Write-Host "== 1/4 ollama を止めてモデルを $Dest に移動 =="
Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
$src = Join-Path $env:USERPROFILE '.ollama\models'
$current = [Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'User')
if ($current -and (Test-Path $current)) { $src = $current }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
if ((Test-Path $src) -and ((Resolve-Path $src).Path -eq (Resolve-Path $Dest).Path)) {
  Write-Host "モデルは既に $Dest にあるので移動を飛ばす"
} elseif (Test-Path $src) {
  # 失敗した取得の残骸（-partial）は移す価値がないので先に消す
  Get-ChildItem (Join-Path $src 'blobs') -Filter '*-partial*' -ErrorAction SilentlyContinue | Remove-Item -Force
  $size = Dir-GB $src
  Write-Host "移動 $size GB: $src -> $Dest（数分かかる）"
  # robocopy /MOVE はコピー成功を確認してから元を消す。終了コード 8 以上が失敗。
  robocopy $src $Dest /E /MOVE /R:1 /W:1 /NFL /NDL /NJH /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy が失敗した（終了コード $LASTEXITCODE）。モデルは $src と $Dest に分かれている可能性があるので、手動で確認してください。" }
  Write-Host "移動完了"
} else {
  Write-Host "$src が無い（モデル未取得）。以後の取得先だけ $Dest に設定する"
}
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $Dest, 'User')
$env:OLLAMA_MODELS = $Dest

Write-Host "== 2/4 キャッシュ掃除（winget インストーラ、TEMP）=="
foreach ($p in @("$env:LOCALAPPDATA\Temp\WinGet", "$env:TEMP\WinGet", "$env:LOCALAPPDATA\Microsoft\WinGet\Downloads")) {
  if (Test-Path $p) { Write-Host "  削除 $(Dir-GB $p) GB: $p"; Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue }
}
$tempGB = Dir-GB $env:TEMP
Get-ChildItem $env:TEMP -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "  TEMP から約 $tempGB GB を削除（使用中のファイルは残る）"

Write-Host "== 3/4 ollama 再起動 =="
# setup-3090-ollama-node.ps1 が User 環境変数に入れた LAN 公開設定を今のシェルにも反映してから serve を起動する
foreach ($k in 'OLLAMA_HOST', 'OLLAMA_KEEP_ALIVE') {
  $v = [Environment]::GetEnvironmentVariable($k, 'User'); if ($v) { Set-Item "env:$k" $v }
}
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden
$ready = $false
foreach ($i in 1..30) {
  try { Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null; $ready = $true; break } catch { Start-Sleep 1 }
}
if (-not $ready) { throw "ollama serve が 30 秒以内に起動しなかった。手動で 'ollama serve' を実行してエラーを確認してください。" }
$have = @((Invoke-RestMethod 'http://127.0.0.1:11434/api/tags').models | ForEach-Object { $_.name })
Write-Host "  $Dest で認識しているモデル: $($have -join ', ')"

Write-Host "== 4/4 足りないモデルを取得（保存先は $Dest）=="
$missing = @($Models | Where-Object { $_ -notin $have })
if ($SkipPull) {
  Write-Host "  -SkipPull 指定のため飛ばす。未取得: $($missing -join ', ')"
} elseif ($missing.Count -gt 0) {
  foreach ($m in $missing) { ollama pull $m }
  $have = @((Invoke-RestMethod 'http://127.0.0.1:11434/api/tags').models | ForEach-Object { $_.name })
  $still = @($Models | Where-Object { $_ -notin $have })
  if ($still.Count -gt 0) { Write-Warning "取得できていないモデル: $($still -join ', ')" }
} else {
  Write-Host "  全モデル取得済み"
}

Write-Host ""
Write-Host "DONE. C: 空き $before GB -> $(Free-GB 'C') GB / ${destDrive}: 空き $(Free-GB $destDrive) GB"
Write-Host ""
Write-Host "== ユーザーフォルダの大きい順（次に F へ移す候補の目安）=="
Get-ChildItem $env:USERPROFILE -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
  [PSCustomObject]@{ GB = Dir-GB $_.FullName; Folder = $_.Name }
} | Where-Object { $_.GB -ge 0.5 } | Sort-Object GB -Descending | Format-Table -AutoSize
Write-Host "この一覧を Claude に貼ると、次に何を移すかの提案とスクリプトを作ります。"
