"""Amazon.co.jp: 公式APIは出品者/アソシエイト審査が必要で個人利用には
現実的でないため、ヘッドレスChrome(Selenium)で検索結果ページ or 商品ページを開いて読む。
Amazon側がボット判定してCAPTCHA等を出した場合は、無理に突破しようとせず
単に「今回は0件」として静かにスキップする(次回また試す)。
"""
import re
import urllib.parse
from bs4 import BeautifulSoup
from . import generic_scrape as gs
from . import browser


def check(keyword, direct_url=None, timeout=25, trusted_sellers=None):
    if direct_url:
        return _check_direct_url(direct_url, timeout, trusted_sellers)
    return _check_search(keyword, timeout, trusted_sellers)


def _current_price_tag(soup):
    """単一の「買い物カゴ」(バイボックス)がある通常ページでの実売価格(priceToPay)を返す。
    取り消し線の参考価格(a-text-price)は対象外。ここで見つからない場合は None を返す
    (ページ全体を対象にした無条件フォールバックはしない — 複数出品者が並ぶページで
    無関係な価格を拾ってしまう不具合の原因になっていたため、あえて外している)。
    """
    selectors = (
        "#corePrice_feature_div span.priceToPay span.a-offscreen",
        "#corePriceDisplay_desktop_feature_div span.priceToPay span.a-offscreen",
        "#corePrice_feature_div span.a-price:not(.a-text-price) span.a-offscreen",
        "#corePriceDisplay_desktop_feature_div span.a-price:not(.a-text-price) span.a-offscreen",
    )
    for sel in selectors:
        tag = soup.select_one(sel)
        if tag:
            return tag
    return None


_TAX_EXCLUDED_RE = re.compile(r"^￥([\d,]+)\s*税抜$")
_TAX_INCLUDED_RE = re.compile(r"^￥([\d,]+)\s*税込$")
_OFFER_SELLER_RE = re.compile(r"^(?:出荷元|販売元)(.+)$")


def _parse_offer_listing(body_text):
    """単一バイボックスが無く、複数の出品者(出荷元/販売元)が並んでいるページ用の解析。
    CSSクラスではなく画面表示テキスト(税抜/税込/出荷元/販売元の行)を頼りにしているので、
    レイアウトのクラス名変更に強い代わりに、行区切りの想定が崩れると解析0件になる。
    """
    lines = [ln.strip() for ln in body_text.splitlines() if ln.strip()]
    offers = []
    i = 0
    while i < len(lines) - 1:
        m_pretax = _TAX_EXCLUDED_RE.match(lines[i])
        m_tax = _TAX_INCLUDED_RE.match(lines[i + 1]) if m_pretax else None
        if not (m_pretax and m_tax):
            i += 1
            continue

        price = int(m_tax.group(1).replace(",", ""))
        condition = lines[i - 1] if i > 0 else None
        seller = None
        for j in range(i + 2, min(i + 15, len(lines))):
            if _TAX_EXCLUDED_RE.match(lines[j]):
                break  # 出品者が見つかる前に次の出品の価格行に到達した
            sm = _OFFER_SELLER_RE.match(lines[j])
            if sm:
                seller = sm.group(1).strip()
                break
        offers.append({"condition": condition, "price": price, "seller": seller})
        i += 2
    return offers


_SELLER_PREFIXES = ("販売:", "販売元:", "販売業者:", "出荷元:", "Sold by", "Ships from and sold by")


def _seller_name(soup):
    """買い物カゴ(バイボックス)に表示されている出品者名を取得する。取れなければ None。"""
    tag = soup.select_one("#merchant-info") or soup.select_one("#tabular-buybox #tabular-buybox-container")
    if not tag:
        return None
    text = tag.get_text(" ", strip=True)
    for prefix in _SELLER_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = text.strip()
    return text or None


def _seller_allowed(seller, trusted_sellers):
    """trusted_sellers が空(未設定)なら従来通り出品者は問わない。設定されている場合のみ絞り込む。"""
    if not trusted_sellers:
        return True
    if not seller:
        return False
    return any(t in seller for t in trusted_sellers)


def _check_direct_url(url, timeout, trusted_sellers=None):
    # 複数出品者の一覧(All Offers Display)はJSで後から描画されるため、
    # 通常ページより長めに待ってから本文を読む(browser.py側の実装は未確認のため、
    # ここで安全側に倒して待ち時間を延ばしている)。
    body_text, html = browser.load_page(url, timeout=timeout, wait=6)
    if html is None:
        return {"ok": False, "error": "商品ページを取得できませんでした", "items": []}

    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.select_one("#productTitle")
    name = title_tag.get_text(strip=True) if title_tag else url
    unavailable = any(p in body_text for p in gs.UNAVAILABLE_PATTERNS)
    buy_type = gs.detect_buy_type(body_text)

    price_tag = _current_price_tag(soup)
    if price_tag is not None:
        digits = "".join(ch for ch in price_tag.get_text() if ch.isdigit())
        price = int(digits) if digits else None
        seller = _seller_name(soup)
        seller_ok = _seller_allowed(seller, trusted_sellers)
        in_stock = price is not None and not unavailable and seller_ok

        if in_stock:
            reason = None
        elif price is not None and not unavailable and not seller_ok:
            reason = f"信頼できる出品者ではないため対象外(出品者: {seller or '不明'})"
        else:
            reason = "価格が見つからないか、取り扱い終了/売り切れの文言あり"

        return {
            "ok": True,
            "items": [
                {
                    "name": name,
                    "price": price,
                    "url": url,
                    "in_stock": in_stock,
                    "unavailable_reason": reason,
                    "buy_type": buy_type,
                    "seller": seller,
                }
            ],
        }

    # 単一のバイボックスが見つからない = 複数の出品者(出荷元/販売元)が並ぶページの可能性が高い。
    offers = _parse_offer_listing(body_text)
    if not offers:
        # 出品一覧はJSの遅延描画のため、初回でまだ描画し切れていない可能性がある。
        # もう一度だけ、さらに長く待ってから読み直してみる。
        body_text, html = browser.load_page(url, timeout=timeout, wait=10)
        if html is not None:
            soup = BeautifulSoup(html, "html.parser")
            unavailable = any(p in body_text for p in gs.UNAVAILABLE_PATTERNS)
            offers = _parse_offer_listing(body_text)
    if not offers:
        return {
            "ok": True,
            "items": [
                {
                    "name": name,
                    "price": None,
                    "url": url,
                    "in_stock": False,
                    "unavailable_reason": "価格情報を解析できませんでした(ページ構成が想定と異なる可能性)",
                    "buy_type": buy_type,
                    "seller": None,
                }
            ],
        }

    items = []
    for idx, offer in enumerate(offers):
        seller = offer["seller"]
        seller_ok = _seller_allowed(seller, trusted_sellers)
        in_stock = not unavailable and seller_ok
        if in_stock:
            reason = None
        elif not seller_ok:
            reason = f"信頼できる出品者ではないため対象外(出品者: {seller or '不明'})"
        else:
            reason = "取り扱い終了/売り切れの文言あり"
        items.append(
            {
                "name": name,
                "price": offer["price"],
                # 出品ごとに状態を別々に追跡できるよう、出品者名をURLのフラグメントとして付与する
                "url": f"{url}#offer={urllib.parse.quote(seller or f'offer{idx}')}",
                "in_stock": in_stock,
                "unavailable_reason": reason,
                "buy_type": buy_type,
                "seller": seller,
                "condition": offer["condition"],
            }
        )
    return {"ok": True, "items": items}


def _check_search(keyword, timeout, trusted_sellers=None):
    url = "https://www.amazon.co.jp/s?k=" + urllib.parse.quote(keyword)
    _, html = browser.load_page(url, timeout=timeout, wait=3)  # 検索結果は静的なのでこちらは従来通り
    if html is None:
        return {"ok": False, "error": "検索結果ページを取得できませんでした", "items": []}

    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select("div[data-component-type='s-search-result']"):
        title_tag = card.select_one("h2 span")
        link_tag = card.select_one("h2 a")
        if not title_tag or not link_tag:
            continue
        price_tag = card.select_one("span.a-price:not(.a-text-price) > span.a-offscreen")
        price = None
        if price_tag:
            digits = "".join(ch for ch in price_tag.get_text() if ch.isdigit())
            price = int(digits) if digits else None
        href = link_tag.get("href", "")
        full_url = "https://www.amazon.co.jp" + href if href.startswith("/") else href
        card_text = card.get_text(" ", strip=True)
        unavailable = any(p in card_text for p in gs.UNAVAILABLE_PATTERNS)
        # 検索結果カードには出品者名が出ないため、出品者フィルタは商品ページ(direct_url)のみで有効。
        items.append(
            {
                "name": title_tag.get_text(strip=True),
                "price": price,
                "url": full_url,
                # Amazonは価格が取れて、かつ「売り切れ」等の文言が無ければ購入可能とみなす
                "in_stock": price is not None and not unavailable,
            }
        )
    return {"ok": True, "items": items}
