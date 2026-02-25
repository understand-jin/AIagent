import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TAVILY_API_KEY")


def search_news_for_keywords(keywords, max_results: int = 20) -> pd.DataFrame:
    """여러 키워드에 대해 Tavily 뉴스 검색을 수행하고 DataFrame 반환."""
    all_data = []

    for keyword in keywords:
        response = requests.post(
            "https://api.tavily.com/search",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            json={
                "query": keyword,
                "topic": "news",
                "max_results": max_results,
            },
            timeout=15,
        )

        response.raise_for_status()
        data = response.json()

        for item in data.get("results", []):
            all_data.append(
                {
                    "keyword": keyword,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                }
            )

    df = pd.DataFrame(all_data)
    return df


def search_news_for_keyword(keyword: str, max_results: int = 20) -> pd.DataFrame:
    """단일 키워드용 편의 함수."""
    return search_news_for_keywords([keyword], max_results=max_results)


if __name__ == "__main__":
    # 기존 동작 유지: 여러 키워드에 대해 CSV 저장
    keywords = ["제약 AI", "신약", "질병"]
    df = search_news_for_keywords(keywords, max_results=20)
    df.to_csv("pharma_news.csv", index=False, encoding="utf-8-sig")
    print("완료!")