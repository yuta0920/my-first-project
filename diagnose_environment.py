"""JV-Link接続診断: 環境診断スクリプト

PC-KEIBAのセットアップ後にPythonからJV-Linkへ接続するための、
事前環境チェックのみを行う。

このスクリプトは以下を確認する:
    - Windowsのバージョン
    - Pythonのバージョン
    - Pythonの32bit/64bit
    - pywin32が利用可能か
    - JV-LinkのCOM登録状況（レジストリから動的に検出。ProgIDは決め打ちしない）
    - JV-Linkのタイプライブラリ情報

データの取得やPC-KEIBAのデータベースへの書き込みは一切行わない。
"""

import datetime
import logging
import platform
import struct
import subprocess
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"

# JV-LinkのProgID/CLSIDを断定せず、レジストリ上のキー名に対する
# 部分一致検索で候補を探すためのキーワード。
# （公式ProgIDや型名を推測してハードコードすることは行わない）
_JVLINK_NAME_HINTS = ("jv", "link")


def setup_logger(name="diagnose_environment"):
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{name}_{timestamp}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger, log_path


def check_windows_version(logger):
    logger.info("=== Windows バージョン ===")
    if platform.system() != "Windows":
        logger.warning(
            "実行OSがWindowsではありません（検出: %s）。JV-LinkはWindows専用のCOMコンポーネントのため、"
            "本チェックはWindows実機（PC-KEIBAをセットアップしたPC）で実行してください。",
            platform.system(),
        )
        return

    logger.info("platform.platform(): %s", platform.platform())
    release, version, csd, ptype = platform.win32_ver()
    logger.info("platform.win32_ver(): release=%s version=%s csd=%s ptype=%s", release, version, csd, ptype)

    try:
        wv = sys.getwindowsversion()
        logger.info(
            "sys.getwindowsversion(): major=%s minor=%s build=%s platform=%s product_type=%s",
            wv.major, wv.minor, wv.build, wv.platform, getattr(wv, "product_type", "N/A"),
        )
    except AttributeError:
        logger.warning("sys.getwindowsversion() が利用できません。")

    # platform.win32_ver() はPythonのバージョンによってWindows 10/11を
    # 区別できないことがあるため、PowerShell経由でも参考情報を取得する。
    # (読み取り専用のGet-CimInstanceのみ。設定変更は行わない)
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance Win32_OperatingSystem) | "
                "Select-Object Caption,Version,BuildNumber,OSArchitecture | ConvertTo-Json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.info("PowerShell Get-CimInstance Win32_OperatingSystem: %s", result.stdout.strip())
        else:
            logger.warning(
                "PowerShellからのOS情報取得に失敗しました (returncode=%s): %s",
                result.returncode,
                result.stderr.strip(),
            )
    except Exception as e:  # noqa: BLE001 - 参考情報の取得なので失敗しても診断は続行する
        logger.warning("PowerShell経由でのOS情報取得に失敗しました: %s", e)


def check_python_version(logger):
    logger.info("=== Python バージョン ===")
    logger.info("sys.version: %s", sys.version)
    logger.info("platform.python_version(): %s", platform.python_version())
    logger.info("platform.python_implementation(): %s", platform.python_implementation())
    logger.info("sys.executable: %s", sys.executable)


def check_python_bitness(logger):
    logger.info("=== Python 32bit / 64bit ===")
    arch = platform.architecture()[0]
    pointer_bits = struct.calcsize("P") * 8
    logger.info("platform.architecture(): %s", arch)
    logger.info("struct.calcsize('P') * 8: %sbit", pointer_bits)
    logger.info(
        "注記: JV-LinkはWindowsのCOMコンポーネントであり、環境によっては32bit版として提供される場合がある。"
        "Pythonのbit数とJV-Linkのbit数が一致しないと、COMインスタンス生成時にエラーとなることがある。"
        "正確な対応関係は必ずJV-Link/JRA-VAN Data Labの公式ドキュメントで確認すること。"
    )


def check_pywin32(logger):
    logger.info("=== pywin32 の利用可否 ===")
    try:
        import pythoncom
        import win32api
        import win32com
        import win32com.client
    except ImportError as e:
        logger.error("pywin32（win32com / pythoncom）のインポートに失敗しました: %s", e)
        logger.error("pip install pywin32 が必要です（別途承認の上で実施してください）。")
        return False

    logger.info("pywin32: 利用可能")
    logger.info("win32com module path: %s", win32com.__file__)
    try:
        logger.info("pythoncom module path: %s", pythoncom.__file__)
    except AttributeError:
        pass
    try:
        logger.info("win32api.GetVersionEx(): %s", win32api.GetVersionEx())
    except Exception as e:  # noqa: BLE001 - 参考情報取得のため失敗しても続行
        logger.warning("win32api.GetVersionEx() の呼び出しに失敗しました: %s", e)
    return True


def _enum_hkcr_matches(access_flag, view_label, logger):
    """指定したレジストリビューでHKEY_CLASSES_ROOT直下を列挙し、
    JV-Link関連と思われるキー名（'jv' と 'link' の両方を含む、大小文字無視）を集める。
    """
    import winreg

    matches = []
    try:
        key = winreg.OpenKeyEx(winreg.HKEY_CLASSES_ROOT, "", 0, winreg.KEY_READ | access_flag)
    except OSError as e:
        logger.info("レジストリビュー[%s]は利用できません: %s", view_label, e)
        return matches

    try:
        index = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, index)
            except OSError:
                break
            index += 1

            lowered = subkey_name.lower()
            if all(hint in lowered for hint in _JVLINK_NAME_HINTS):
                entry = {"progid": subkey_name, "view": view_label, "clsid": None}
                try:
                    with winreg.OpenKey(key, subkey_name + r"\CLSID") as clsid_key:
                        entry["clsid"] = winreg.QueryValue(clsid_key, None)
                except OSError:
                    pass
                matches.append(entry)
    finally:
        winreg.CloseKey(key)

    return matches


def discover_jvlink_registrations(logger):
    """JV-LinkのProgIDを決め打ちせず、実機のレジストリから
    'jv' と 'link' を含むCOM登録エントリを検出する。

    64bit Windows上では32bit専用のCOMコンポーネントが
    WOW6432Nodeビューにのみ登録されていることがあるため、
    既定ビューに加えて32bit/64bitビューも明示的に確認する。

    ここで見つかったものが実際にJV-Linkかどうかは、
    JV-Link/JRA-VAN Data Labの公式ドキュメントと突き合わせて
    利用者自身が確認すること。
    """
    logger.info("=== JV-Link COM登録状況 ===")

    if platform.system() != "Windows":
        logger.warning("Windows以外のためレジストリ検索をスキップします。")
        return []

    import winreg

    views = [
        (0, "既定のビュー（プロセスと同じbit）"),
        (winreg.KEY_WOW64_32KEY, "32bitレジストリビュー (WOW6432Node)"),
        (winreg.KEY_WOW64_64KEY, "64bitレジストリビュー"),
    ]

    all_matches = []
    seen = set()
    for access_flag, view_label in views:
        for entry in _enum_hkcr_matches(access_flag, view_label, logger):
            key = (entry["progid"].lower(), entry["view"])
            if key in seen:
                continue
            seen.add(key)
            all_matches.append(entry)

    if not all_matches:
        logger.warning(
            "レジストリ上に 'jv' と 'link' を両方含むProgIDは見つかりませんでした。"
            "JV-Link SDKが未インストールか、PC-KEIBAのセットアップが完了していない可能性があります。"
        )
    else:
        for entry in all_matches:
            logger.info(
                "検出: ProgID=%s CLSID=%s (レジストリビュー: %s)",
                entry["progid"], entry["clsid"], entry["view"],
            )

    return all_matches


def describe_typelib_for_clsid(logger, clsid):
    logger.info("--- タイプライブラリ情報 (CLSID=%s) ---", clsid)
    if not clsid:
        logger.warning("CLSIDが不明のためタイプライブラリ情報を取得できません。")
        return

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\TypeLib") as key:
            typelib_guid = winreg.QueryValue(key, None)
    except OSError:
        logger.warning("CLSID %s にTypeLibの登録が見つかりませんでした。", clsid)
        return

    logger.info("TypeLib GUID: %s", typelib_guid)

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"TypeLib\{typelib_guid}") as tlb_key:
            version_index = 0
            while True:
                try:
                    version = winreg.EnumKey(tlb_key, version_index)
                except OSError:
                    break
                version_index += 1
                try:
                    with winreg.OpenKey(tlb_key, version) as ver_key:
                        try:
                            description = winreg.QueryValue(ver_key, None)
                        except OSError:
                            description = "(説明なし)"
                        logger.info("  バージョン %s: %s", version, description)
                except OSError as e:
                    logger.warning("  バージョン %s の詳細取得に失敗しました: %s", version, e)
    except OSError as e:
        logger.warning("TypeLib %s の情報取得に失敗しました: %s", typelib_guid, e)


def check_jvlink_typelib(logger, candidates):
    logger.info("=== JV-Link タイプライブラリ情報 ===")
    if not candidates:
        logger.warning("JV-Link候補のCOM登録が見つからなかったため、タイプライブラリ情報の取得をスキップします。")
        return

    for entry in candidates:
        if entry.get("clsid"):
            describe_typelib_for_clsid(logger, entry["clsid"])


def main():
    logger, log_path = setup_logger("diagnose_environment")
    logger.info("=== JV-Link接続診断: 環境診断 開始 ===")
    logger.info("ログファイル: %s", log_path)
    logger.info(
        "本スクリプトはデータ取得やデータベースへの書き込みは一切行わない環境チェック専用スクリプトです。"
    )

    check_windows_version(logger)
    check_python_version(logger)
    check_python_bitness(logger)
    check_pywin32(logger)
    candidates = discover_jvlink_registrations(logger)
    check_jvlink_typelib(logger, candidates)

    logger.info("=== JV-Link接続診断: 環境診断 終了 ===")
    logger.info("詳細はログファイルを参照してください: %s", log_path)


if __name__ == "__main__":
    main()
