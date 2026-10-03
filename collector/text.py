"""文章から発売日・価格・カテゴリなどを読み取る部分（ルールベースなので完璧ではありません）。"""

import html
import re
import unicodedata
from datetime import date

CATEGORY_KEYWORDS = {
    "美容家電": [
        "美顔器", "美容家電", "美容機器", "ドライヤー", "ヘアアイロン", "ストレートアイロン",
        "カールアイロン", "ヘアビューロン", "光美容器", "脱毛器", "EMS", "LED美容",
        "電動洗顔", "電動ブラシ", "スカルプブラシ", "温熱",
    ],
    "ヘアケア": [
        "シャンプー", "コンディショナー", "トリートメント", "ヘアオイル", "ヘアミスト",
        "ヘアケア", "ヘアマスク", "スカルプ", "頭皮", "白髪", "ヘアカラー", "スタイリング",
        "ヘアバーム", "ヘアミルク", "ヘアセラム", "洗い流さない",
    ],
    "ベースメイク": [
        "ファンデーション", "ファンデ", "化粧下地", "下地", "プライマー", "コンシーラー",
        "クッションファンデ", "フェイスパウダー", "ルースパウダー", "プレストパウダー",
        "BBクリーム", "CCクリーム", "ベースメイク", "トーンアップ下地", "セッティングパウダー",
        "セッティングスプレー", "メイクキープ",
    ],
    "ポイントメイク": [
        "リップ", "口紅", "ルージュ", "ティント", "グロス", "アイシャドウ", "アイシャドー",
        "アイライナー", "マスカラ", "アイブロウ", "眉マスカラ", "チーク", "ハイライター", "シェーディング",
        "アイパレット", "アイカラー", "ポイントメイク", "メイクパレット", "コフレ",
    ],
    "スキンケア": [
        "化粧水", "美容液", "乳液", "クリーム", "洗顔", "クレンジング", "パック",
        "シートマスク", "フェイスマスク", "スキンケア", "美容オイル", "アイクリーム",
        "日焼け止め", "UVケア", "ローション", "セラム", "トナー", "導入液", "ブースター",
        "オールインワン", "ピーリング", "エッセンス", "基礎化粧品", "角質ケア",
    ],
}

# 「新商品のお知らせ」らしいかを見る言葉
NEW_PRODUCT_WORDS = re.compile(
    r"発売|新商品|新製品|新作|登場|デビュー|ローンチ|リニューアル|限定|予約|上陸|新色|新シリーズ|新ブランド"
)
# 新商品以外の話題（調査・イベント報告など）らしい言葉
NOT_PRODUCT_WORDS = re.compile(
    r"調査|アンケート|セミナー|開催しました|開催レポート|受賞|決算|資金調達|採用|求人|"
    r"出店|オープン|ポップアップ|POP ?UP|イベント|キャンペーン|プレゼント|募集|提携|業務|就任|"
    r"クリニック|サロン|施術|サプリ|医療|読み解く|解析|特集|フェス|Festival|バトル|開幕|紹介|出演|パーティ|研究|成功|開発|発表会|スタートアップ|レビュー"
)
# 今回の5カテゴリに入らないもの（タイトルにあれば対象外にする）
OUT_OF_SCOPE = re.compile(
    r"ダンベル|シューズ|スニーカー|靴|家具|ステッパー|ウィッグ|かつら|ネイル|ボディ|ハンドクリーム|"
    r"バスト|フレグランス|香水|オードパルファン|オードトワレ|入浴剤|バスソルト|デオドラント|"
    r"除毛|脱毛|歯磨き|オーラルケア|サプリ|ペット|下着|アパレル|ファッション|バッグ|ジュエリー"
)
# 顔・髪向けの商品であることを示す言葉（OUT_OF_SCOPE の言葉と一緒にあれば対象に戻す）
IN_SCOPE_HINT = re.compile(
    r"フェイス|顔|化粧水|美容液|乳液|洗顔|クレンジング|ファンデ|下地|リップ|アイシャドウ|マスカラ|"
    r"チーク|シャンプー|トリートメント|ヘア|頭皮|美顔器|ドライヤー"
)
STRONG_NEW_WORDS = re.compile(r"発売|新商品|新製品|新作|新色|新シリーズ|新ブランド")


def html_to_text(src):
    src = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", src or "")
    src = re.sub(r"<[^>]+>", "", src)
    src = html.unescape(src).replace("　", " ")
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in src.split("\n")]
    return "\n".join(l for l in lines if l)


def normalize(s):
    """比較用に文字をそろえる（全角半角・大文字小文字・記号や空白を無視）。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[^0-9a-z぀-ヿ一-鿿]", "", s)


def classify(title, body):
    """カテゴリを判定する。対象外なら空文字。タイトルの言葉を重く見る。"""
    title_n = unicodedata.normalize("NFKC", title)
    if OUT_OF_SCOPE.search(title_n) and not IN_SCOPE_HINT.search(title_n):
        return ""
    body_n = unicodedata.normalize("NFKC", body[:1500])
    scores = {}
    for cat, words in CATEGORY_KEYWORDS.items():
        t = sum(title_n.count(w) for w in words)
        b = sum(body_n.count(w) for w in words)
        scores[cat] = t * 5 + b
    # 「クリーム」は BB/CC クリームでも数えられるので補正
    bbcc = (title_n + body_n).count("BBクリーム") + (title_n + body_n).count("CCクリーム")
    scores["スキンケア"] -= bbcc
    best = max(scores, key=scores.get)
    # タイトルにカテゴリの言葉が無い場合は、本文に何度も出てくるときだけ対象にする
    if scores[best] < 5:
        return ""
    return best


# ---------- 発売日 ----------

_DATE = re.compile(
    r"(?:(20\d\d)\s*[年/.]\s*)?(\d{1,2})\s*[月/]\s*(?:(\d{1,2})\s*日?|(上旬|中旬|下旬))"
)


def _to_date(y, m, d, part, base):
    m = int(m)
    if not 1 <= m <= 12:
        return None
    if y:
        y = int(y)
    else:
        # 年が書いていない場合は情報公開日から推測（公開日より半年以上前なら翌年）
        y = base.year + (1 if m < base.month - 6 else 0)
    if part:
        return (y, m, {"上旬": 5, "中旬": 15, "下旬": 25}[part], f"{y}/{m:02d} {part}")
    d = int(d)
    try:
        date(y, m, d)
    except ValueError:
        return None
    return (y, m, d, f"{y}/{m:02d}/{d:02d}")


def find_release_date(text, base):
    """「〇月〇日発売」などから発売日を探す。(表示用文字列, 並べ替え用date) を返す。"""
    text = unicodedata.normalize("NFKC", text)
    candidates = []
    for m in re.finditer(r"発売", text):
        before = text[max(0, m.start() - 45): m.start()]
        after = text[m.end(): m.end() + 30]
        # 「〇月〇日（木）より発売」：発売の直前にある日付（いちばん近いもの）
        found = list(_DATE.finditer(before))
        if found:
            candidates.append((0, found[-1]))
            continue
        # 「発売日：〇月〇日」
        if after.startswith(("日", "予定日", "開始日")):
            f = _DATE.search(after)
            if f:
                candidates.append((0, f))
    if not candidates:
        m = re.search(r"(?:販売開始|登場|発売)(?:日|予定日)?[:：]\s*", text)
        if m:
            f = _DATE.match(text, m.end())
            if f:
                candidates.append((1, f))
    for _, f in sorted(candidates, key=lambda c: c[0]):
        r = _to_date(f.group(1), f.group(2), f.group(3), f.group(4), base)
        if r:
            return r[3], date(r[0], r[1], r[2])
    return "", None


# ---------- 価格 ----------

_PRICE_INC = re.compile(
    r"(?:税込(?:価格)?\s*[:：]?\s*[¥￥]?\s*([\d,]{3,7})\s*円?)|"
    r"(?:[¥￥]?\s*([\d,]{3,7})\s*円?\s*[(（]\s*税込)|"
    r"(?:[¥￥]\s*([\d,]{3,7})\s*[(（]\s*税込)"
)
_PRICE_EXC = re.compile(r"[¥￥]?\s*([\d,]{3,7})\s*円?\s*[(（]\s*(?:税抜|税別|本体)")
_PRICE_ANY = re.compile(r"(?:価格|価|円)[^\n]{0,15}?[¥￥]\s*([\d,]{3,7})|([\d,]{3,7})円")


def _nums(matches):
    out = []
    for m in matches:
        v = next((g for g in m.groups() if g), None)
        if not v:
            continue
        try:
            n = int(v.replace(",", ""))
        except ValueError:
            continue
        if 100 <= n <= 300000:
            out.append(n)
    return out


def find_price(text):
    """価格を探す。(表示用文字列, いちばん安い税込価格 or None) を返す。"""
    text = unicodedata.normalize("NFKC", text)
    inc = sorted(set(_nums(_PRICE_INC.finditer(text))))
    if inc:
        return _fmt(inc, "税込"), inc[0]
    exc = sorted(set(_nums(_PRICE_EXC.finditer(text))))
    if exc:
        return _fmt(exc, "税抜"), int(exc[0] * 1.1)
    if "オープン価格" in text:
        return "オープン価格", None
    # 価格の近くに書かれた「〇〇円」（税込か不明）
    m = re.search(r"価格[^\n]{0,30}", text)
    if m:
        anyp = sorted(set(_nums(_PRICE_ANY.finditer(m.group()))))
        if anyp:
            return _fmt(anyp, "税込/税抜不明"), anyp[0]
    return "", None


def _fmt(nums, note):
    if len(nums) == 1:
        return f"{nums[0]:,}円（{note}）"
    return f"{nums[0]:,}〜{nums[-1]:,}円（{note}）"


def summarize(text, limit=150):
    """本文の最初のほうを短くまとめる（会社の住所・代表者などのカッコ書きは消す）。"""
    t = re.sub(r"[（(][^（）()]*(?:本社|代表|所在地|URL|http)[^（）()]*[）)]", "", text)
    t = re.sub(r"\s+", " ", t).strip()
    sentences = re.split(r"(?<=。)", t)
    out = ""
    for s in sentences:
        if len(out) + len(s) > limit and out:
            break
        out += s
    return out[:limit] + ("…" if len(out) > limit else "")
