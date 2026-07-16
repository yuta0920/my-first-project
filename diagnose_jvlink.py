"""JV-Link接続診断: インスタンス生成診断スクリプト

JV-LinkのCOMインスタンス生成のみを試行し、成功/失敗を明確に表示する。

行わないこと:
    - JVInit/JVOpen等によるデータ取得は行わない
    - PC-KEIBAのPostgreSQLデータベースへのアクセス・書き込みは行わない
    - JV-Linkの具体的なメソッド呼び出しは一切行わない（インスタンス生成のみ）

ProgIDは決め打ちにせず、diagnose_environment.py と同じロジックで
レジストリから動的に検出する。検出できない場合は --progid オプションで
明示的に指定できる（instructions: 公式ドキュメントで確認した値を渡すこと）。
"""

import argparse
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagnose_environment import discover_jvlink_registrations, setup_logger  # noqa: E402


def try_create_instance(logger, progid):
    logger.info("JV-Linkインスタンスの生成を試行します。ProgID=%s", progid)

    try:
        import win32com.client
    except ImportError as e:
        logger.error("失敗: pywin32（win32com）が利用できないため、COMインスタンスを生成できません。")
        logger.error("例外の型: %s", type(e).__name__)
        logger.error("エラーメッセージ: %s", e)
        return False

    try:
        obj = win32com.client.Dispatch(progid)
    except Exception as e:  # noqa: BLE001 - pywintypes.com_error等を含め全て記録する
        logger.error("失敗: JV-Linkインスタンスの生成に失敗しました。")
        logger.error("例外の型: %s", type(e).__name__)
        logger.error("エラーメッセージ: %s", e)

        hresult = None
        args = getattr(e, "args", None)
        if args:
            hresult = args[0]
        if hresult is not None:
            logger.error("エラー番号 (args[0] / HRESULT等): %s", hresult)

        return False

    logger.info("成功: JV-Linkインスタンスの生成に成功しました。")
    logger.info("生成されたオブジェクト: %r", obj)
    del obj
    return True


def main():
    parser = argparse.ArgumentParser(
        description="JV-Link接続診断（COMインスタンス生成のみ。データ取得・DB更新は行わない）"
    )
    parser.add_argument(
        "--progid",
        help=(
            "使用するJV-LinkのProgIDを明示的に指定する。"
            "省略時はレジストリから自動検出する。"
            "公式ドキュメントで確認した値を指定すること（推測値を指定しないこと）。"
        ),
    )
    args = parser.parse_args()

    logger, log_path = setup_logger("diagnose_jvlink")
    logger.info("=== JV-Link接続診断: インスタンス生成診断 開始 ===")
    logger.info("ログファイル: %s", log_path)
    logger.info("本スクリプトはデータ取得・データベース更新を一切行いません。")

    if platform.system() != "Windows":
        logger.error(
            "実行OSがWindowsではありません（検出: %s）。"
            "JV-LinkはWindows専用のCOMコンポーネントのため、Windows実機で実行してください。",
            platform.system(),
        )
        sys.exit(1)

    progid = args.progid
    if progid:
        logger.info("コマンドラインで指定されたProgIDを使用します: %s", progid)
    else:
        candidates = discover_jvlink_registrations(logger)
        if not candidates:
            logger.error(
                "JV-LinkのProgIDをレジストリから検出できませんでした。"
                "--progid オプションで公式ドキュメント記載の値を明示的に指定するか、"
                "JV-Link SDK / PC-KEIBAのセットアップ状況を確認してください。"
            )
            sys.exit(1)
        progid = candidates[0]["progid"]
        if len(candidates) > 1:
            logger.warning(
                "複数のJV-Link候補が検出されました。先頭の候補を使用します: %s "
                "（他の候補: %s）",
                progid,
                ", ".join(c["progid"] for c in candidates[1:]),
            )
        logger.info("自動検出されたProgIDを使用します: %s", progid)

    success = try_create_instance(logger, progid)

    logger.info("=== JV-Link接続診断: インスタンス生成診断 終了 (結果: %s) ===", "成功" if success else "失敗")
    logger.info("詳細はログファイルを参照してください: %s", log_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
