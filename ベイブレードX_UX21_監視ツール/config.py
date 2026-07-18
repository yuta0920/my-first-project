"""設定値は同じフォルダの settings.csv で管理している(Excel等で編集できるように)。
このファイルは settings.csv を読み込んで、他のモジュールが今まで通り
`config.EXPECTED_MSRP` のように参照できるようにするだけの薄いローダー。
"""
import csv
import os

_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.csv")


def _load():
    values = {}
    with open(_CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row.get("key") or "").strip()
            # 空行や「#」で始まる行は説明用コメントとして無視する
            if not key or key.startswith("#"):
                continue
            values[key] = row.get("value", "")
    return values


_v = _load()

PRODUCT_NAME = _v["PRODUCT_NAME"]
MODEL_CODE = _v["MODEL_CODE"]
SEARCH_KEYWORDS = [k.strip() for k in _v["SEARCH_KEYWORDS"].split("|") if k.strip()]
EXPECTED_MSRP = int(_v["EXPECTED_MSRP"])
MSRP_TOLERANCE = int(_v["MSRP_TOLERANCE"])
CHECK_INTERVAL_SECONDS = int(_v["CHECK_INTERVAL_SECONDS"])

# 商品ページのURLが分かっている場合はここに入る(空文字ならキーワード検索にフォールバック)
AMAZON_URL = _v.get("AMAZON_URL", "").strip() or None
YODOBASHI_URL = _v.get("YODOBASHI_URL", "").strip() or None
EDION_URL = _v.get("EDION_URL", "").strip() or None
KAKAKU_KEYWORD = _v.get("KAKAKU_KEYWORD", "").strip() or None

# メール通知の設定(空欄ならメールは送らず、Windows通知とログだけ)
# 複数宛先に送りたい場合は settings.csv の値にカンマ区切りで並べる(例: a@x.com,b@y.com)
NOTIFY_EMAIL_TO = _v.get("NOTIFY_EMAIL_TO", "").strip()
SMTP_SERVER = _v.get("SMTP_SERVER", "").strip()
SMTP_PORT = _v.get("SMTP_PORT", "").strip()
SMTP_USER = _v.get("SMTP_USER", "").strip()
# アプリパスワードはGoogleが4桁ずつ空白区切りで表示するが、実際の値は空白なしの16文字。
# 空白を入れたまま貼り付けても動くよう、間の空白もすべて取り除く。
SMTP_PASSWORD = "".join(_v.get("SMTP_PASSWORD", "").split())

STATE_FILE = _v["STATE_FILE"]
LOG_FILE = _v["LOG_FILE"]
