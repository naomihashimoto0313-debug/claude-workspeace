"""PR TIMES の「ビューティー」カテゴリから新作コスメのプレスリリースを集める部分。"""

import re
from datetime import datetime

from . import http
from .brands import brand_from_title, products_from_title
from .text import (
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


def is_new_cosme(title, body):
    head = title + "\n" + body[:300]
    if not NEW_PRODUCT_WORDS.search(head):
        return False
    if NOT_PRODUCT_WORDS.search(title) and not STRONG_NEW_WORDS.search(title):
        return False
    # イベントの開催報告は、新製品の話が含まれていても対象外
    if re.search(r"開催|パーティ", title):
        return False
    return True


def to_rows(releases, brand_book):
    rows = []
    for a, published in releases:
        title = a["title"].strip()
        body = html_to_text(a.get("text", ""))
        if not is_new_cosme(title, body):
            continue
        category = classify(title, body)
        if not category:
            continue
        provider = (a.get("provider") or {}).get("name", "")
        listed = brand_book.find(title)
        brand = listed["ブランド名"] if listed else brand_from_title(title, provider)
        release_label, release_date = find_release_date(body, published.date())
        price_label, price_min = find_price(body)
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
            # ここから下は並べ替え・重複判定・タグ付けに使う内部用の値
            "_release_date": release_date,
            "_price_min": price_min,
            "_title": title,
            "_text": title + "\n" + body,
            "_provider": provider,
            "_published": published,
        })
    return rows
