import requests
from bs4 import BeautifulSoup
from typing import Tuple


DEFAULT_URL = "https://www.hitnews.co.kr/news/articleView.html?idxno=72366"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://search.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}


def crawl_article(url: str = DEFAULT_URL) -> Tuple[str, str]:
    """주어진 뉴스 URL에서 제목과 본문 텍스트를 크롤링."""
    resp = requests.get(url, headers=_HEADERS, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── 제목 ──
    title_el = soup.select_one("h1") or soup.title
    title = title_el.get_text(strip=True) if title_el else ""

    # ── 본문 선택자 (우선순위 순) ──
    # 네이버 뉴스 (n.news.naver.com)
    content_el = soup.select_one("#dic_area")

    # 일반 언론사 공통 선택자
    if not content_el:
        content_el = soup.select_one(
            "#article-view-content-div, "
            ".article-body, "
            "#articleBody, "
            "#articeBody, "
            ".article_body, "
            ".news_end, "         # 일부 언론사
            "#newsEndContents, "  # 뉴스1 등
            "article"
        )

    paragraphs = []
    if content_el:
        p_tags = content_el.select("p")
        if not p_tags:
            # p 태그가 없는 경우 전체 텍스트 fallback
            paragraphs = [content_el.get_text(" ", strip=True)]
    else:
        # 최후 fallback: 전체 페이지 p 태그
        p_tags = soup.find_all("p")

    for p in p_tags:
        text = p.get_text(" ", strip=True)
        if text:
            paragraphs.append(text)

    body = "\n".join(paragraphs)
    return title, body


if __name__ == "__main__":
    title, body = crawl_article()
    print(title)
    print("=" * 80)
    print(body)