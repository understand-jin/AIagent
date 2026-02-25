from collections import Counter
import os
import re
from urllib.parse import urlparse

from flask import Flask, render_template, request
import pandas as pd

from link import search_news_for_keyword
from check import crawl_article

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


# =========================
# Groq API 설정
# =========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

client = Groq(api_key=GROQ_API_KEY)


# =========================
# 유틸 함수
# =========================
def _summarize_text(text: str, max_chars: int = 220) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[\.!?다])\s+", str(text))
    first = sentences[0].strip() if sentences else str(text).strip()
    return first[:max_chars] + "..." if len(first) > max_chars else first


def _source_info_list(urls):
    sources = []
    for u in urls:
        try:
            domain = urlparse(u).netloc
        except Exception:
            domain = str(u)
        sources.append({"url": u, "domain": domain})
    return sources


def _domain_filter(domain: str) -> bool:
    blocked = {"blog.naver.com", "tistory.com", "cafe.naver.com",
               "instagram.com", "facebook.com", "twitter.com", "x.com"}
    return domain not in blocked


# =========================
# ★ 노드 1: 수집가 (Researcher)
# =========================
def node_researcher(keyword: str, max_results: int = 20) -> pd.DataFrame:
    """
    키워드 + '대웅 {키워드}' 두 가지 쿼리로 Tavily 뉴스 수집
    → 중복·저신뢰 필터 → 최대 20건 정렬 DataFrame 반환
    """
    daewoong_query = f"대웅 {keyword}"

    df_main     = search_news_for_keyword(keyword,        max_results=max_results)
    df_daewoong = search_news_for_keyword(daewoong_query, max_results=max_results)

    df_all = pd.concat([df_main, df_daewoong], ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["url"]).reset_index(drop=True)

    rows = []
    seen_titles = set()

    for _, row in df_all.iterrows():
        url          = row.get("url", "")
        source_title = row.get("title", "")

        if not url:
            continue

        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = ""

        if not _domain_filter(domain):
            continue

        try:
            article_title, content = crawl_article(url)
        except Exception:
            continue

        content = content or ""
        summary = _summarize_text(content)

        title_key = (article_title or source_title)[:20]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        rows.append({
            "keyword":       row.get("keyword", keyword),
            "source_title":  source_title,
            "article_title": article_title or source_title,
            "url":           url,
            "domain":        domain,
            "content":       content,
            "summary":       summary,
        })

        if len(rows) >= 20:
            break

    if not rows:
        cols = ["keyword", "source_title", "article_title", "url", "domain", "content", "summary"]
        return pd.DataFrame(columns=cols)

    df_result = pd.DataFrame(rows).reset_index(drop=True)
    df_result = df_result.sort_values("article_title").reset_index(drop=True)
    return df_result


# =========================
# ★ 노드 2: 대웅 전문가 (Expert)
# =========================
def node_expert(keyword: str, df_articles: pd.DataFrame) -> str:
    df_dw = df_articles[df_articles["keyword"].str.contains("대웅", na=False)]
    if df_dw.empty:
        df_dw = df_articles[
            df_articles["content"].str.contains("대웅", na=False) |
            df_articles["article_title"].str.contains("대웅", na=False)
        ]

    bullets = []
    for _, r in df_dw.head(10).iterrows():
        bullets.append(
            f"- 제목: {r['article_title']}\n"
            f"  요약: {r['summary']}\n"
            f"  링크: {r['url']}"
        )

    bullets_text = "\n".join(bullets) if bullets else \
        "관련 기사를 찾지 못했습니다. 공개 정보를 기반으로 추론해 주세요."

    prompt = f"""
너는 대웅그룹(대웅제약, 대웅바이오 등) 전문 분석가다.
아래 뉴스 자료를 바탕으로 '{keyword}' 이슈에 대한 **대웅그룹의 현황과 포지셔닝**을 한국어로 정리해라.

작성 구조:
1. 대웅그룹 핵심 사업 현황 (2~3줄)
2. '{keyword}' 관련 대웅의 최근 동향 (3~5줄)
3. 경쟁사 대비 대웅의 강점/약점 (2~3줄)
4. 주목할 리스크 요인 (2줄)

분량: 500~700자. 과장 금지, 추정은 '추정' 표기.

[대웅 관련 뉴스]
{bullets_text}
""".strip()

    chat = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return (chat.choices[0].message.content or "").strip()


# =========================
# ★ 노드 3: 전략가 (Strategist)
# =========================
def node_strategist(keyword: str, df_articles: pd.DataFrame,
                    expert_report: str) -> dict:
    bullets = []
    for _, r in df_articles.head(10).iterrows():
        bullets.append(
            f"- 제목: {r['article_title']}\n"
            f"  요약: {r['summary']}"
        )

    prompt = f"""
너는 전략 컨설턴트다. 아래 두 가지 자료를 바탕으로 대웅그룹이 '{keyword}' 이슈에 대응하는
**단기(3개월) / 중기(1년) 전략 보고서**를 한국어 1페이지 형식으로 작성해라.

작성 구조:
## Executive Summary (3줄)
## 시장 핵심 트렌드 TOP3
## 단기 전략 (0~3개월) — 즉시 실행 가능한 액션 아이템 3개
## 중기 전략 (3~12개월) — 중장기 경쟁력 강화 방향 3개
## 예상 리스크 & 대응 방안
## 결론 및 우선순위

분량: 900~1300자. 구체적 수치/기간 포함 권장.

[시장 뉴스 요약]
{chr(10).join(bullets)}

[대웅그룹 현황 (전문가 분석)]
{expert_report}
""".strip()

    chat = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    strategy_text = (chat.choices[0].message.content or "").strip()

    short_term, mid_term = "", ""
    short_match = re.search(r"##\s*단기 전략.*?(?=##|$)", strategy_text, re.DOTALL)
    mid_match   = re.search(r"##\s*중기 전략.*?(?=##|$)", strategy_text, re.DOTALL)
    if short_match:
        short_term = short_match.group(0).strip()
    if mid_match:
        mid_term = mid_match.group(0).strip()

    return {
        "full_report": strategy_text,
        "short_term":  short_term,
        "mid_term":    mid_term,
        "sources":     _source_info_list(list(df_articles["url"].head(5))),
    }


# =========================
# 키워드 빈도 분석
# =========================
def analyze_keywords(df: pd.DataFrame, keyword: str) -> list:
    all_text = " ".join(df["content"].dropna().astype(str))
    tokens = re.findall(r"[A-Za-z가-힣0-9]{2,}", all_text)
    stopwords = {
        "그리고", "하지만", "이번", "대한", "관련", "통해", "있는", "한다",
        "하는", "위한", "있다", "이다", "했다", "됩니다", "것이", "대해", keyword,
    }
    tokens = [t for t in tokens if t not in stopwords]
    return Counter(tokens).most_common(20)


# =========================
# 메인 페이지
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    keyword  = None
    articles = []
    analysis = None
    expert   = None
    strategy = None

    if request.method == "POST":
        keyword = (request.form.get("keyword") or "").strip()

        if keyword:
            df            = node_researcher(keyword, max_results=20)
            expert_report = node_expert(keyword, df)
            strategy      = node_strategist(keyword, df, expert_report)

            num_articles = len(df)
            avg_length   = int(df["content"].astype(str).str.len().mean()) if num_articles else 0

            analysis = {
                "summary":      (
                    f"키워드 '{keyword}' + 대웅 관련 뉴스 {num_articles}건 분석. "
                    f"기사 평균 {avg_length}자."
                ),
                "num_articles": num_articles,
                "top_words":    analyze_keywords(df, keyword) if num_articles else [],
            }
            expert   = {"report": expert_report}
            articles = df.to_dict(orient="records")

    return render_template(
        "index.html",
        keyword=keyword,
        articles=articles,
        analysis=analysis,
        expert=expert,
        strategy=strategy,
    )


# =========================
# 실행
# =========================
# if __name__ == "__main__":
#     app.run(debug=True)
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)