"""collect.py で作った CSV を、メールで読みやすい HTML レポートにするプログラム。

使い方（ターミナルで）:
    python make_report.py                                  # いちばん新しい CSV から作る
    python make_report.py output/新作コスメ_20261004.csv    # CSV を指定して作る

output/メール_日付.html に保存します（Gmail の本文としてそのまま使えます）。
"""

import csv
import html
import re
import sys
from collections import Counter
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

TAGS = ["SNSで話題になりそう", "プチプラ", "新ブランド／新シリーズ", "限定商品", "40代でも使いやすそう"]
TAG_STYLE = {  # 背景色, 文字色
    "SNSで話題になりそう": ("#fde7f0", "#a3134f"),
    "プチプラ": ("#e6f4ea", "#1e6b34"),
    "新ブランド／新シリーズ": ("#e8f0fe", "#1a4fa0"),
    "限定商品": ("#fff4e0", "#8a4b00"),
    "40代でも使いやすそう": ("#f1e8fb", "#5b2a8c"),
}
CATEGORY_COLOR = {"スキンケア": "#2e7d6b", "ベースメイク": "#a0673a", "ポイントメイク": "#b0335a", "美容家電": "#455a8a"}
PICKUP_MIN_TAGS = 3  # タグがこの数以上の商品を「記事にしやすい候補」として上に出す
SUMMARY_LEN = 80


def e(s):
    return html.escape(s or "", quote=True)


# 見た目の指定（Gmail は <style> の中のクラス指定に対応しているので、まとめて書いて容量を小さくする）
CSS = """
body{margin:0;padding:0;background:#f6f4f2;font-family:'Hiragino Sans','Hiragino Kaku Gothic ProN','Meiryo',sans-serif;color:#222}
.w{max-width:640px;margin:0 auto;padding:16px 10px}
.h1{font-size:20px;font-weight:bold}
.sub{font-size:14px;color:#444;margin-top:6px}
.sec{font-size:17px;font-weight:bold;border-left:4px solid #888;padding-left:8px;margin:18px 0 8px}
.pk{color:#a3134f;border-color:#a3134f}
.note{font-size:12px;color:#666;margin-bottom:8px}
.mon{font-size:15px;font-weight:bold;color:#555;margin:14px 0 8px}
.c{border:1px solid #e6e6e6;border-radius:8px;margin:0 0 10px;background:#fff;padding:12px 14px}
.cs{border-color:#e0a0bc}
.d{font-size:12px;color:#666;margin-bottom:4px}
.b{font-size:13px;color:#555}
.n{font-size:16px;font-weight:bold;margin:2px 0 6px}
.p{font-size:13px;color:#333;margin-bottom:6px}
.s{font-size:13px;color:#444;line-height:1.6;margin:4px 0 6px}
.m{font-size:12px;color:#8a4b00;margin-bottom:6px}
.l a{color:#1a4fa0;font-size:13px;margin-right:12px}
.t{display:inline-block;margin:0 4px 4px 0;padding:2px 8px;border-radius:10px;font-size:12px}
.t0{background:#fde7f0;color:#a3134f}.t1{background:#e6f4ea;color:#1e6b34}.t2{background:#e8f0fe;color:#1a4fa0}
.t3{background:#fff4e0;color:#8a4b00}.t4{background:#f1e8fb;color:#5b2a8c}
.pl{font-size:14px;line-height:1.7;margin:0 0 6px;padding:0 0 6px;border-bottom:1px dashed #e0d0d6}
.f{font-size:12px;color:#777;line-height:1.7;margin-top:18px}
"""


def n_tags(row):
    return sum(row.get(t) == "○" for t in TAGS)


def tag_badges(row):
    return "".join(f'<span class="t t{i}">{e(t)}</span>' for i, t in enumerate(TAGS) if row.get(t) == "○")


def links(row):
    out = []
    for url in [u.strip() for u in row["情報元URL"].split("／") if u.strip()]:
        label = "PR TIMES" if "prtimes" in url else "@cosme" if "cosme" in url else "情報元"
        out.append(f'<a href="{e(url)}">{label}で見る</a>')
    return "".join(out)


def card(row, star):
    summary = row["商品概要"]
    if len(summary) > SUMMARY_LEN:
        summary = summary[:SUMMARY_LEN] + "…"
    details = " ・ ".join(x for x in [row["価格"] or "価格不明", row["種類"]] if x)
    memo = row.get("メモ", "")
    color = CATEGORY_COLOR.get(row["カテゴリ"], "#555")
    return (
        f'<div class="c{" cs" if star else ""}">'
        f'<div class="d"><b style="color:#222">{e(row["発売日"] or "発売日不明")}</b>（{e(row["発売状況"])}）'
        f'<span style="color:{color};margin-left:6px">● {e(row["カテゴリ"])}</span>'
        f'{" <b style=color:#a3134f>★記事候補</b>" if star else ""}</div>'
        f'<div class="b">{e(row["ブランド名"])}</div>'
        f'<div class="n">{e(row["商品名"])}</div>'
        f'<div class="p">{e(details)}</div>'
        f'<div>{tag_badges(row)}</div>'
        f'<div class="s">{e(summary)}</div>'
        + (f'<div class="m">⚠ {e(memo)}</div>' if memo else "")
        + f'<div class="l">{links(row)}</div></div>'
    )


def build(rows, summary_text, date_label):
    status = Counter(r["発売状況"] for r in rows)
    tag_counts = {t: sum(r.get(t) == "○" for r in rows) for t in TAGS}
    pickup = sorted([r for r in rows if n_tags(r) >= PICKUP_MIN_TAGS], key=lambda r: -n_tags(r))
    unknown = f' ／ 発売日不明 {status["発売日不明"]}件' if status.get("発売日不明") else ""

    parts = [
        f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="w">',
        f'<div class="h1">新作コスメ情報（{e(date_label)}）</div>',
        f'<div class="sub">全 <b>{len(rows)}件</b>（発売予定 {status.get("発売予定", 0)}件 ／ 発売済み {status.get("発売済み", 0)}件{unknown}）</div>',
        '<div style="margin-top:8px">'
        + "".join(f'<span class="t t{i}">{e(t)} {n}件</span>' for i, (t, n) in enumerate(tag_counts.items()))
        + "</div>",
    ]
    if pickup:
        parts.append(f'<div class="sec pk">★ 記事にしやすい候補（タグ{PICKUP_MIN_TAGS}つ以上）</div>')
        parts.append('<div class="note">くわしくは下の一覧の「★記事候補」を見てください。</div>')
        for r in pickup:
            parts.append(
                f'<div class="pl"><b>{e(r["発売日"] or "発売日不明")}</b>　{e(r["ブランド名"])}　'
                f'<b>{e(r["商品名"])}</b><br>{tag_badges(r)}</div>'
            )
    parts.append('<div class="sec">発売日順の一覧</div>')
    current_month = None
    for r in rows:
        m = re.match(r"(\d{4})/(\d{2})", r["発売日"])
        month = f"{int(m.group(2))}月" if m else "発売日不明"
        if month != current_month:
            current_month = month
            parts.append(f'<div class="mon">― {e(month)} ―</div>')
        parts.append(card(r, n_tags(r) >= PICKUP_MIN_TAGS))
    parts.append(
        '<div class="f"><b>ご注意</b><br>'
        "・ブランド名・価格・発売日・タグは自動で読み取っています。記事にする前に必ず情報元で確認してください。<br>"
        "・@cosme の商品説明は自分用のメモです。ブログには転載しないでください（@cosme 利用規約 第7条）。<br><br>"
        f"<b>今回の集計</b><br>{e(summary_text).strip().replace(chr(10), '<br>')}</div>"
        "</div></body></html>"
    )
    return "".join(parts)


def main():
    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
    else:
        src = sorted(OUTPUT_DIR.glob("新作コスメ_*.csv"))[-1]
    date_code = re.search(r"(\d{8})", src.name).group(1)
    with open(src, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    summary_file = OUTPUT_DIR / f"集計_{date_code}.txt"
    summary_text = summary_file.read_text(encoding="utf-8") if summary_file.exists() else ""
    date_label = f"{int(date_code[4:6])}月{int(date_code[6:])}日"
    out = OUTPUT_DIR / f"メール_{date_code}.html"
    out.write_text(build(rows, summary_text, date_label), encoding="utf-8")
    print(f"保存しました：{out}")


if __name__ == "__main__":
    main()
