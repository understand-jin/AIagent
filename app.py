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
    입력 키워드로 시장 뉴스 수집 (대웅 특정 검색 제거)
    """
    df_all = search_news_for_keyword(keyword, max_results=max_results)
    
    if df_all.empty:
        cols = ["keyword", "source_title", "article_title", "url", "domain", "content", "summary"]
        return pd.DataFrame(columns=cols)

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

    df_result = pd.DataFrame(rows).reset_index(drop=True)
    return df_result


# =========================
# ★ 노드 2: 기회 분석 전문가 (Opportunity Analyst)
# =========================
def node_expert(keyword: str, df_articles: pd.DataFrame) -> str:
    """
    일반 뉴스 자료를 바탕으로 대웅제약이 가질 수 있는 기회 요인 분석
    """
    bullets = []
    for _, r in df_articles.head(10).iterrows():
        bullets.append(
            f"- 제목: {r['article_title']}\n"
            f"  내용요약: {r['summary']}"
        )

    bullets_text = "\n".join(bullets) if bullets else "수집된 뉴스 정보가 부족합니다."

    prompt = f"""
너는 대웅제약의 전략기획팀 전문 분석가다.
제공된 시장 뉴스 자료를 바탕으로 '{keyword}' 이슈가 대웅제약에게 주는 **비즈니스 기회와 전략적 활용 방안**을 한국어로 보고해라.

작성 구조:
1. 시장 트렌드 핵심 요약 (2~3줄)
2. 대웅제약이 주목해야 할 3대 기회 요인 (각 요인별 상세 설명)
3. 대웅제약의 핵심 역량과의 접점 (R&D, 영업망, 제조시설 등 연계)
4. 활용 시 예상되는 장벽 및 해결 방향 (2줄)

분량: 600~800자. 구체적인 제약사 시각에서 분석할 것.

[시장 뉴스 자료]
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
너는 대한민국 1등 제약 전략 컨설턴트다. 
앞서 분석된 기회 요인들을 바탕으로 대웅제약이 '{keyword}' 이슈를 시장 점유율 확대와 
성장 동력으로 만들기 위한 **실행 전략 보고서**를 한국어로 작성해라.

작성 구조:
## 1. 전략적 기회 개요 (Executive Summary)
## 2. 대웅제약 맞춤형 대응 전략
   - 신약 R&D/인허가 관점
   - 시장 선점 및 마케팅 관점
## 3. 실행 로드맵 (단기: 3개월 / 중기: 1년)
## 4. 기대 효과 및 성과 지표 (KPI)
## 5. 리스크 관리 방안

분량: 1000~1300자. 논리적이고 전문적인 비즈니스 톤 유지.

[시장 뉴스 자료 요약]
{chr(10).join(bullets)}

[대웅제약 기회 요인 분석 보고]
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