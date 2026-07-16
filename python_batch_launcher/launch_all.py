"""scripts.txt に列挙された Python スクリプトを、それぞれ別のコンソールウィンドウで一括起動する。"""
import subprocess
import sys
from pathlib import Path

SCRIPT_LIST = Path(__file__).with_name("scripts.txt")

# CREATE_NEW_CONSOLE は Windows 専用のフラグ
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def load_script_paths():
    paths = []
    for line in SCRIPT_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line)
    return paths


def main():
    launched = 0
    for path in load_script_paths():
        if not Path(path).exists():
            print(f"[skip] ファイルが見つかりません: {path}")
            continue
        print(f"[launch] {path}")
        subprocess.Popen([sys.executable, path], creationflags=NEW_CONSOLE)
        launched += 1

    print(f"\n{launched} 個のスクリプトを起動しました。")


if __name__ == "__main__":
    main()
