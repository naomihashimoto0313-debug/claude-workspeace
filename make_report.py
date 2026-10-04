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
SUMMARY_LEN = 90


def e(s):
    return html.escape(s or "")


def tag_badges(row):
    out = []
    for t in TAGS:
        if row.get(t) == "○":
            bg, fg = TAG_STYLE[t]
            out.append(
                f'<span style="display:inline-block;margin:0 4px 4px 0;padding:2px 8px;border-radius:10px;'
                f'background:{bg};color:{fg};font-size:12px;">{e(t)}</span>'
            )
    return "".join(out)


def links(row):
    out = []
    for url in [u.strip() for u in row["情報元URL"].split("／") if u.strip()]:
        label = "PR TIMES" if "prtimes" in url else "@cosme" if "cosme" in url else "情報元"
        out.append(f'<a href="{e(url)}" style="color:#1a4fa0;">{label}で見る</a>')
    return "　".join(out)


def card(row, highlight=False):
    tags_count = sum(row.get(t) == "○" for t in TAGS)
    cat = row["カテゴリ"]
    color = CATEGORY_COLOR.get(cat, "#555")
    summary = row["商品概要"]
    if len(summary) > SUMMARY_LEN:
        summary = summary[:SUMMARY_LEN] + "…"
    details = " ・ ".join(x for x in [row["価格"] or "価格不明", row["種類"]] if x)
    memo = row.get("メモ", "")
    border = "#e0b0c4" if highlight else "#e6e6e6"
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {border};border-radius:8px;margin:0 0 10px 0;background:#ffffff;">
<tr><td style="padding:12px 14px;">
  <div style="font-size:12px;color:#666;margin-bottom:4px;">
    <b style="color:#222;">{e(row['発売日'] or '発売日不明')}</b>（{e(row['発売状況'])}）
    <span style="color:{color};margin-left:6px;">● {e(cat)}</span>
  </div>
  <div style="font-size:13px;color:#555;">{e(row['ブランド名'])}</div>
  <div style="font-size:16px;font-weight:bold;color:#222;margin:2px 0 6px 0;">{e(row['商品名'])}</div>
  <div style="font-size:13px;color:#333;margin-bottom:6px;">{e(details)}</div>
  <div>{tag_badges(row)}{'' if tags_count else '<span style="font-size:12px;color:#999;">タグなし</span>'}</div>
  <div style="font-size:13px;color:#444;line-height:1.6;margin:4px 0 6px 0;">{e(summary)}</div>
  {f'<div style="font-size:12px;color:#8a4b00;margin-bottom:6px;">⚠ {e(memo)}</div>' if memo else ''}
  <div style="font-size:13px;">{links(row)}</div>
</td></tr></table>"""


def build(rows, summary_text, date_label):
    status = Counter(r["発売状況"] for r in rows)
    tag_counts = {t: sum(r.get(t) == "○" for r in rows) for t in TAGS}
    pickup = [r for r in rows if sum(r.get(t) == "○" for t in TAGS) >= PICKUP_MIN_TAGS]
    pickup.sort(key=lambda r: -sum(r.get(t) == "○" for t in TAGS))

    parts = [f"""<!doctype html><html><body style="margin:0;padding:0;background:#f6f4f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f4f2;"><tr><td align="center" style="padding:16px 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;font-family:'Hiragino Sans','Hiragino Kaku Gothic ProN','Meiryo',sans-serif;">
<tr><td style="padding:4px 4px 12px 4px;">
  <div style="font-size:20px;font-weight:bold;color:#222;">新作コスメ情報（{e(date_label)}）</div>
  <div style="font-size:14px;color:#444;margin-top:6px;">
    全 <b>{len(rows)}件</b>（発売予定 {status.get('発売予定', 0)}件 ／ 発売済み {status.get('発売済み', 0)}件{' ／ 発売日不明 ' + str(status['発売日不明']) + '件' if status.get('発売日不明') else ''}）
  </div>
  <div style="margin-top:8px;">""" + "".join(
        f'<span style="display:inline-block;margin:0 4px 4px 0;padding:2px 8px;border-radius:10px;'
        f'background:{TAG_STYLE[t][0]};color:{TAG_STYLE[t][1]};font-size:12px;">{e(t)} {n}件</span>'
        for t, n in tag_counts.items()
    ) + "</div></td></tr>"]

    if pickup:
        parts.append(f"""<tr><td style="padding:8px 4px;">
  <div style="font-size:17px;font-weight:bold;color:#a3134f;border-left:4px solid #a3134f;padding-left:8px;margin-bottom:4px;">★ 記事にしやすい候補（タグ{PICKUP_MIN_TAGS}つ以上）</div>
  <div style="font-size:12px;color:#666;margin-bottom:10px;">タグが多い順。下の一覧にも同じ商品が載っています。</div>
  {''.join(card(r, highlight=True) for r in pickup)}
</td></tr>""")

    parts.append("""<tr><td style="padding:8px 4px;">
  <div style="font-size:17px;font-weight:bold;color:#222;border-left:4px solid #888;padding-left:8px;margin-bottom:10px;">発売日順の一覧</div>""")
    current_month = None
    for r in rows:
        m = re.match(r"(\d{4})/(\d{2})", r["発売日"])
        month = f"{int(m.group(2))}月" if m else "発売日不明"
        if month != current_month:
            current_month = month
            parts.append(f'<div style="font-size:15px;font-weight:bold;color:#555;margin:14px 0 8px 0;">― {e(month)} ―</div>')
        parts.append(card(r))
    parts.append("</td></tr>")

    parts.append(f"""<tr><td style="padding:12px 4px;font-size:12px;color:#777;line-height:1.7;">
  <div style="font-weight:bold;color:#555;">ご注意</div>
  ・ブランド名・価格・発売日・タグは自動で読み取っています。記事にする前に必ず情報元で確認してください。<br>
  ・@cosme の商品説明は自分用のメモです。ブログには転載しないでください（@cosme 利用規約 第7条）。<br>
  <div style="font-weight:bold;color:#555;margin-top:8px;">今回の集計</div>
  {e(summary_text).replace(chr(10), '<br>')}
</td></tr>
</table></td></tr></table></body></html>""")
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
