"""同じ商品が PR TIMES と @cosme の両方にある場合などに、1行にまとめる部分。"""

import re

from .text import normalize


def _product_key(name):
    return normalize(name)


def _join(a, b):
    parts = [p for p in (a.split("\n") if a else []) + (b.split("\n") if b else []) if p]
    return "\n".join(dict.fromkeys(parts))


def _absorb(keep, other):
    """other の情報を keep に足す（keep に空欄がある項目だけ埋める）。"""
    keep["情報元URL"] = _join(keep["情報元URL"], other["情報元URL"])
    keep["情報元"] = " / ".join(dict.fromkeys(keep["情報元"].split(" / ") + other["情報元"].split(" / ")))
    for col in ("発売日", "価格", "商品概要", "情報公開日"):
        if not keep[col] and other[col]:
            keep[col] = other[col]
    # 種類は「新商品」より具体的なもの（新色・追加発売など）を残す
    if keep.get("種類") == "新商品" and other.get("種類") not in (None, "新商品"):
        keep["種類"] = other["種類"]
    other_memo = other.get("メモ", "")
    if keep["価格"]:
        # keep 側の価格を使うので、other 側の価格についての注意書きは付けない
        other_memo = "\n".join(l for l in other_memo.split("\n") if not l.startswith("価格"))
    keep["メモ"] = _join(keep.get("メモ", ""), other_memo)
    if keep["_release_date"] is None:
        keep["_release_date"] = other["_release_date"]
    if keep["_price_min"] is None:
        keep["_price_min"] = other["_price_min"]
    # 情報公開日は早いほう（最初に発表された日）
    if other["_published"] and (keep["_published"] is None or other["_published"] < keep["_published"]):
        keep["_published"] = other["_published"]
        keep["情報公開日"] = other["情報公開日"]
    keep["_text"] += "\n" + other["_text"]


def _brand_ok(cosme_row, pr_row, brand_book):
    """@cosme のブランドが PR TIMES の記事のブランドと同じと言えるか。"""
    if brand_book.key(cosme_row["ブランド名"]) == brand_book.key(pr_row["ブランド名"]):
        return True
    hay = normalize(pr_row["_title"] + pr_row["_provider"] + pr_row["_text"][:500])
    names = [cosme_row["ブランド名"]] + re.findall(r"[(（]([^)）]+)[)）]", cosme_row["ブランド名"])
    names.append(re.sub(r"[(（].*?[)）]", "", cosme_row["ブランド名"]))
    return any(len(normalize(n)) >= 2 and normalize(n) in hay for n in names)


def merge(pr_rows, cosme_rows, brand_book):
    # 1) @cosme の商品が PR TIMES の記事に載っていれば、@cosme の行に PR TIMES の情報を足す
    used_pr = set()
    for c in cosme_rows:
        name = _product_key(c["商品名"])
        brand_n = normalize(re.sub(r"[(（].*?[)）]", "", c["ブランド名"]))
        short = name[len(brand_n):] if brand_n and name.startswith(brand_n) else name
        if len(short) < 4:
            continue
        for i, p in enumerate(pr_rows):
            if not _brand_ok(c, p, brand_book):
                continue
            if short in normalize(p["_text"]):
                _absorb(c, p)
                c["_published"] = p["_published"]
                c["情報公開日"] = p["情報公開日"]
                used_pr.add(i)
    rest_pr = [p for i, p in enumerate(pr_rows) if i not in used_pr]

    # 2) 同じサイトの中での重複（同じブランド・同じ商品名）をまとめる
    merged = {}
    for row in cosme_rows + rest_pr:
        key = (brand_book.key(row["ブランド名"]), _product_key(row["商品名"]))
        if key in merged:
            _absorb(merged[key], row)
        else:
            merged[key] = row
    return list(merged.values())
