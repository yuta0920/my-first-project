import datetime
import json
import os
import sys
import time
import traceback

import config
from checkers import amazon, yodobashi, edion, kakaku, official_lineup
from notifier import notify_windows, log_hit, send_email


def _sites():
    # タカラトミーモールは抽選販売のため、定価・先着監視の対象からは外している。
    return [
        ("Amazon.co.jp", lambda: amazon.check(config.SEARCH_KEYWORDS[0], direct_url=config.AMAZON_URL)),
        (
            "ヨドバシ.com",
            lambda: yodobashi.check(config.SEARCH_KEYWORDS[0], config.MODEL_CODE, direct_url=config.YODOBASHI_URL),
        ),
        ("エディオン", lambda: edion.check(config.MODEL_CODE, config.EDION_URL)),
        ("価格.com", lambda: kakaku.check(config.KAKAKU_KEYWORD, config.MODEL_CODE)),
        ("タカラトミー公式ラインナップ", lambda: official_lineup.check(config.MODEL_CODE)),
    ]


def load_state():
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_target(item):
    name = item.get("name") or ""
    return config.MODEL_CODE in name or "ヘルズネザー" in name


def is_fair_price(price):
    if price is None:
        return True  # 価格不明の場合は「要確認」として通知は出す
    return price <= config.EXPECTED_MSRP + config.MSRP_TOLERANCE


def _price_text(price):
    return f"{price:,}円" if isinstance(price, int) else "価格不明"


def _buy_label(it):
    """予約/購入のどちらが可能かに応じたラベルを返す。"""
    bt = it.get("buy_type")
    if bt == "予約":
        return "【予約できます!】"
    if bt == "購入":
        return "【購入できます!】"
    return "【定価で買える!】"


def _item_status(it):
    """1商品の状態を、素人にも分かる短い日本語にする。"""
    price = it.get("price")
    in_stock = bool(it.get("in_stock", True))
    pt = _price_text(price)
    if in_stock and is_fair_price(price):
        return f"{pt} / 在庫あり → {_buy_label(it)}"
    if not in_stock:
        reason = it.get("unavailable_reason") or "在庫なし"
        return f"{pt} / {reason} → 対象外"
    return f"{pt} / 在庫あり → 高いので対象外(定価オーバー)"


def _site_detail(items):
    """1サイト分の表示テキストを作る。"""
    if not items:
        return "対象商品なし(0件)"
    if len(items) == 1:
        return _item_status(items[0])
    cheapest = min(
        items, key=lambda x: x.get("price") if isinstance(x.get("price"), int) else 10 ** 9
    )
    return f"{len(items)}件ヒット / 最安 {_item_status(cheapest)}"


def run_once(state, verbose=True):
    any_checked = False
    ok_count = 0
    ng_count = 0
    new_hits = 0

    for site_name, fn in _sites():
        try:
            result = fn()
        except Exception as e:
            ng_count += 1
            if verbose:
                print(f"[{site_name}] 例外: {e}")
            else:
                print(f"  ・{site_name} … 今回は確認できませんでした(エラー)", flush=True)
            continue

        if not result.get("ok"):
            ng_count += 1
            if verbose:
                print(f"[{site_name}] 取得できませんでした: {result.get('error')}")
            else:
                print(f"  ・{site_name} … 今回は確認できませんでした({result.get('error')})", flush=True)
            continue

        any_checked = True
        ok_count += 1
        items = [it for it in result["items"] if is_target(it)]
        if verbose:
            print(f"[{site_name}] 該当商品 {len(items)} 件")
        else:
            print(f"  ・{site_name} … {_site_detail(items)}", flush=True)

        for it in items:
            key = f"{site_name}::{it['url']}"
            price = it.get("price")
            in_stock = bool(it.get("in_stock", True))
            fair = is_fair_price(price)
            hit_now = in_stock and fair

            prev = state.get(key, {})
            hit_before = bool(prev.get("hit", False))

            if verbose:
                reason = it.get("unavailable_reason")
                print(f"  - {it['name'][:60]!r} 価格:{price} 在庫:{in_stock} 定価相当:{fair}")
                if reason:
                    print(f"    (在庫なし理由: {reason})")
                print(f"    {it['url']}")

            if hit_now and not hit_before:
                new_hits += 1
                price_text = _price_text(price)
                buy_type = it.get("buy_type")  # "予約" / "購入" / None
                action = buy_type or "予約/購入"  # 分からない時は両方の可能性
                label = _buy_label(it)
                msg = f"{site_name} / {action}できます / 価格:{price_text}\n{it['url']}"
                notify_windows(f"ベイブレードX UX-21 {action}できます!", msg)
                log_hit(config.LOG_FILE, site_name, it["name"], price, in_stock, it["url"])
                print(f"    >>> 【発見】{site_name} で {action}できます 定価:{price_text} → 通知しました  {it['url']}")

                if config.NOTIFY_EMAIL_TO:
                    subject = f"【{action}できます】{config.PRODUCT_NAME}"
                    body = (
                        f"{config.PRODUCT_NAME} が定価相当で {action}できる状態になりました。\n\n"
                        f"お店: {site_name}\n"
                        f"状態: {label}\n"
                        f"価格: {price_text}\n"
                        f"商品名: {it['name']}\n"
                        f"URL: {it['url']}\n\n"
                        f"※このツールは自動では購入しません。上のURLを開いて自分で予約・購入してください。\n"
                        f"※在庫はすぐ無くなる場合があります。お早めに。"
                    )
                    send_email(
                        subject,
                        body,
                        config.NOTIFY_EMAIL_TO,
                        config.SMTP_SERVER,
                        config.SMTP_PORT,
                        config.SMTP_USER,
                        config.SMTP_PASSWORD,
                    )

            state[key] = {
                "hit": hit_now,
                "price": price,
                "site": site_name,
                "name": it["name"],
            }

    if not verbose:
        # 連続監視中の1行まとめ(生きていることが分かるように)
        if new_hits == 0:
            print(f"    → {ok_count}サイト確認完了 / 定価で買える在庫は今のところ無し", flush=True)
        else:
            print(f"    → {ok_count}サイト確認完了 / 定価の在庫を {new_hits}件 見つけました！", flush=True)

    save_state(state)
    return any_checked


def test_mail():
    """設定されたメール設定を使って、テストメールを1通送ってみる。"""
    print("--- メール送信テスト ---")

    missing = []
    if not config.NOTIFY_EMAIL_TO:
        missing.append("NOTIFY_EMAIL_TO(宛先メールアドレス)")
    if not config.SMTP_SERVER:
        missing.append("SMTP_SERVER(送信サーバー)")
    if not config.SMTP_USER:
        missing.append("SMTP_USER(送信元アドレス)")
    if not config.SMTP_PASSWORD:
        missing.append("SMTP_PASSWORD(アプリパスワード)")

    if missing:
        print("次の項目が settings.csv に入力されていません:")
        for m in missing:
            print(f"  ・{m}")
        print("これらを入力・保存してから、もう一度お試しください。")
        return

    print(f"宛先: {config.NOTIFY_EMAIL_TO}")
    print(f"送信元: {config.SMTP_USER}  サーバー: {config.SMTP_SERVER}:{config.SMTP_PORT or '587'}")
    ok = send_email(
        subject="【テスト】ベイブレードX 監視ツール メール送信テスト",
        body=(
            "これはテストメールです。\n"
            "このメールが届いていれば、メール通知の設定は正しくできています。\n\n"
            "定価で買える在庫が見つかったときも、同じようにこのアドレスへお知らせが届きます。"
        ),
        to_addr=config.NOTIFY_EMAIL_TO,
        smtp_server=config.SMTP_SERVER,
        smtp_port=config.SMTP_PORT,
        smtp_user=config.SMTP_USER,
        smtp_password=config.SMTP_PASSWORD,
    )
    if ok:
        print("送信できました。受信箱(または迷惑メールフォルダ)を確認してください。")
    else:
        print("送信に失敗しました。上のエラー内容と settings.csv の入力を確認してください。")
        print("Gmailの場合、SMTP_PASSWORDは通常のパスワードではなく『アプリパスワード』(16桁)が必要です。")


def main():
    if "--testmail" in sys.argv:
        test_mail()
        return

    once = "--once" in sys.argv
    state = load_state()

    if once:
        print("--- 1回だけチェックします ---")
        checked = run_once(state, verbose=True)
        if not checked:
            print("どのサイトからも結果を取得できませんでした。ネットワーク環境や config.py の設定を確認してください。")
        return

    print(f"監視を開始します(間隔: {config.CHECK_INTERVAL_SECONDS}秒)。停止するには Ctrl+C を押してください。")
    print("※各お店ごとにブラウザを開くので、1回の巡回に30秒〜1分ほどかかります。")
    print("※定価で買える在庫が見つかると、ここに【発見】と表示され、通知(とメール)が届きます。\n")
    while True:
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] チェック中… (見つかると通知します / 止めるには Ctrl+C)", flush=True)
        try:
            run_once(state, verbose=False)
        except Exception:
            traceback.print_exc()
        time.sleep(config.CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
