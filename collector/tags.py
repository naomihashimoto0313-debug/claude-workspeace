"""ブログの記事候補を選びやすくするためのタグを付ける部分。

どれも「言葉が含まれているか」で機械的に判定しているので、最後は人の目で確認してください。
判定の理由は CSV の「タグの根拠」列に書き出します。
"""

import re
import unicodedata

PETIT_PRICE = 2000  # この金額（税込）以下ならプチプラ

# 記事の最後にある会社紹介・公式SNSの案内などで誤判定しないよう、文章の最初のほうだけを見る
TAG_TEXT_LEN = 600

TAG_WORDS = {
    "SNSで話題になりそう": r"SNS|TikTok|ティックトック|Instagram|インスタ|バズ|話題|インフルエンサー|"
    r"YouTuber|ユーチューバー|コラボ|即完売|完売|再販|Qoo10|メガ割|累計.{0,10}(?:万|突破)|韓国コスメ|"
    r"推し|キャラクター|サンリオ|ディズニー|ポケモン",
    "新ブランド／新シリーズ": r"新ブランド|ブランドデビュー|ブランド誕生(?!\d*周年)|新シリーズ|"
    r"新ライン|日本初上陸|初上陸|日本上陸",
    "限定商品": r"限定|ホリデー|クリスマスコフレ|コフレ",
    "40代でも使いやすそう": r"エイジング|年齢肌|年齢に応じた|大人の?肌|大人世代|大人女性|40代|50代|"
    r"ハリ不足|ハリ・|ハリを|ハリと|シワ|しわ|たるみ|くすみ|毛穴|白髪|うねり|ゆらぎ|シミ|しみ・|"
    r"レチノール|ナイアシンアミド|敏感肌|カバー力|乾燥小じわ|ほうれい|目元の悩み|更年期",
}


def tag(row, listed_brand):
    text = unicodedata.normalize("NFKC", row["_text"])[:TAG_TEXT_LEN]
    tags, reasons = [], []
    for name, pattern in TAG_WORDS.items():
        m = re.search(pattern, text)
        if name == "SNSで話題になりそう" and listed_brand and listed_brand["系統"] in ("SNS系", "韓国"):
            tags.append(name)
            reasons.append(f"{name}：ブランド一覧で「{listed_brand['系統']}」")
        elif m:
            tags.append(name)
            reasons.append(f"{name}：「{m.group()}」")
        if name == "SNSで話題になりそう":
            # プチプラはSNSの次に入れる（タグの並びを依頼どおりにするため）
            _petit(row, listed_brand, tags, reasons)
    return tags, reasons


def _petit(row, listed_brand, tags, reasons):
    price = row.get("_price_min")
    if price is not None and price <= PETIT_PRICE:
        tags.append("プチプラ")
        reasons.append(f"プチプラ：{price:,}円")
    elif price is None and listed_brand and listed_brand["価格帯"] == "プチプラ":
        tags.append("プチプラ")
        reasons.append("プチプラ：価格不明だがブランド一覧で「プチプラ」")
