# my-first-project

PC-KEIBA（PostgreSQL）と連携するJV-Linkデータ取得プログラムの開発プロジェクト。

現段階では **JV-Link接続診断プログラムのみ** を提供している。
データ取得プログラム（通常データ取得を期間ごとに分割実行する処理）は、
この診断が成功した後の次の段階で作成する。

## 重要: 現段階でできること・できないこと

- 現段階のスクリプトは **診断のみ** を行う。
- JVOpen/JVRead等によるデータ取得は **行わない**。
- PC-KEIBAのPostgreSQLデータベースへの接続・INSERT/UPDATE/DELETE/TRUNCATE/
  CREATE/ALTER/DROPは **一切行わない**。
- JV-LinkのProgID・メソッド名・引数は、コード内に決め打ちで書いていない。
  `diagnose_environment.py` / `diagnose_jvlink.py` はどちらも、
  実行時にWindowsレジストリ（HKEY_CLASSES_ROOT）を検索して
  JV-Link関連のCOM登録を動的に検出する。検出結果が実際にJV-Linkかどうかは、
  JV-Link/JRA-VAN Data Labの公式ドキュメントと突き合わせて必ず確認すること。

## 前提条件

- Windows PC（PC-KEIBAおよびJV-Link SDKがセットアップ済みであること）
- PowerShellが利用できること
- Python 3.x がインストールされていること
  - JV-LinkはWindowsのCOMコンポーネントであり、環境によっては32bit版として
    提供される場合がある。Pythonのbit数とJV-Linkのbit数が一致しないと、
    COMインスタンス生成時にエラーとなることがある
    （`diagnose_environment.py` がPythonのbit数を確認する）。
    正確な対応関係は必ず公式ドキュメントで確認すること。
- `pywin32` パッケージ（`requirements.txt` に記載）

このリポジトリのスクリプトは、上記のセットアップ状況を**変更せず確認するだけ**である。
パッケージのインストールやレジストリ変更が必要な場合でも、スクリプト自身は
それらを行わない。

## セットアップ（Windows PowerShellでの実行例）

```powershell
# 1. 仮想環境の作成（任意。PC-KEIBAが利用しているPythonと同じbit数を使用すること）
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. 依存パッケージのインストール
pip install -r requirements.txt
```

`pip install` の実行、レジストリの変更、管理者権限での実行が必要な操作は、
利用者自身の判断・承認のもとで実施すること。

## 実行方法

### 1. 環境診断

```powershell
python diagnose_environment.py
```

以下を確認し、結果を画面と `logs\diagnose_environment_YYYYMMDD_HHMMSS.log` に出力する。

| 確認項目 | 内容 |
|---|---|
| Windowsバージョン | `platform.win32_ver()` / `sys.getwindowsversion()` に加え、参考情報として PowerShell の `Get-CimInstance Win32_OperatingSystem`（読み取り専用）の結果を記録する |
| Pythonバージョン | `sys.version` / `platform.python_version()` |
| Pythonの32bit/64bit | `platform.architecture()` / ポインタサイズ |
| pywin32の利用可否 | `win32com` / `pythoncom` / `win32api` のインポート可否とパス |
| JV-LinkのCOM登録状況 | `HKEY_CLASSES_ROOT` 配下を走査し、キー名に `jv` と `link` の両方を含む ProgID を検出する。64bit Windows上の32bit専用登録も見逃さないよう、既定ビュー・32bitビュー(WOW6432Node)・64bitビューの3つを個別に確認する |
| JV-Linkのタイプライブラリ情報 | 検出したCLSIDに紐づく `TypeLib` レジストリ情報（GUID・バージョン・説明） |

### 2. JV-Linkインスタンス生成診断

```powershell
python diagnose_jvlink.py

# レジストリから自動検出されたProgIDではなく、
# 公式ドキュメントで確認済みのProgIDを明示的に使いたい場合
python diagnose_jvlink.py --progid "確認済みのProgID"
```

行うことは **COMインスタンスの生成試行のみ**（`win32com.client.Dispatch(progid)`）。
JVInit/JVOpen等のメソッド呼び出しやデータ取得は行わない。

成功/失敗を画面に明示し、失敗時は例外の型・エラーメッセージ・エラー番号
（HRESULT等）を `logs\diagnose_jvlink_YYYYMMDD_HHMMSS.log` に記録する。

終了コードは成功時 `0`、失敗時 `1`。

## ログ

`logs\` フォルダに実行日時ごとのログファイルが作成される
（例: `logs\diagnose_environment_20260716_153000.log`）。
ログファイル自体は `.gitignore` で除外しており、リポジトリには
フォルダの存在のみを `.gitkeep` で保持している。

## エラーの意味（代表例）

| 症状 | 想定される原因 |
|---|---|
| `pywin32（win32com / pythoncom）のインポートに失敗` | `pywin32` が未インストール。`pip install pywin32` が必要（要承認）|
| JV-Link関連のProgIDがレジストリに見つからない | JV-Link SDKが未インストール、または PC-KEIBA/JV-Linkのセットアップが未完了 |
| `Dispatch` 失敗時の例外に `-2147221164` (`0x80040154`, `REGDB_E_CLASSNOTREG`) 等が含まれる | 指定したProgIDのCOMクラスが（現在のプロセスのbit数から見て）登録されていない。Pythonとインストール済みJV-Linkのbit不一致が典型的な原因の一つ |
| `--progid` を指定しても失敗する | 指定したProgIDが誤っている、または管理者権限でのCOM登録が必要な状態になっている可能性がある。公式ドキュメントとPC-KEIBA側のセットアップ手順を再確認すること |
| Windows以外のOSで実行した旨のメッセージが出る | JV-LinkはWindows専用のCOMコンポーネントのため、Windows実機（PC-KEIBAをセットアップしたPC）で実行する必要がある |

## 今後の予定

この診断プログラムで接続に問題がないことを確認した後、次の段階として
通常データ取得を期間ごとに分割実行するプログラムを作成する。
データ取得・データベース更新を伴う処理は、本diagnoseスクリプトの範囲外であり、
別途承認のうえで着手する。
