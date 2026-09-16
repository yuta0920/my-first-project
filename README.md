# my-first-project

## 3090 PC を判定ノードにして 5090 PC からつなぐ

| 順番 | どの PC | 実行するもの | やること |
| --- | --- | --- | --- |
| 1 | 3090 PC（管理者 PowerShell） | `scripts/setup-3090-ollama-node.ps1` | ollama を入れて LAN に公開し、判定用モデル 4 本を取得する |
| 2 | 5090 PC（通常 PowerShell） | `scripts/connect-5090-to-3090.ps1 -NodeIp <3090 の IP>` | 到達確認、モデル確認、`JINX_OLLAMA` の設定、推論テスト |

手順 1 の最後に表示される IP をそのまま手順 2 に渡す。IP を省略すると同一サブネットを走査して自動で見つける。
