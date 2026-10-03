"""PR TIMES の「ビューティー」カテゴリから新作コスメのプレスリリースを集める部分。"""

import re
from collections import Counter
from datetime import datetime

from . import http
from .brands import brand_from_title, products_from_title
from .text import (
    ANIME_WORDS,
    EVENT_WORDS,
    FOOD_WORDS,
    NEW_PRODUCT_WORDS,
    NOT_PRODUCT_WORDS,
    STRONG_NEW_WORDS,
    classify,
    find_price,
    find_release_date,
    html_to_text,
    summarize,
)

API = "https://prtimes.jp/api/search_release.php"
PER_PAGE = 40
MAX_PAGES = 60


def fetch_releases(since, log=print):
    """since（日時）以降に公開された「ビューティー」カテゴリのプレスリリースを全部取る。"""
    releases = []
    for page in range(1, MAX_PAGES + 1):
        res = http.get(
            API,
            params={"page": page, "type": "main_category", "v": "beauty", "limit": PER_PAGE},
            wait=1.5,
        )
        if res is None:
            log(f"  PR TIMES {page}ページ目が取得できませんでした。ここで止めます。")
            break
        articles = res.json().get("articles", [])
        if not articles:
            break
        oldest = None
        for a in articles:
            published = datetime.fromisoformat(a["updated_at"]["time_iso_8601"])
            oldest = published
            if published >= since:
                releases.append((a, published))
        log(f"  PR TIMES {page}ページ目：{oldest:%m/%d %H:%M} までの記事を確認")
        if oldest is not None and oldest < since:
            break
    return releases


def exclude_reason(title, body):
    """対象外にする理由を返す。対象ならNone。"""
    head = title + "\n" + body[:300]
    if FOOD_WORDS.search(title):
        return "食品・サプリ"
    if ANIME_WORDS.search(title):
        return "アニメ・キャラクター関連"
    if EVENT_WORDS.search(title):
        return "イベント・施設"
    if not NEW_PRODUCT_WORDS.search(head):
        return "新商品のお知らせではない（調査・企業ニュースなど）"
    if NOT_PRODUCT_WORDS.search(title) and not STRONG_NEW_WORDS.search(title):
        return "新商品のお知らせではない（調査・企業ニュースなど）"
    if not classify(title, body):
        return "コスメ以外・対象外カテゴリ（ボディ・ネイル・香水・雑貨など）"
    return None


def kind(title):
    """新商品の種類（新色・リニューアルなど）。"""
    t = title
    if "新色" in t:
        return "新色"
    if "リニューアル" in t:
        return "リニューアル"
    if "定番化" in t:
        return "定番化"
    if "再販" in t or "復刻" in t:
        return "再販"
    return "新商品"


def to_rows(releases, brand_book):
    """記事を1行ずつのデータにする。(行のリスト, 除外した理由ごとの件数) を返す。"""
    rows = []
    excluded = Counter()
    for a, published in releases:
        title = a["title"].strip()
        body = html_to_text(a.get("text", ""))
        reason = exclude_reason(title, body)
        if reason:
            excluded[reason] += 1
            continue
        category = classify(title, body)
        provider = (a.get("provider") or {}).get("name", "")
        # 「〇〇ブランド「rdrd」」と書かれていれば、そのブランドを優先する
        # （「rom&ndを展開する会社の新ブランドrdrd」が rom&nd と判定されないように）
        m = re.search(r"ブランド\s*[「『]([^」』]{2,30})[」』]", title)
        named = m.group(1) if m else ""
        listed = brand_book.match(named) if named else None
        if named and not listed:
            brand = named
        else:
            listed = listed or brand_book.find(title)
            brand = listed["ブランド名"] if listed else brand_from_title(title, provider)
        release_label, release_date = find_release_date(body, published.date())
        price_label, price_min = find_price(body)
        memo = []
        if re.search(r"期間限定価格|メガポ|メガ割|セール価格|特別価格", body[:1500]):
            memo.append("価格はセール・期間限定価格の可能性あり")
        rows.append({
            "ブランド名": brand,
            "商品名": products_from_title(title, brand),
            "カテゴリ": category,
            "発売日": release_label,
            "価格": price_label,
            "商品概要": summarize(body),
            "情報元URL": "https://prtimes.jp" + a["url"],
            "情報公開日": f"{published:%Y/%m/%d}",
            "情報元": "PR TIMES",
            "種類": kind(title),
            "メモ": "\n".join(memo),
            # ここから下は並べ替え・重複判定・タグ付けに使う内部用の値
            "_release_date": release_date,
            "_price_min": price_min,
            "_title": title,
            "_text": title + "\n" + body,
            "_provider": provider,
            "_published": published,
        })
    return rows, excluded
