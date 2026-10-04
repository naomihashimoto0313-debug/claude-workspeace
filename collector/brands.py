"""ブランド一覧表（data/brands.csv）を読み込んで、ブランド名を見つける部分。"""

import csv
import re
import unicodedata
from pathlib import Path

from .text import normalize

BRANDS_CSV = Path(__file__).resolve().parent.parent / "data" / "brands.csv"

GENERIC_BRACKET = re.compile(
    r"新発売|発売|限定|新商品|新製品|新作|新色|公式|PR|プレスリリース|NEW|予約|"
    r"上陸|初|話題|累計|受賞|ランキング|第\d|\d|%|％|キャンペーン|情報|お知らせ|速報|"
    r"掲載|史上|開幕|記念|周年|アニメ|映画|キャラクター|コラボ|監修|特集|ブランド$"
)


class BrandBook:
    def __init__(self, path=BRANDS_CSV):
        self.rows = []
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                names = [row["ブランド名"]] + [
                    a for a in row["別名（検索用・|区切り）"].split("|") if a
                ]
                keys = sorted({normalize(n) for n in names if normalize(n)}, key=len, reverse=True)
                self.rows.append((row, keys))

    def find(self, text):
        """文章の中から一覧表にあるブランドを探す。見つかれば表の1行(dict)を返す。"""
        t = normalize(text)
        best = None
        for row, keys in self.rows:
            for k in keys:
                # 短い英字ブランド名（KATE など）が単語の一部で当たらないよう3文字以上に限る
                if len(k) >= 3 and k in t:
                    if best is None or len(k) > best[1]:
                        best = (row, len(k))
        return best[0] if best else None

    def match(self, brand_name, product_name=""):
        """ブランド名が一覧表のブランドと「同じ」と言えるときだけ、表の1行を返す。

        find() と違い、名前の一部だけ一致する場合（「コンフィー」と「フィー」など）は同じとみなさない。
        """
        names = [re.sub(r"[(（].*?[)）]", "", brand_name)] + re.findall(r"[(（]([^)）]+)[)）]", brand_name)
        names = {normalize(n) for n in names if normalize(n)}
        names.add(normalize(brand_name))
        product = normalize(product_name)
        for row, keys in self.rows:
            for k in keys:
                if k in names:
                    return row
                # 「SOFINA iP」「ソフィーナ プリマヴィスタ ○○」のように、名前の先頭がブランド名のとき
                if len(k) >= 3 and (any(n.startswith(k) for n in names) or product.startswith(k)):
                    return row
        return None

    def key(self, brand_name):
        """重複判定に使うブランドの名前（一覧表にあれば表の名前にそろえる）。"""
        row = self.find(brand_name)
        if row:
            return normalize(row["ブランド名"])
        main = re.sub(r"[(（].*?[)）]", "", brand_name)
        return normalize(main) or normalize(brand_name)


_LEAD_BRACKETS = r"^(?:[<＜〈《【\[][^>＞〉》】\]]*[>＞〉》】\]]\s*)*"
_WORD = r"[A-Za-z][A-Za-z0-9&'.\-]*(?: [A-Za-z0-9&'.\-]+){0,3}(?:[（(][^）)]{1,20}[）)])?|[ァ-ヶー・]{3,15}"


def _ok(s):
    return s and 2 <= len(s) <= 30 and not GENERIC_BRACKET.search(s)


def brand_from_title(title, provider):
    """PR TIMES のタイトルからブランド名らしい部分を取り出す（見つからなければ発表した会社名）。"""
    t = unicodedata.normalize("NFKC", title)
    patterns = [
        r"ブランド\s*[「『“\"]([^」』”\"]{2,30})[」』”\"]",  # ヘアケアブランド「アンプリール」
        r"[「『“\"]([^」』”\"]{2,30})[」』”\"]\s*(?:から|より)",  # 「クロノセル」から
        r"(?:^|\s|、)(" + _WORD + r")\s*(?:から|より)",  # Pyt（ピュット）より
        r"[<＜〈《【\[]([^>＞〉》】\]]{2,40})[>＞〉》】\]]",  # 【ブランド】
        _LEAD_BRACKETS + r"(" + _WORD + r")\s*[「『]",  # ブランド「商品」
    ]
    for p in patterns:
        for m in re.finditer(p, t):
            s = m.group(1).strip(" 、,")
            # 「メルティ リップ グロス」から新色、のように商品シリーズ名のことも多いので除く
            if p is patterns[1] and _PRODUCT_HINT.search(s) and not re.search(r"[A-Za-z]", s):
                continue
            if _ok(s):
                return s
    return re.sub(r"(株式会社|有限会社|合同会社|\(株\)|（株）)", "", provider).strip()


# 商品名らしくない「」の中身（キャッチコピー・人名・番組名など）
_NOT_PRODUCT = re.compile(r"(?:感|肌|香り|髪|色|気分|時間|ケア|！|!|？|\?)$|^[ぁ-ん]+$")
_PRODUCT_HINT = re.compile(
    r"[A-Za-z]|クリーム|ローション|セラム|美容液|化粧水|乳液|リップ|ティント|グロス|パレット|"
    r"アイシャドウ|マスカラ|ライナー|チーク|ファンデ|下地|パウダー|コンシーラー|シャンプー|"
    r"トリートメント|オイル|ミスト|ジェル|パック|マスク|ドライヤー|アイロン|美顔器|シリーズ|ライン"
)


def products_from_title(title, brand=""):
    """タイトルのかぎかっこ「」『』の中から商品名らしいものを取り出す（最大3つ）。"""
    names = []
    for m in re.finditer(r"[「『“\"]([^」』”\"]{2,60})[」』”\"]", title):
        # 『NANA』のような漫画・アニメ・映画などの作品名は商品名ではない
        if re.search(r"漫画|マンガ|アニメ|映画|ドラマ|作品|小説|ゲーム", title[max(0, m.start() - 8): m.start()]):
            continue
        names.append(m.group(1))
    scored = []
    for n in dict.fromkeys(x.strip() for x in names):
        if re.fullmatch(r"[\d,.%％ ]+", n) or (brand and normalize(n) == normalize(brand)):
            continue
        score = (2 if _PRODUCT_HINT.search(n) else 0) - (2 if _NOT_PRODUCT.search(n) else 0)
        scored.append((score, n))
    good = [n for s, n in scored if s > 0] or [n for s, n in scored if s == 0]
    if good:
        return "／".join(good[:3])
    # かぎかっこが無い（または商品名らしくない）ときはタイトルをそのまま（長すぎる部分は切る）
    t = re.sub(r"[<＜〈《【\[][^>＞〉》】\]]*[>＞〉》】\]]", "", title).strip()
    return t[:60]
