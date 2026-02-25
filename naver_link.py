"""
naver_link.py
네이버 뉴스 검색 결과에서 기사 링크+제목을 스크래핑합니다.
"""
import urllib.parse
import requests
from bs4 import BeautifulSoup
import pandas as pd


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://search.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}


def search_naver_news(keyword: str, max_results: int = 20) -> pd.DataFrame:
    """
    네이버 뉴스 검색에서 키워드를 최신순으로 검색,
    기사 제목·URL을 DataFrame으로 반환.
    """
    rows = []
    # sort=1: 최신순, ds/de: 날짜 필터 없이 전체
    encoded = urllib.parse.quote(keyword)

    # 한 페이지 최대 10건 → 페이지 순회
    start = 1
    while len(rows) < max_results:
        url = (
            f"https://search.naver.com/search.naver"
            f"?where=news&query={encoded}&sort=1&start={start}"
        )
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            resp.raise_for_status()
        except Exception:
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # 네이버 뉴스 검색결과 카드 선택 (2024-2025 구조)
        cards = (
            soup.select("div.news_area")           # 일반 뉴스
            or soup.select("li.bx")                # 일부 레이아웃
        )

        if not cards:
            break

        for card in cards:
            if len(rows) >= max_results:
                break

            # 제목 + 링크
            title_el = (
                card.select_one("a.news_tit")
                or card.select_one(".news_tit")
            )
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link  = title_el.get("href", "")

            if not link or not title:
                continue

            # 네이버 뉴스 원문 링크인지 확인 (n.news.naver.com 등)
            rows.append({
                "keyword": keyword,
                "title": title,
                "url": link,
            })

        # 다음 페이지
        start += 10
        # 결과가 적으면 더 이상 페이지 없음
        if len(cards) < 5:
            break

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["keyword", "title", "url"])
