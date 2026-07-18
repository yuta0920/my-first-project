"""Amazon.co.jp: 公式APIは出品者/アソシエイト審査が必要で個人利用には
現実的でないため、ヘッドレスChrome(Selenium)で検索結果ページ or 商品ページを開いて読む。
Amazon側がボット判定してCAPTCHA等を出した場合は、無理に突破しようとせず
単に「今回は0件」として静かにスキップする(次回また試す)。
"""
import urllib.parse
from bs4 import BeautifulSoup
from . import generic_scrape as gs
from . import browser


def check(keyword, direct_url=None, timeout=25):
    if direct_url:
        return _check_direct_url(direct_url, timeout)
    return _check_search(keyword, timeout)


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


def _check_direct_url(url, timeout):
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

    unavailable = any(p in body_text for p in gs.UNAVAILABLE_PATTERNS)
    in_stock = price is not None and not unavailable

    return {
        "ok": True,
        "items": [
            {
                "name": name,
                "price": price,
                "url": url,
                "in_stock": in_stock,
                "unavailable_reason": None if in_stock else "価格が見つからないか、取り扱い終了/売り切れの文言あり",
                "buy_type": gs.detect_buy_type(body_text),
            }
        ],
    }


def _check_search(keyword, timeout):
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
