"""Amazon.co.jp: 公式APIは出品者/アソシエイト審査が必要で個人利用には
現実的でないため、ヘッドレスChrome(Selenium)で検索結果ページ or 商品ページを開いて読む。
Amazon側がボット判定してCAPTCHA等を出した場合は、無理に突破しようとせず
単に「今回は0件」として静かにスキップする(次回また試す)。
"""
import urllib.parse
from bs4 import BeautifulSoup
from . import generic_scrape as gs
from . import browser


def check(keyword, direct_url=None, timeout=25, trusted_sellers=None):
    if direct_url:
        return _check_direct_url(direct_url, timeout, trusted_sellers)
    return _check_search(keyword, timeout, trusted_sellers)


def _current_price_tag(soup):
    """実際の販売価格(priceToPay)を返す。取り消し線の参考価格(a-text-price)は対象外にする。
    a-text-price を除外しないと、割引表示時に「参考価格」を実売価格として誤取得してしまう。
    """
    selectors = (
        "#corePrice_feature_div span.priceToPay span.a-offscreen",
        "#corePriceDisplay_desktop_feature_div span.priceToPay span.a-offscreen",
        "#corePrice_feature_div span.a-price:not(.a-text-price) span.a-offscreen",
        "#corePriceDisplay_desktop_feature_div span.a-price:not(.a-text-price) span.a-offscreen",
        "span.priceToPay span.a-offscreen",
        "span.a-price:not(.a-text-price) span.a-offscreen",
    )
    for sel in selectors:
        tag = soup.select_one(sel)
        if tag:
            return tag
    return None


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
    body_text, html = browser.load_page(url, timeout=timeout, wait=3)
    if html is None:
        return {"ok": False, "error": "商品ページを取得できませんでした", "items": []}

    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.select_one("#productTitle")
    name = title_tag.get_text(strip=True) if title_tag else url

    price_tag = _current_price_tag(soup)
    price = None
    if price_tag:
        digits = "".join(ch for ch in price_tag.get_text() if ch.isdigit())
        price = int(digits) if digits else None

    seller = _seller_name(soup)
    seller_ok = _seller_allowed(seller, trusted_sellers)

    unavailable = any(p in body_text for p in gs.UNAVAILABLE_PATTERNS)
    in_stock = price is not None and not unavailable and seller_ok

    if in_stock:
        unavailable_reason = None
    elif price is not None and not unavailable and not seller_ok:
        unavailable_reason = f"信頼できる出品者ではないため対象外(出品者: {seller or '不明'})"
    else:
        unavailable_reason = "価格が見つからないか、取り扱い終了/売り切れの文言あり"

    return {
        "ok": True,
        "items": [
            {
                "name": name,
                "price": price,
                "url": url,
                "in_stock": in_stock,
                "unavailable_reason": unavailable_reason,
                "buy_type": gs.detect_buy_type(body_text),
                "seller": seller,
            }
        ],
    }


def _check_search(keyword, timeout, trusted_sellers=None):
    url = "https://www.amazon.co.jp/s?k=" + urllib.parse.quote(keyword)
    _, html = browser.load_page(url, timeout=timeout, wait=3)
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
