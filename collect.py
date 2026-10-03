"""新作コスメ情報を PR TIMES と @cosme から集めて CSV に保存するプログラム。

使い方（ターミナルで）:
    python collect.py              # 過去7日分
    python collect.py --days 3     # 過去3日分
    python collect.py --no-cosme   # PR TIMES だけ
"""

import argparse
import csv
import unicodedata
from collections import Counter
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
# CSV に載せない価格帯（ブランド一覧表の「価格帯」の列。戻したいときはここから消す）
EXCLUDE_PRICE_TIERS = ["デパコス"]

TAG_NAMES = ["SNSで話題になりそう", "プチプラ"] + [t for t in TAG_WORDS if t != "SNSで話題になりそう"]
COLUMNS = (
    ["ブランド名", "商品名", "カテゴリ", "発売日", "発売状況", "価格", "商品概要", "情報元URL", "情報公開日"]
    + TAG_NAMES
    + ["タグの根拠", "種類", "メモ", "情報元", "ブランド一覧", "取得日"]
)


def sort_key(row, today):
    """並び順：今日以降の発売予定（近い順）→ 発売済み（最近のもの順）→ 発売日不明。
    同じ発売日はブランド名 → 商品名の順。"""
    d = row["_release_date"]
    names = (
        unicodedata.normalize("NFKC", row["ブランド名"]).lower(),
        unicodedata.normalize("NFKC", row["商品名"]).lower(),
    )
    if d is None:
        return (2, 0) + names
    if d >= today:
        return (0, (d - today).days) + names
    return (1, (today - d).days) + names


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

    excluded = Counter()

    print(f"PR TIMES：{since:%Y/%m/%d %H:%M} 以降に公開された記事を集めます")
    releases = prtimes.fetch_releases(since)
    pr_rows, ex = prtimes.to_rows(releases, brand_book)
    excluded.update(ex)
    print(f"  → ビューティーの記事 {len(releases)}件のうち、新作コスメと判定 {len(pr_rows)}件")

    cosme_rows, items = [], []
    if not args.no_cosme:
        start, end = today - timedelta(days=args.days), today + timedelta(days=args.ahead)
        print(f"@cosme：発売日が {start:%Y/%m/%d}〜{end:%Y/%m/%d} の商品を集めます")
        items = cosme.fetch_calendar(start, end)
        cache = cosme.fetch_products(items)
        cosme_rows, ex = cosme.to_rows(items, cache)
        excluded.update(ex)
        print(f"  → カレンダーの商品 {len(items)}件のうち、対象カテゴリ {len(cosme_rows)}件")

    before_merge = len(pr_rows) + len(cosme_rows)
    rows = merge(pr_rows, cosme_rows, brand_book)
    excluded["PR TIMES と @cosme の重複（1行にまとめた）"] += before_merge - len(rows)

    for r in rows:
        # 「ソフィーナ プリマヴィスタ ○○」のように商品名の先頭がブランド名になっているのは @cosme の書き方。
        # PR TIMES の商品名はタイトルから推測したものなので、ブランドの判定には使わない
        product = r["商品名"] if "@cosme" in r["情報元"] else ""
        listed = brand_book.match(r["ブランド名"], product)
        r["_listed"] = listed
        tags, reasons = tag(r, listed)
        for t in TAG_NAMES:
            r[t] = "○" if t in tags else ""
        r["タグの根拠"] = "\n".join(reasons)
        r["ブランド一覧"] = listed["状態"] if listed else "一覧外"
        r["取得日"] = f"{today:%Y/%m/%d}"

    kept = []
    for r in rows:
        if r["カテゴリ"] not in TARGET_CATEGORIES:
            excluded[f"対象外のカテゴリ（{r['カテゴリ']}）"] += 1
        elif r["_listed"] and r["_listed"]["価格帯"] in EXCLUDE_PRICE_TIERS:
            excluded["デパコスのブランド"] += 1
        elif not r["_listed"] and not args.all:
            # ブランド一覧表（data/brands.csv）にあるブランドだけに絞る
            excluded["ブランド一覧にないブランド"] += 1
        else:
            kept.append(r)
    rows = sorted(kept, key=lambda r: sort_key(r, today))
    for r in rows:
        d = r["_release_date"]
        r["発売状況"] = "発売日不明" if d is None else ("発売予定" if d >= today else "発売済み")
        # セルの中の改行は、アプリによって行が分かれて見えるので「 ／ 」でつなぐ
        for k, v in r.items():
            if isinstance(v, str) and "\n" in v:
                r[k] = " ／ ".join(x for x in v.split("\n") if x)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"新作コスメ_{today:%Y%m%d}.csv"
    # Excel で文字化けしないよう BOM 付き UTF-8 で保存
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # 取得件数と除外件数のまとめ
    fetched = len(releases) + len(items)
    lines = [
        f"取得日：{today:%Y/%m/%d}",
        f"取得件数：{fetched}件（PR TIMES の記事 {len(releases)}件 ＋ @cosme の商品 {len(items)}件）",
        f"除外した件数：{sum(excluded.values())}件",
    ]
    lines += [f"  ・{k}：{v}件" for k, v in excluded.most_common()]
    lines.append(f"CSV に残った件数：{len(rows)}件")
    summary = "\n".join(lines)
    (OUTPUT_DIR / f"集計_{today:%Y%m%d}.txt").write_text(summary + "\n", encoding="utf-8")
    print(f"\n保存しました：{out}\n")
    print(summary)


if __name__ == "__main__":
    main()
