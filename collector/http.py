"""サイトへのアクセスをまとめた部分。

相手のサイトに負担をかけないよう、1回アクセスするごとに少し待ちます。
"""

import time

import requests

USER_AGENT = "Mozilla/5.0 (compatible; cosme-blog-research/1.0; personal use)"

_last_access = {}


def get(url, params=None, wait=1.5, encoding=None, retries=2):
    """URL を開いて requests.Response を返す。同じサイトへは wait 秒以上あける。"""
    host = url.split("/")[2]
    elapsed = time.time() - _last_access.get(host, 0)
    if elapsed < wait:
        time.sleep(wait - elapsed)

    for attempt in range(retries + 1):
        try:
            res = requests.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
            )
            _last_access[host] = time.time()
            if res.status_code == 200:
                if encoding:
                    res.encoding = encoding
                return res
            if res.status_code == 404:
                return None
        except requests.RequestException:
            _last_access[host] = time.time()
        if attempt < retries:
            time.sleep(5 * (attempt + 1))
    return None
