# my-first-project

## python_batch_launcher

複数の Python スクリプトを一発で全部起動するためのツールです。

### 使い方

1. `python_batch_launcher/scripts.txt` に、起動したいスクリプトのフルパスを1行ずつ記載する(すでにあなたの環境に合わせて7個登録済み)。
2. `python_batch_launcher/launch_all.bat` をダブルクリックする。
3. `scripts.txt` に書かれた全スクリプトが、それぞれ別のコンソールウィンドウで並行して起動する。

- スクリプトを増減したいときは `scripts.txt` を編集するだけでよい(`launch_all.py` の変更は不要)。
- 行頭に `#` を付けた行はコメント扱いで無視される。
- `python` コマンドが見つからない場合は `launch_all.bat` 内の `python` を `py` などに書き換える。
- さらに手間を省きたい場合は、`launch_all.bat` のショートカットを作成してデスクトップに置くか、タスクスケジューラに登録すると、ダブルクリックやログイン時の自動実行ができる。
