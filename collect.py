"""新作コスメ情報を PR TIMES と @cosme から集めて CSV に保存するプログラム。

使い方（ターミナルで）:
    python collect.py              # 過去7日分
    python collect.py --days 3     # 過去3日分
    python collect.py --no-cosme   # PR TIMES だけ
"""

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector import cosme, prtimes
from collector.brands import BrandBook
from collector.merge import merge
from collector.tags import TAG_WORDS, tag

JST = timezone(timedelta(hours=9))
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# CSV に載せるカテゴリ（ヘアケアを戻したいときは "ヘアケア" を書き足す）
TARGET_CATEGORIES = ["スキンケア", "ベースメイク", "ポイントメイク", "美容家電"]

TAG_NAMES = ["SNSで話題になりそう", "プチプラ"] + [t for t in TAG_WORDS if t != "SNSで話題になりそう"]
COLUMNS = (
    ["ブランド名", "商品名", "カテゴリ", "発売日", "価格", "商品概要", "情報元URL", "情報公開日"]
    + TAG_NAMES
    + ["タグの根拠", "情報元", "ブランド一覧", "取得日"]
)


def sort_key(row, today):
    d = row["_release_date"]
    if d is None:
        return (2, 0)
    if d >= today:
        return (0, (d - today).days)  # これから発売：近い順
    return (1, (today - d).days)  # すでに発売済み：最近のものから


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="何日前までの情報を集めるか")
    ap.add_argument("--ahead", type=int, default=60, help="@cosme は発売日が何日先までの商品を集めるか")
    ap.add_argument("--no-cosme", action="store_true", help="@cosme からは集めない")
    ap.add_argument("--all", action="store_true", help="ブランド一覧にないブランドも含めて全部保存する")
    args = ap.parse_args()

    now = datetime.now(JST)
    today = now.date()
    since = now - timedelta(days=args.days)
    brand_book = BrandBook()

    print(f"PR TIMES：{since:%Y/%m/%d %H:%M} 以降に公開された記事を集めます")
    releases = prtimes.fetch_releases(since)
    pr_rows = prtimes.to_rows(releases, brand_book)
    print(f"  → ビューティーの記事 {len(releases)}件のうち、新作コスメと判定 {len(pr_rows)}件")

    cosme_rows = []
    if not args.no_cosme:
        start, end = today - timedelta(days=args.days), today + timedelta(days=args.ahead)
        print(f"@cosme：発売日が {start:%Y/%m/%d}〜{end:%Y/%m/%d} の商品を集めます")
        items = cosme.fetch_calendar(start, end)
        cache = cosme.fetch_products(items)
        cosme_rows = cosme.to_rows(items, cache)
        print(f"  → カレンダーの商品 {len(items)}件のうち、対象カテゴリ {len(cosme_rows)}件")

    rows = merge(pr_rows, cosme_rows, brand_book)
    rows = [r for r in rows if r["カテゴリ"] in TARGET_CATEGORIES]
    rows.sort(key=lambda r: sort_key(r, today))

    for r in rows:
        listed = brand_book.match(r["ブランド名"], r["商品名"])
        r["_listed"] = listed
        tags, reasons = tag(r, listed)
        for t in TAG_NAMES:
            r[t] = "○" if t in tags else ""
        r["タグの根拠"] = "\n".join(reasons)
        r["ブランド一覧"] = listed["状態"] if listed else "一覧外"
        r["取得日"] = f"{today:%Y/%m/%d}"

    total = len(rows)
    if not args.all:
        # ブランド一覧表（data/brands.csv）にあるブランドだけに絞る
        rows = [r for r in rows if r["_listed"]]
        print(f"\nブランド一覧にあるブランドに絞りました：{total}件 → {len(rows)}件")

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"新作コスメ_{today:%Y%m%d}.csv"
    # Excel で文字化けしないよう BOM 付き UTF-8 で保存
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    both = sum(1 for r in rows if " / " in r["情報元"])
    print(f"\n保存しました：{out}")
    print(f"  合計 {len(rows)}件（PR TIMES と @cosme の両方に載っていてまとめたもの {both}件）")


if __name__ == "__main__":
    main()
