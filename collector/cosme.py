"""@cosme の「新作コスメカレンダー」と商品ページから新作情報を集める部分。

@cosme には「情報が載った日」が表示されないため、発売日で範囲を決めて集めます。
一度見た商品ページは cache/ に保存し、次回からはアクセスしません（相手の負担を減らすため）。
"""

import json
import re
from datetime import date
from pathlib import Path

from . import http
from .text import html_to_text, summarize

BASE = "https://www.cosme.net"
CACHE = Path(__file__).resolve().parent.parent / "cache" / "cosme_products.json"


def _months(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_calendar(start, end, log=print):
    """発売日が start〜end の商品を、カレンダーから一覧で取る。"""
    items = []
    for y, m in _months(start, end):
        res = http.get(f"{BASE}/calendar/index/year/{y}/month/{m:02d}", wait=2.0, encoding="cp932")
        if res is None:
            log(f"  @cosme {y}年{m}月のカレンダーが取得できませんでした。")
            continue
        page = res.text
        body_start = page.find('class="newProductList"')
        page = page[body_start:] if body_start >= 0 else page
        # 日付の見出しごとに区切る
        parts = re.split(r'<h3 class="subTitle">\s*(\d{1,2})月(\d{1,2})日', page)
        count = 0
        for i in range(1, len(parts) - 2, 3):
            day = date(y, int(parts[i]), int(parts[i + 1]))
            if not start <= day <= end:
                continue
            block = parts[i + 2]
            for bm in re.finditer(
                r'<h4 class="brandName">\s*<a href="[^"]*/brands/(\d+)/">([^<]+)</a>(.*?)(?=<h4 class="brandName">|$)',
                block, re.S,
            ):
                brand = bm.group(2).strip()
                for pm in re.finditer(r'href="https://www\.cosme\.net/products/(\d+)/">([^<]+)</a>', bm.group(3)):
                    items.append({
                        "id": pm.group(1),
                        "brand": brand,
                        "name": pm.group(2).strip(),
                        "calendar_date": day,
                    })
                    count += 1
        log(f"  @cosme {y}年{m}月：対象期間の商品 {count}件")
    # 同じ商品が複数日に載ることがあるので1つにまとめる
    seen = {}
    for it in items:
        seen.setdefault(it["id"], it)
    return list(seen.values())


def _load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache):
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _field(page, label):
    m = re.search(
        r'<p class="info-ttl">' + label + r'</p>\s*<p class="info-desc">(.*?)</p>', page, re.S
    )
    return html_to_text(m.group(1)).replace("NEW", "").strip() if m else ""


def fetch_product(pid):
    res = http.get(f"{BASE}/products/{pid}/", wait=2.0, encoding="cp932")
    if res is None:
        return None
    page = res.text
    cat = re.search(r'<dl class="item-category[^"]*">.*?<dd>(.*?)</dd>', page, re.S)
    categories = []
    if cat:
        for span in re.findall(r"<span>(.*?)</span>", cat.group(1), re.S):
            categories.append(" > ".join(re.findall(r">([^<>]+)</a>", span)))
    desc = re.search(r'<dl class="item-description[^"]*">\s*<dt>[^<]*</dt>\s*<dd>(.*?)</dd>', page, re.S)
    return {
        "price": _field(page, "容量・税込価格"),
        "release": _field(page, "発売日"),
        "categories": categories,
        "description": html_to_text(desc.group(1)) if desc else "",
    }


def fetch_products(items, log=print):
    cache = _load_cache()
    new = [it for it in items if it["id"] not in cache]
    log(f"  @cosme 商品ページ：{len(items)}件中、新しく見る商品 {len(new)}件（1件2秒ほどかかります）")
    for n, it in enumerate(new, 1):
        info = fetch_product(it["id"])
        if info is not None:
            cache[it["id"]] = info
        if n % 50 == 0:
            _save_cache(cache)
            log(f"    {n}/{len(new)} 件 完了")
    _save_cache(cache)
    return cache


# @cosme のカテゴリ名 → このブログ用の5カテゴリ
def map_category(paths):
    for p in paths:
        top = p.split(" > ")[0]
        sub = p.split(" > ")[1] if " > " in p else ""
        lower = " > ".join(p.split(" > ")[1:])
        if re.search(r"美容家電|美容機器|美顔器|ドライヤー|ヘアアイロン|脱毛器", lower):
            return "美容家電"
        if top.startswith("美容グッズ") or "ネイル" in sub:
            continue  # メイクブラシ・つけまつげ・ネイルなどは対象外
        if sub == "スキンケアキット":
            return "スキンケア"
        if sub == "メイクアップキット・パレット":
            return "ポイントメイク"
        if top.startswith("スキンケア"):
            return "スキンケア"
        if top.startswith("ヘアケア"):
            return "ヘアケア"
        if top.startswith("ベースメイク"):
            return "ベースメイク"
        if top.startswith(("メイクアップ", "ポイントメイク")) or sub in (
            "アイメイク", "リップメイク", "チーク", "フェイスカラー", "アイシャドウ", "口紅"
        ):
            return "ポイントメイク"
    return ""


def _price(src):
    """「150mL・14,850円」のような @cosme の表記から税込価格を読む（@cosme の欄は税込）。"""
    nums = sorted({int(n.replace(",", "")) for n in re.findall(r"([\d,]{3,7})円", src)})
    nums = [n for n in nums if 100 <= n <= 300000]
    if nums:
        label = f"{nums[0]:,}円（税込）" if len(nums) == 1 else f"{nums[0]:,}〜{nums[-1]:,}円（税込）"
        return label, nums[0]
    if "オープン価格" in src:
        return "オープン価格", None
    return src, None


def to_rows(items, cache):
    rows = []
    for it in items:
        info = cache.get(it["id"])
        if not info:
            continue
        category = map_category(info["categories"])
        if not category:
            continue
        price_label, price_min = _price(info["price"])
        m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", info["release"])
        rel = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else it["calendar_date"]
        rows.append({
            "ブランド名": it["brand"],
            "商品名": it["name"],
            "カテゴリ": category,
            "発売日": f"{rel:%Y/%m/%d}",
            "価格": price_label,
            "商品概要": summarize(info["description"]),
            "情報元URL": f"{BASE}/products/{it['id']}/",
            "情報公開日": "",
            "情報元": "@cosme",
            "_release_date": rel,
            "_price_min": price_min,
            "_title": it["name"],
            "_text": it["name"] + "\n" + info["description"],
            "_provider": "",
            "_published": None,
            "_cosme_category": " / ".join(info["categories"]),
        })
    return rows
